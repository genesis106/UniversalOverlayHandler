// =============================================
// Drive Manager — JavaScript Logic
// =============================================

// ---- Tab Switching ----
document.querySelectorAll(".tab").forEach(tab => {
    tab.addEventListener("click", () => {
        document.querySelectorAll(".tab").forEach(t => t.classList.remove("active"));
        document.querySelectorAll(".tab-content").forEach(c => c.classList.remove("active"));
        tab.classList.add("active");
        document.getElementById(tab.dataset.tab + "Tab").classList.add("active");
    });
});


// ---- Toast Notification ----
function showToast(message, isError = false) {
    const existing = document.querySelector(".toast");
    if (existing) existing.remove();

    const toast = document.createElement("div");
    toast.className = "toast" + (isError ? " error" : "");
    toast.textContent = message;
    document.body.appendChild(toast);
    setTimeout(() => toast.remove(), 2500);
}


// ---- Storage Counter ----
async function updateStorageCount() {
    const summary = await getStorageSummary();
    document.getElementById("storageCount").textContent = summary.total + " items";
}


// =============================================
// PROFILE SECTION
// =============================================

// Update field suggestions based on selected category
document.getElementById("addCategory").addEventListener("change", updateSuggestions);

function updateSuggestions() {
    const category = document.getElementById("addCategory").value;
    const datalist = document.getElementById("fieldSuggestions");
    datalist.innerHTML = "";

    const suggestions = FIELD_SUGGESTIONS[category] || [];
    suggestions.forEach(s => {
        const opt = document.createElement("option");
        opt.value = s;
        datalist.appendChild(opt);
    });
}

// Add profile entry
document.getElementById("addProfileBtn").addEventListener("click", async () => {
    const key = document.getElementById("addKey").value.trim();
    const value = document.getElementById("addValue").value.trim();
    const category = document.getElementById("addCategory").value;

    if (!key || !value) {
        showToast("Please fill both field name and value", true);
        return;
    }

    await addProfileEntry(key, value, category);
    document.getElementById("addKey").value = "";
    document.getElementById("addValue").value = "";
    showToast(`✅ "${key}" saved to Drive`);
    renderProfile();
    updateStorageCount();
});

// Allow Enter key to add
document.getElementById("addValue").addEventListener("keydown", (e) => {
    if (e.key === "Enter") document.getElementById("addProfileBtn").click();
});

// Render profile list
async function renderProfile(filter = "all", search = "") {
    const profileList = document.getElementById("profileList");
    let items;

    if (filter === "all") {
        items = await getAllProfile();
    } else {
        items = await getProfileByCategory(filter);
    }

    if (search) {
        const q = search.toLowerCase();
        items = items.filter(i =>
            i.key.toLowerCase().includes(q) || i.value.toLowerCase().includes(q)
        );
    }

    if (items.length === 0) {
        profileList.innerHTML = `
      <div class="empty-state">
        <div class="empty-icon">📋</div>
        <p>No data stored yet. Add your first field above!</p>
      </div>
    `;
        return;
    }

    // Group by category
    const grouped = {};
    items.forEach(item => {
        if (!grouped[item.category]) grouped[item.category] = [];
        grouped[item.category].push(item);
    });

    let html = "";
    for (const [cat, entries] of Object.entries(grouped)) {
        entries.forEach(item => {
            html += `
        <div class="item-card" data-key="${escapeHtml(item.key)}">
          <div class="item-info">
            <div class="item-key">
              <span class="category-tag">${cat}</span>
              ${escapeHtml(item.key)}
            </div>
            <div class="item-value">${escapeHtml(item.value)}</div>
          </div>
          <div class="item-actions">
            <button class="btn-icon profile-action-btn" data-action="edit" data-key="${escapeAttr(item.key)}" title="Edit">✏️</button>
            <button class="btn-icon profile-action-btn" data-action="delete" data-key="${escapeAttr(item.key)}" title="Delete">🗑️</button>
          </div>
        </div>
      `;
        });
    }

    profileList.innerHTML = html;
}

// Filter & search
document.getElementById("categoryFilter").addEventListener("change", () => {
    renderProfile(
        document.getElementById("categoryFilter").value,
        document.getElementById("profileSearch").value
    );
});

document.getElementById("profileSearch").addEventListener("input", () => {
    renderProfile(
        document.getElementById("categoryFilter").value,
        document.getElementById("profileSearch").value
    );
});

// Delete profile
async function removeProfile(key) {
    if (!confirm(`Delete "${key}" from Drive?`)) return;
    await deleteProfileEntry(key);
    showToast(`🗑️ "${key}" deleted`);
    renderProfile(
        document.getElementById("categoryFilter").value,
        document.getElementById("profileSearch").value
    );
    updateStorageCount();
}

// Edit profile — show modal
async function editProfile(key) {
    const item = await getProfileEntry(key);
    if (!item) return;

    document.getElementById("editKey").value = item.key;
    document.getElementById("editValue").value = item.value;
    document.getElementById("editCategory").value = item.category;
    document.getElementById("editModal").classList.remove("hidden");
}

document.getElementById("editSaveBtn").addEventListener("click", async () => {
    const key = document.getElementById("editKey").value;
    const value = document.getElementById("editValue").value.trim();
    const category = document.getElementById("editCategory").value;

    if (!value) {
        showToast("Value cannot be empty", true);
        return;
    }

    await updateProfileEntry(key, value, category);
    document.getElementById("editModal").classList.add("hidden");
    showToast(`✅ "${key}" updated`);
    renderProfile(
        document.getElementById("categoryFilter").value,
        document.getElementById("profileSearch").value
    );
});

document.getElementById("editCancelBtn").addEventListener("click", () => {
    document.getElementById("editModal").classList.add("hidden");
});

// Event Delegation for Profile List Actions
document.getElementById("profileList").addEventListener("click", (e) => {
    const btn = e.target.closest(".profile-action-btn");
    if (!btn) return;
    const action = btn.dataset.action;
    const key = btn.dataset.key;
    if (action === "edit") editProfile(key);
    if (action === "delete") removeProfile(key);
});


// =============================================
// DOCUMENTS SECTION
// =============================================

const docUploadArea = document.getElementById("docUploadArea");
const docFileInput = document.getElementById("docFileInput");

docUploadArea.addEventListener("click", () => docFileInput.click());

docUploadArea.addEventListener("dragover", (e) => {
    e.preventDefault();
    docUploadArea.classList.add("drag-over");
});

docUploadArea.addEventListener("dragleave", () => {
    docUploadArea.classList.remove("drag-over");
});

docUploadArea.addEventListener("drop", (e) => {
    e.preventDefault();
    docUploadArea.classList.remove("drag-over");
    handleDocFiles(e.dataTransfer.files);
});

docFileInput.addEventListener("change", (e) => {
    handleDocFiles(e.target.files);
});

async function handleDocFiles(files) {
    const docType = document.getElementById("docType").value;

    for (const file of files) {
        if (file.size > 10 * 1024 * 1024) {
            showToast(`"${file.name}" is too large (max 10MB)`, true);
            continue;
        }

        const reader = new FileReader();
        reader.onload = async (e) => {
            const base64 = e.target.result.split(",")[1];
            await addDocument(file.name, docType, base64, file.type);
            showToast(`📄 "${file.name}" uploaded`);
            renderDocuments();
            updateStorageCount();
        };
        reader.readAsDataURL(file);
    }
}

async function renderDocuments() {
    const docs = await getDocumentsMeta();
    const list = document.getElementById("documentsList");

    if (docs.length === 0) {
        list.innerHTML = `
      <div class="empty-state">
        <div class="empty-icon">📄</div>
        <p>No documents uploaded yet</p>
      </div>
    `;
        return;
    }

    const docIcons = {
        "resume": "📝",
        "certificate": "🎖️",
        "id_card": "🪪",
        "transcript": "📜",
        "other": "📄"
    };

    list.innerHTML = docs.map(doc => `
    <div class="doc-card">
      <span class="doc-icon">${docIcons[doc.type] || "📄"}</span>
      <div class="doc-info">
        <div class="doc-name">${escapeHtml(doc.name)}</div>
        <div class="doc-meta">${doc.type} • ${formatDate(doc.dateAdded)}</div>
      </div>
      <div class="item-actions">
        <button class="btn-icon doc-action-btn" data-action="download" data-id="${doc.id}" title="Download">⬇️</button>
        <button class="btn-icon doc-action-btn" data-action="delete" data-id="${doc.id}" title="Delete">🗑️</button>
      </div>
    </div>
  `).join("");
}

async function removeDoc(id) {
    if (!confirm("Delete this document?")) return;
    await deleteDocument(id);
    showToast("🗑️ Document deleted");
    renderDocuments();
    updateStorageCount();
}

async function downloadDoc(id) {
    const doc = await getDocumentById(id);
    if (!doc) return;

    const link = document.createElement("a");
    link.href = "data:" + doc.mimeType + ";base64," + doc.content;
    link.download = doc.name;
    link.click();
}

// Event Delegation for Document List Actions
document.getElementById("documentsList").addEventListener("click", (e) => {
    const btn = e.target.closest(".doc-action-btn");
    if (!btn) return;
    const action = btn.dataset.action;
    const id = parseInt(btn.dataset.id, 10);
    if (action === "download") downloadDoc(id);
    if (action === "delete") removeDoc(id);
});


// =============================================
// IMAGES SECTION
// =============================================

const imgUploadArea = document.getElementById("imgUploadArea");
const imgFileInput = document.getElementById("imgFileInput");

imgUploadArea.addEventListener("click", () => imgFileInput.click());

imgUploadArea.addEventListener("dragover", (e) => {
    e.preventDefault();
    imgUploadArea.classList.add("drag-over");
});

imgUploadArea.addEventListener("dragleave", () => {
    imgUploadArea.classList.remove("drag-over");
});

imgUploadArea.addEventListener("drop", (e) => {
    e.preventDefault();
    imgUploadArea.classList.remove("drag-over");
    handleImgFiles(e.dataTransfer.files);
});

imgFileInput.addEventListener("change", (e) => {
    handleImgFiles(e.target.files);
});

async function handleImgFiles(files) {
    for (const file of files) {
        if (file.size > 5 * 1024 * 1024) {
            showToast(`"${file.name}" is too large (max 5MB)`, true);
            continue;
        }

        const reader = new FileReader();
        reader.onload = async (e) => {
            const base64 = e.target.result.split(",")[1];
            await addImage(file.name, base64, file.type);
            showToast(`🖼️ "${file.name}" uploaded`);
            renderImages();
            updateStorageCount();
        };
        reader.readAsDataURL(file);
    }
}

async function renderImages() {
    const imgs = await getAllImages();
    const grid = document.getElementById("imagesList");

    if (imgs.length === 0) {
        grid.innerHTML = `
      <div class="empty-state" style="grid-column: 1/-1">
        <div class="empty-icon">🖼️</div>
        <p>No images uploaded yet</p>
      </div>
    `;
        return;
    }

    grid.innerHTML = imgs.map(img => `
    <div class="image-card">
      <img src="data:${img.mimeType};base64,${img.content}" alt="${escapeHtml(img.name)}">
      <div class="image-info">
        <span class="image-name" title="${escapeHtml(img.name)}">${escapeHtml(img.name)}</span>
        <button class="btn-icon img-action-btn" data-action="delete" data-id="${img.id}" title="Delete">🗑️</button>
      </div>
    </div>
  `).join("");
}

async function removeImg(id) {
    if (!confirm("Delete this image?")) return;
    await deleteImage(id);
    showToast("🗑️ Image deleted");
    renderImages();
    updateStorageCount();
}

// Event Delegation for Image List Actions
document.getElementById("imagesList").addEventListener("click", (e) => {
    const btn = e.target.closest(".img-action-btn");
    if (!btn) return;
    const id = parseInt(btn.dataset.id, 10);
    if (btn.dataset.action === "delete") removeImg(id);
});


// =============================================
// CLEAR ALL
// =============================================

document.getElementById("clearAllBtn").addEventListener("click", async () => {
    if (!confirm("⚠️ This will delete ALL stored data from Drive. Are you sure?")) return;
    await clearAllData();
    showToast("All data cleared");
    renderProfile();
    renderDocuments();
    renderImages();
    updateStorageCount();
});


// =============================================
// UTILITIES
// =============================================

function escapeHtml(str) {
    const div = document.createElement("div");
    div.textContent = str;
    return div.innerHTML;
}

function escapeAttr(str) {
    return str.replace(/'/g, "\\'").replace(/"/g, '\\"');
}

function formatDate(iso) {
    if (!iso) return "";
    const d = new Date(iso);
    return d.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
}


// =============================================
// INIT
// =============================================
(async function init() {
    updateSuggestions();
    await renderProfile();
    await renderDocuments();
    await renderImages();
    await updateStorageCount();
})();
