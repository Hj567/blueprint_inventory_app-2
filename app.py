from __future__ import annotations

import json
import os
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, jsonify, redirect, render_template, send_from_directory, url_for

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
PREBUILT_DIR = BASE_DIR / "prebuilt_demo"

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "dev-secret-change-me")


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


def load_dataset() -> dict:
    dataset_path = PREBUILT_DIR / "dataset.json"
    if not dataset_path.exists():
        raise FileNotFoundError(f"dataset.json not found in {PREBUILT_DIR}")
    with open(dataset_path, "r", encoding="utf-8") as f:
        return json.load(f)


@app.route("/firebase-config.js")
def firebase_config_js():
    payload = firebase_env_payload()
    ready = bool(payload.get("apiKey") and payload.get("projectId") and payload.get("appId"))
    js = "window.BLUEPRINT_APP_FIREBASE_CONFIG = " + json.dumps(payload) + ";\n"
    js += f"window.BLUEPRINT_APP_FIREBASE_READY = {'true' if ready else 'false'};\n"
    return app.response_class(js, mimetype="application/javascript")


@app.route("/")
def index():
    return redirect(url_for("viewer"))


@app.route("/viewer")
def viewer():
    try:
        dataset = load_dataset()
        return render_template(
            "viewer.html",
            dataset=dataset,
            job_id="prebuilt_demo",
            firebase_ready=bool(firebase_env_payload().get("projectId")),
        )
    except Exception as exc:
        return render_template("index.html", error=str(exc)), 500


@app.route("/prebuilt/<path:filename>")
def prebuilt_file(filename: str):
    return send_from_directory(PREBUILT_DIR, filename)


@app.route("/api/dataset")
def dataset_api():
    try:
        return jsonify(load_dataset())
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5001)
