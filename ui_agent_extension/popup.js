// =============================================
// UI Navigator Popup — Logic
// =============================================

let currentSessionId = null;
let lastQuestion = null;

// ── Init Drive info ──
async function initDrive() {
  const summary = await getStorageSummary();
  document.getElementById("storageInfo").textContent = summary.total;
}
initDrive();

// ── Open Drive Tab ──
document.getElementById("driveBtn").addEventListener("click", () => {
  chrome.tabs.create({ url: chrome.runtime.getURL("drive.html") });
});

// ── Detect active tab URL ──
chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
  if (tabs && tabs[0]) {
    const url = tabs[0].url;
    const urlInput = document.getElementById("url");
    const urlDisplay = document.getElementById("urlDisplay");
    const urlDot = document.getElementById("urlDot");

    // Show detected URL
    try {
      const parsed = new URL(url);
      urlDisplay.innerHTML = `<b>${parsed.hostname}</b>${parsed.pathname !== "/" ? parsed.pathname : ""}`;
    } catch {
      urlDisplay.textContent = url;
    }

    urlDot.classList.remove("idle");

    // Auto-fill URL field if empty
    if (!urlInput.value) {
      urlInput.value = url;
    }
  }
});

// ── Run Agent ──
document.getElementById("runBtn").addEventListener("click", runAgent);

async function runAgent() {
  const instruction = document.getElementById("instruction").value.trim();
  const urlField = document.getElementById("url").value.trim();

  if (!instruction) {
    setStatus("Please enter a task instruction", "error");
    return;
  }

  // Fallback: get active tab URL if not set
  let url = urlField;
  if (!url) {
    url = await getActiveTabUrl();
  }

  if (!currentSessionId) {
    currentSessionId = Date.now().toString();
  }

  setRunning(true);
  setStatus("Starting agent…");

  const profileData = await getProfileCategorized();
  const documents = await getAllDocuments();
  const images = await getAllImages();

  const userDataPayload = {
    profile: profileData,
    documents: documents.map(d => ({ name: d.name, type: d.type, mimeType: d.mimeType, content: d.content })),
    images: images.map(i => ({ name: i.name, mimeType: i.mimeType, content: i.content }))
  };

  try {
    const res = await fetch("http://127.0.0.1:8000/run-agent", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        instruction,
        url,
        action_type: "CLICK_INPUT_ALL",
        session_id: currentSessionId,
        user_data: userDataPayload
      })
    });

    const data = await res.json();

    if (data.status === "ask_user") {
      lastQuestion = data.question;
      setStatus("Agent is asking for input…");
      addAgentMessage(data.question);
      showQuestionBox();
      setRunning(false);
    } else if (data.status === "done") {
      setStatus("✅ Task completed!" + (data.summary ? " " + data.summary : ""), "success");
      addAgentMessage("✅ Task completed!" + (data.summary ? "\n" + data.summary : ""));
      currentSessionId = null;
      setRunning(false);
    } else {
      setStatus("Unexpected response from agent", "error");
      setRunning(false);
    }
  } catch (err) {
    setStatus("Cannot connect to agent server (127.0.0.1:8000)", "error");
    setRunning(false);
  }
}

// ── Submit Answer ──
document.getElementById("submitAnswer").addEventListener("click", sendAnswer);
document.getElementById("userAnswer").addEventListener("keydown", (e) => {
  if (e.key === "Enter") sendAnswer();
});

async function sendAnswer() {
  const answer = document.getElementById("userAnswer").value.trim();
  if (!answer) return;

  const saveToDrive = document.getElementById("saveToDrive").checked;

  // Show user's answer as chat bubble
  addUserMessage(answer);
  hideQuestionBox();

  // Save to drive if requested
  if (saveToDrive && lastQuestion && answer) {
    let fieldName = lastQuestion
      .replace(/what is|please enter|enter your|your|the/gi, "")
      .replace(/[?.,]/g, "")
      .trim();
    if (!fieldName || fieldName.length > 50) {
      fieldName = "Saved Field " + Date.now().toString().slice(-4);
    }
    await addProfileEntry(fieldName, answer, "other");
    initDrive();
  }

  setStatus("Sending answer to agent…");
  setRunning(true);

  try {
    await fetch("http://127.0.0.1:8000/user-response", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ answer, session_id: currentSessionId })
    });

    document.getElementById("userAnswer").value = "";
    setStatus("Agent continuing…");
    runAgent();
  } catch (err) {
    setStatus("Failed to send answer", "error");
    setRunning(false);
  }
}

// ── UI Helpers ──

function setRunning(running) {
  const btn = document.getElementById("runBtn");
  btn.disabled = running;
  btn.innerHTML = running
    ? `<span class="spinner"></span> Running…`
    : `<span>▶</span> Run Agent`;
}

function setStatus(msg, type = "info") {
  const bar = document.getElementById("statusBar");
  const text = document.getElementById("statusText");
  bar.className = "status-bar visible";
  if (type === "error") bar.classList.add("error");
  if (type === "success") bar.classList.add("success");

  const icons = { info: "⚡", error: "⚠️", success: "✅" };
  bar.querySelector(".status-icon").textContent = icons[type] || "⚡";
  text.textContent = msg;
}

function addAgentMessage(text) {
  removeChatEmpty();
  const panel = document.getElementById("chatPanel");
  const msg = document.createElement("div");
  msg.className = "msg agent";
  msg.innerHTML = `
    <div class="msg-label">🤖 Agent</div>
    <div class="msg-bubble">${escapeHtml(text)}</div>
  `;
  panel.appendChild(msg);
  panel.scrollTop = panel.scrollHeight;
}

function addUserMessage(text) {
  removeChatEmpty();
  const panel = document.getElementById("chatPanel");
  const msg = document.createElement("div");
  msg.className = "msg user";
  msg.innerHTML = `
    <div class="msg-label">You</div>
    <div class="msg-bubble">${escapeHtml(text)}</div>
  `;
  panel.appendChild(msg);
  panel.scrollTop = panel.scrollHeight;
}

function removeChatEmpty() {
  const empty = document.getElementById("chatEmpty");
  if (empty) empty.remove();
}

function showQuestionBox() {
  const box = document.getElementById("questionBox");
  box.classList.remove("hidden");
  document.getElementById("userAnswer").focus();
}

function hideQuestionBox() {
  document.getElementById("questionBox").classList.add("hidden");
}

function escapeHtml(str) {
  const d = document.createElement("div");
  d.textContent = str;
  return d.innerHTML;
}

async function getActiveTabUrl() {
  return new Promise((resolve) => {
    chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
      resolve(tabs && tabs[0] ? tabs[0].url : "");
    });
  });
}
