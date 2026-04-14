from __future__ import annotations

import json
import os
import re
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import fitz  # PyMuPDF
import pandas as pd
from dotenv import load_dotenv
from flask import (
    Flask,
    jsonify,
    redirect,
    render_template,
    request,
    send_from_directory,
    url_for,
)
from werkzeug.utils import secure_filename

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
UPLOAD_DIR = BASE_DIR / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)

SOURCE_DIR = BASE_DIR / "source_files"
SOURCE_DIR.mkdir(exist_ok=True)

DEMO_JOB_ID = "hardcoded_demo"

ALLOWED_PDF = {".pdf"}
ALLOWED_XLSX = {".xlsx", ".xls"}
UNIT_PATTERN = re.compile(r"LF-[A-Z]-\d{3}", re.IGNORECASE)

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 30 * 1024 * 1024
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "dev-secret-change-me")


@dataclass
class UnitPosition:
    unit_code: str
    page: int
    x: float
    y: float
    w: float
    h: float
    page_width: float
    page_height: float


@dataclass
class InventoryUnit:
    unit_code: str
    serial_no: str | None
    level: str | None
    floor: str | None
    type: str | None
    uds_sqft: float | None
    total_area_sqft: float | None
    page: int | None = None
    x: float | None = None
    y: float | None = None
    w: float | None = None
    h: float | None = None
    page_width: float | None = None
    page_height: float | None = None


def normalize_text(value: Any) -> str:
    if pd.isna(value):
        return ""
    return str(value).strip()


def normalize_unit_code(value: Any) -> str:
    text = normalize_text(value).upper().replace(" ", "")
    match = UNIT_PATTERN.search(text)
    return match.group(0) if match else text


def to_float(value: Any) -> float | None:
    text = normalize_text(value).replace(",", "")
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def find_project_file(possible_names: list[str]) -> Path | None:
    search_roots = [SOURCE_DIR, BASE_DIR, UPLOAD_DIR]
    normalized_names = [name.strip().lower() for name in possible_names]

    for root in search_roots:
        if not root.exists():
            continue

        for candidate in possible_names:
            direct = root / candidate
            if direct.exists() and direct.is_file():
                return direct

        for path in root.rglob("*"):
            if path.is_file() and path.name.strip().lower() in normalized_names:
                return path

    return None


DEMO_PDF = find_project_file(
    [
        "MOI Godown Presenter_July_8th_2025-1 (dragged).pdf",
        "moi_godown_presenter.pdf",
    ]
)
DEMO_EXCEL = find_project_file(
    [
        "Unsold Inventory(1).xlsx",
        "unsold_inventory.xlsx",
    ]
)


def load_inventory(excel_path: Path) -> list[InventoryUnit]:
    raw_df = pd.read_excel(excel_path, sheet_name=0, header=None)
    raw_df = raw_df.dropna(how="all")

    if raw_df.empty:
        return []

    header_row_index = None
    for idx in range(min(15, len(raw_df))):
        row_text = " | ".join(normalize_text(v).upper() for v in raw_df.iloc[idx].tolist())
        if "SHOP" in row_text and "AREA" in row_text:
            header_row_index = idx
            break

    if header_row_index is None:
        raise ValueError("Could not identify the header row in the inventory sheet.")

    headers = [normalize_text(v) for v in raw_df.iloc[header_row_index].tolist()]
    df = raw_df.iloc[header_row_index + 1 :].copy()
    df.columns = headers
    df = df.dropna(how="all")

    rename_map: dict[str, str] = {}
    for col in df.columns:
        key = normalize_text(col).upper().replace("\n", " ")
        if key.startswith("S.NO"):
            rename_map[col] = "serial_no"
        elif "LEVEL" in key:
            rename_map[col] = "level"
        elif key == "FLOOR":
            rename_map[col] = "floor"
        elif key == "TYPE":
            rename_map[col] = "type"
        elif "SHOP" in key:
            rename_map[col] = "unit_code"
        elif "UDS" in key:
            rename_map[col] = "uds_sqft"
        elif "TOTAL AREA" in key:
            rename_map[col] = "total_area_sqft"

    df = df.rename(columns=rename_map)

    required = {"unit_code", "total_area_sqft"}
    if not required.issubset(df.columns):
        raise ValueError("The inventory sheet must contain unit code and total area columns.")

    units: list[InventoryUnit] = []
    for _, row in df.iterrows():
        unit_code = normalize_unit_code(row.get("unit_code"))
        if not UNIT_PATTERN.fullmatch(unit_code):
            continue

        units.append(
            InventoryUnit(
                unit_code=unit_code,
                serial_no=normalize_text(row.get("serial_no")) or None,
                level=normalize_text(row.get("level")) or None,
                floor=normalize_text(row.get("floor")) or None,
                type=normalize_text(row.get("type")) or None,
                uds_sqft=to_float(row.get("uds_sqft")),
                total_area_sqft=to_float(row.get("total_area_sqft")),
            )
        )

    return units


def extract_unit_positions(
    pdf_path: Path, render_scale: float = 1.8
) -> tuple[dict[str, UnitPosition], list[dict[str, Any]]]:
    doc = fitz.open(pdf_path)
    positions: dict[str, UnitPosition] = {}
    pages: list[dict[str, Any]] = []

    for index, page in enumerate(doc):
        pix = page.get_pixmap(matrix=fitz.Matrix(render_scale, render_scale), alpha=False)
        image_name = f"page_{index + 1}.png"
        image_path = pdf_path.parent / image_name
        pix.save(str(image_path))

        page_rect = page.rect
        pages.append(
            {
                "page": index + 1,
                "image": image_name,
                "width": float(page_rect.width),
                "height": float(page_rect.height),
                "rendered_width": pix.width,
                "rendered_height": pix.height,
            }
        )

        words = page.get_text("words")
        seen_on_page: set[str] = set()

        for word in words:
            x0, y0, x1, y1, text = word[:5]
            code = normalize_unit_code(text)

            if not UNIT_PATTERN.fullmatch(code):
                continue
            if code in seen_on_page:
                continue

            seen_on_page.add(code)
            positions[code] = UnitPosition(
                unit_code=code,
                page=index + 1,
                x=float(x0),
                y=float(y0),
                w=float(x1 - x0),
                h=float(y1 - y0),
                page_width=float(page_rect.width),
                page_height=float(page_rect.height),
            )

    doc.close()
    return positions, pages


def combine_data(units: list[InventoryUnit], positions: dict[str, UnitPosition]) -> list[InventoryUnit]:
    combined: list[InventoryUnit] = []

    for unit in units:
        pos = positions.get(unit.unit_code)
        if pos:
            unit.page = pos.page
            unit.x = pos.x
            unit.y = pos.y
            unit.w = pos.w
            unit.h = pos.h
            unit.page_width = pos.page_width
            unit.page_height = pos.page_height
        combined.append(unit)

    return combined


def build_dataset(pdf_path: Path, excel_path: Path, job_dir: Path) -> dict[str, Any]:
    units = load_inventory(excel_path)
    positions, pages = extract_unit_positions(pdf_path)
    combined_units = combine_data(units, positions)

    matched = sum(1 for u in combined_units if u.page is not None)
    total_area = sum(u.total_area_sqft or 0 for u in combined_units)

    dataset = {
        "summary": {
            "total_unsold_units": len(combined_units),
            "matched_on_blueprint": matched,
            "unmatched_units": len(combined_units) - matched,
            "total_unsold_area_sqft": round(total_area, 2),
        },
        "pages": pages,
        "units": [asdict(u) for u in sorted(combined_units, key=lambda x: x.unit_code)],
    }

    with open(job_dir / "dataset.json", "w", encoding="utf-8") as f:
        json.dump(dataset, f, indent=2)

    return dataset


def ensure_demo_dataset() -> str:
    global DEMO_PDF, DEMO_EXCEL

    if DEMO_PDF is None:
        DEMO_PDF = find_project_file(
            ["MOI Godown Presenter_July_8th_2025-1 (dragged).pdf", "moi_godown_presenter.pdf"]
        )
    if DEMO_EXCEL is None:
        DEMO_EXCEL = find_project_file(
            ["Unsold Inventory(1).xlsx", "unsold_inventory.xlsx"]
        )

    if not DEMO_PDF or not DEMO_PDF.exists():
        raise FileNotFoundError("Demo PDF not found in source_files.")
    if not DEMO_EXCEL or not DEMO_EXCEL.exists():
        raise FileNotFoundError("Demo Excel not found in source_files.")

    job_dir = UPLOAD_DIR / DEMO_JOB_ID
    job_dir.mkdir(parents=True, exist_ok=True)

    pdf_copy = job_dir / DEMO_PDF.name
    excel_copy = job_dir / DEMO_EXCEL.name

    if not pdf_copy.exists():
        pdf_copy.write_bytes(DEMO_PDF.read_bytes())
    if not excel_copy.exists():
        excel_copy.write_bytes(DEMO_EXCEL.read_bytes())

    dataset_path = job_dir / "dataset.json"
    if not dataset_path.exists():
        build_dataset(pdf_copy, excel_copy, job_dir)

    return DEMO_JOB_ID


def firebase_env_payload() -> dict[str, str | None]:
    return {
        "apiKey": os.environ.get("FIREBASE_API_KEY"),
        "authDomain": os.environ.get("FIREBASE_AUTH_DOMAIN"),
        "projectId": os.environ.get("FIREBASE_PROJECT_ID"),
        "storageBucket": os.environ.get("FIREBASE_STORAGE_BUCKET"),
        "messagingSenderId": os.environ.get("FIREBASE_MESSAGING_SENDER_ID"),
        "appId": os.environ.get("FIREBASE_APP_ID"),
        "measurementId": os.environ.get("FIREBASE_MEASUREMENT_ID"),
    }


@app.route("/firebase-config.js")
def firebase_config_js():
    payload = firebase_env_payload()
    ready = bool(payload.get("apiKey") and payload.get("projectId") and payload.get("appId"))
    js = "window.BLUEPRINT_APP_FIREBASE_CONFIG = " + json.dumps(payload) + ";\n"
    js += f"window.BLUEPRINT_APP_FIREBASE_READY = {'true' if ready else 'false'};\n"
    return app.response_class(js, mimetype="application/javascript")


@app.route("/", methods=["GET"])
def index():
    try:
        job_id = ensure_demo_dataset()
        return redirect(url_for("viewer", job_id=job_id))
    except Exception as exc:
        return render_template("index.html", error=f"{exc} BASE_DIR={BASE_DIR} SOURCE_DIR={SOURCE_DIR}")


@app.route("/viewer/<job_id>")
def viewer(job_id: str):
    dataset_path = UPLOAD_DIR / job_id / "dataset.json"
    if not dataset_path.exists():
        return redirect(url_for("index"))

    with open(dataset_path, "r", encoding="utf-8") as f:
        dataset = json.load(f)

    return render_template(
        "viewer.html",
        dataset=dataset,
        job_id=job_id,
        firebase_ready=bool(firebase_env_payload().get("projectId")),
    )


@app.route("/uploads/<job_id>/<path:filename>")
def uploaded_file(job_id: str, filename: str):
    return send_from_directory(UPLOAD_DIR / job_id, filename)


@app.route("/api/<job_id>/dataset")
def dataset_api(job_id: str):
    dataset_path = UPLOAD_DIR / job_id / "dataset.json"
    if not dataset_path.exists():
        return jsonify({"error": "Not found"}), 404

    with open(dataset_path, "r", encoding="utf-8") as f:
        return jsonify(json.load(f))


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5001)