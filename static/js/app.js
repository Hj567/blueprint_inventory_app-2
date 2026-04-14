(function () {
  const appEl = document.getElementById("app");
  if (!appEl) return;

  const dataset = JSON.parse(appEl.dataset.dataset);
  const jobId = appEl.dataset.jobId;

  const tableBody = document.getElementById("unitTableBody");
  const pagesContainer = document.getElementById("pagesContainer");
  const selectedAreaEl = document.getElementById("selectedArea");
  const selectionMetaEl = document.getElementById("selectionMeta");
  const selectedChipsEl = document.getElementById("selectedChips");
  const searchInput = document.getElementById("unitSearch");
  const pageFilter = document.getElementById("pageFilter");
  const clearBtn = document.getElementById("clearSelection");
  const selectVisibleBtn = document.getElementById("selectVisible");
  const saveSelectionBtn = document.getElementById("saveSelection");
  const reloadSelectionBtn = document.getElementById("reloadSelection");
  const userNameInput = document.getElementById("userNameInput");
  const saveNameBtn = document.getElementById("saveNameBtn");
  const firebaseStatus = document.getElementById("firebaseStatus");
  const comparisonTableBody = document.getElementById("comparisonTableBody");

  const state = {
    selected: new Set(),
    search: "",
    page: "all",
    userName: localStorage.getItem(`blueprint-user-name-${jobId}`) || "",
    userId: localStorage.getItem(`blueprint-user-id-${jobId}`) || crypto.randomUUID(),
    compareRows: [],
  };

  localStorage.setItem(`blueprint-user-id-${jobId}`, state.userId);
  userNameInput.value = state.userName;

  const firebaseReady = Boolean(window.BLUEPRINT_APP_FIREBASE_READY);
  let db = null;
  if (firebaseReady && window.firebase) {
    const app = firebase.apps.length ? firebase.app() : firebase.initializeApp(window.BLUEPRINT_APP_FIREBASE_CONFIG);
    db = firebase.firestore(app);
  }

  function slugify(text) {
    return (text || "")
      .trim()
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, "-")
      .replace(/(^-|-$)/g, "")
      .slice(0, 60);
  }

  function currentUserName() {
    return (state.userName || "").trim();
  }

  function getUserDocId() {
    return `${slugify(currentUserName()) || "user"}-${state.userId.slice(0, 8)}`;
  }

  function unitMatchesFilters(unit) {
    const searchOk = !state.search || (unit.unit_code || "").toLowerCase().includes(state.search);
    const pageOk = state.page === "all" || String(unit.page || "") === state.page;
    return searchOk && pageOk;
  }

  function visibleUnits() {
    return dataset.units.filter(unitMatchesFilters);
  }

  function totalSelectedArea() {
    return dataset.units
      .filter((u) => state.selected.has(u.unit_code))
      .reduce((sum, u) => sum + (Number(u.total_area_sqft) || 0), 0);
  }

  function markerDimensions(unit) {
    const padX = Math.max((unit.w || 20) * 0.2, 10);
    const padY = Math.max((unit.h || 8) * 0.8, 10);
    return {
      left: ((unit.x - padX) / unit.page_width) * 100,
      top: ((unit.y - padY) / unit.page_height) * 100,
      width: (((unit.w || 20) + padX * 2) / unit.page_width) * 100,
      height: (((unit.h || 8) + padY * 2) / unit.page_height) * 100,
    };
  }

  function toggleUnit(unitCode) {
    if (state.selected.has(unitCode)) {
      state.selected.delete(unitCode);
    } else {
      state.selected.add(unitCode);
    }
    render();
  }

  function scrollToMarker(unitCode) {
    const marker = document.querySelector(`[data-marker="${unitCode}"]`);
    if (marker) marker.scrollIntoView({ behavior: "smooth", block: "center" });
  }

  function setStatus(message, type) {
    firebaseStatus.textContent = message;
    firebaseStatus.className = `status-line${type ? ` ${type}` : ""}`;
  }

  function renderTable() {
    const rows = visibleUnits()
      .map((unit) => {
        const checked = state.selected.has(unit.unit_code) ? "checked" : "";
        const activeClass = state.selected.has(unit.unit_code) ? "active" : "";
        return `
          <tr class="${activeClass}" data-unit="${unit.unit_code}">
            <td><input type="checkbox" ${checked} data-check="${unit.unit_code}" /></td>
            <td>${unit.unit_code}</td>
            <td>${Number(unit.total_area_sqft || 0).toLocaleString()}</td>
            <td>${unit.page || "-"}</td>
          </tr>
        `;
      })
      .join("");

    tableBody.innerHTML = rows || `<tr><td colspan="4">No units match the current filters.</td></tr>`;

    tableBody.querySelectorAll("tr[data-unit]").forEach((row) => {
      row.addEventListener("click", (event) => {
        if (event.target.matches('input[type="checkbox"]')) return;
        toggleUnit(row.dataset.unit);
        scrollToMarker(row.dataset.unit);
      });
    });

    tableBody.querySelectorAll("input[data-check]").forEach((checkbox) => {
      checkbox.addEventListener("click", (event) => event.stopPropagation());
      checkbox.addEventListener("change", () => toggleUnit(checkbox.dataset.check));
    });
  }

  function renderPages() {
    const pagesHtml = dataset.pages
      .filter((page) => state.page === "all" || String(page.page) === state.page)
      .map((page) => {
        const pageUnits = visibleUnits().filter((u) => u.page === page.page);
        const markers = pageUnits
          .map((unit) => {
            if (!unit.page_width || !unit.page_height) return "";
            const dims = markerDimensions(unit);
            const selectedClass = state.selected.has(unit.unit_code) ? "selected" : "";
            return `
              <button
                class="unit-marker ${selectedClass}"
                data-marker="${unit.unit_code}"
                title="${unit.unit_code} • ${Number(unit.total_area_sqft || 0).toLocaleString()} sq.ft"
                style="left:${dims.left}%; top:${dims.top}%; width:${dims.width}%; height:${dims.height}%;"
              ></button>
            `;
          })
          .join("");

        return `
          <article class="page-card" id="page-${page.page}">
            <div class="page-title">
              <div>
                <h3>Page ${page.page}</h3>
                <div class="page-caption">${pageUnits.length} visible unsold units on this page</div>
              </div>
              <span class="badge">${page.rendered_width} × ${page.rendered_height}</span>
            </div>
            <div class="blueprint-wrap">
              <img src="/uploads/${jobId}/${page.image}" alt="Blueprint page ${page.page}" />
              ${markers}
            </div>
          </article>
        `;
      })
      .join("");

    pagesContainer.innerHTML = pagesHtml || `<div class="page-card"><p>No blueprint pages match the current filters.</p></div>`;
    pagesContainer.querySelectorAll("[data-marker]").forEach((marker) => {
      marker.addEventListener("click", () => toggleUnit(marker.dataset.marker));
    });
  }

  function renderSelection() {
    const selectedUnits = dataset.units.filter((u) => state.selected.has(u.unit_code));
    const totalArea = totalSelectedArea();

    selectedAreaEl.textContent = `${totalArea.toLocaleString()} sq.ft`;
    selectionMetaEl.textContent = `${selectedUnits.length} units selected`;
    selectedChipsEl.innerHTML = selectedUnits.length
      ? selectedUnits
          .sort((a, b) => a.unit_code.localeCompare(b.unit_code))
          .map((u) => `<button class="selected-chip" data-chip="${u.unit_code}">${u.unit_code} · ${Number(u.total_area_sqft || 0).toLocaleString()} sq.ft</button>`)
          .join("")
      : `<span class="page-caption">Nothing selected yet.</span>`;

    selectedChipsEl.querySelectorAll("[data-chip]").forEach((chip) => {
      chip.addEventListener("click", () => {
        toggleUnit(chip.dataset.chip);
        scrollToMarker(chip.dataset.chip);
      });
    });
  }

  function renderComparisonTable() {
    if (!state.compareRows.length) {
      comparisonTableBody.innerHTML = `<tr><td colspan="5">No saved selections yet.</td></tr>`;
      return;
    }

    comparisonTableBody.innerHTML = state.compareRows
      .slice()
      .sort((a, b) => (b.updatedAtMs || 0) - (a.updatedAtMs || 0))
      .map((row) => {
        const mine = row.userId === state.userId ? " <span class=\"badge mine\">You</span>" : "";
        return `
          <tr>
            <td>${row.displayName || "Unnamed user"}${mine}</td>
            <td>${Number(row.unitCount || 0).toLocaleString()}</td>
            <td>${Number(row.totalAreaSqft || 0).toLocaleString()} sq.ft</td>
            <td>${row.updatedAtText || "-"}</td>
            <td><button class="secondary-btn compact-btn" data-load-user="${row.docId}">Load</button></td>
          </tr>
        `;
      })
      .join("");

    comparisonTableBody.querySelectorAll("[data-load-user]").forEach((btn) => {
      btn.addEventListener("click", () => loadOtherSelection(btn.dataset.loadUser));
    });
  }

  function render() {
    renderTable();
    renderPages();
    renderSelection();
    renderComparisonTable();
  }

  function setUserName() {
    state.userName = userNameInput.value.trim();
    localStorage.setItem(`blueprint-user-name-${jobId}`, state.userName);
    if (state.userName) {
      setStatus(`Working as ${state.userName}.`, "ok");
    } else {
      setStatus("Enter your name so your saved selection is clearly separated.", "warning");
    }
  }

  async function saveSelection() {
    if (!db) {
      setStatus("Firebase is not configured yet. Add your Firebase keys first.", "warning");
      return;
    }
    if (!currentUserName()) {
      setStatus("Enter your name before saving your selection.", "warning");
      userNameInput.focus();
      return;
    }

    const unitCodes = Array.from(state.selected).sort();
    const payload = {
      jobId,
      userId: state.userId,
      displayName: currentUserName(),
      unitCodes,
      unitCount: unitCodes.length,
      totalAreaSqft: totalSelectedArea(),
      updatedAt: firebase.firestore.FieldValue.serverTimestamp(),
    };

    try {
      await db.collection("blueprintSelections").doc(jobId).collection("userSelections").doc(getUserDocId()).set(payload);
      setStatus(`Saved ${unitCodes.length} units for ${currentUserName()}.`, "ok");
    } catch (error) {
      console.error(error);
      setStatus("Could not save selection to Firebase.", "error");
    }
  }

  async function loadMySavedSelection() {
    if (!db) return;
    if (!currentUserName()) return;

    try {
      const snap = await db.collection("blueprintSelections").doc(jobId).collection("userSelections").doc(getUserDocId()).get();
      if (!snap.exists) return;
      const data = snap.data() || {};
      state.selected = new Set(data.unitCodes || []);
      render();
      setStatus(`Loaded saved selection for ${currentUserName()}.`, "ok");
    } catch (error) {
      console.error(error);
      setStatus("Could not load your saved selection.", "error");
    }
  }

  async function loadOtherSelection(docId) {
    if (!db) return;
    try {
      const snap = await db.collection("blueprintSelections").doc(jobId).collection("userSelections").doc(docId).get();
      if (!snap.exists) return;
      const data = snap.data() || {};
      state.selected = new Set(data.unitCodes || []);
      render();
      setStatus(`Loaded ${data.displayName || "saved"} selection for comparison.`, "ok");
    } catch (error) {
      console.error(error);
      setStatus("Could not load the selected user basket.", "error");
    }
  }

  function subscribeComparison() {
    if (!db) return;
    db.collection("blueprintSelections").doc(jobId).collection("userSelections").onSnapshot(
      (snapshot) => {
        state.compareRows = snapshot.docs.map((doc) => {
          const data = doc.data() || {};
          const updatedAtDate = data.updatedAt && data.updatedAt.toDate ? data.updatedAt.toDate() : null;
          return {
            docId: doc.id,
            userId: data.userId,
            displayName: data.displayName,
            unitCount: data.unitCount,
            totalAreaSqft: data.totalAreaSqft,
            updatedAtMs: updatedAtDate ? updatedAtDate.getTime() : 0,
            updatedAtText: updatedAtDate ? updatedAtDate.toLocaleString() : "Pending sync",
          };
        });
        renderComparisonTable();
      },
      (error) => {
        console.error(error);
        setStatus("Could not subscribe to shared selections.", "error");
      }
    );
  }

  searchInput.addEventListener("input", () => {
    state.search = searchInput.value.trim().toLowerCase();
    render();
  });

  pageFilter.addEventListener("change", () => {
    state.page = pageFilter.value;
    render();
  });

  clearBtn.addEventListener("click", () => {
    state.selected.clear();
    render();
  });

  selectVisibleBtn.addEventListener("click", () => {
    visibleUnits().forEach((unit) => state.selected.add(unit.unit_code));
    render();
  });

  saveNameBtn.addEventListener("click", () => {
    setUserName();
    loadMySavedSelection();
  });

  userNameInput.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      setUserName();
      loadMySavedSelection();
    }
  });

  saveSelectionBtn.addEventListener("click", saveSelection);
  reloadSelectionBtn.addEventListener("click", loadMySavedSelection);

  render();

  if (firebaseReady && db) {
    setStatus(currentUserName() ? `Firebase connected. Working as ${currentUserName()}.` : "Firebase connected. Enter your name to save your basket.", currentUserName() ? "ok" : "warning");
    subscribeComparison();
    if (currentUserName()) {
      loadMySavedSelection();
    }
  } else {
    setStatus("Firebase is not configured yet. The app still works locally, but shared selections are disabled.", "warning");
  }
})();
