// Initialize Drive UI
document.getElementById("driveBtn").addEventListener("click", () => {
  chrome.tabs.create({ url: chrome.runtime.getURL("drive.html") });
});

async function initDrive() {
  const summary = await getStorageSummary();
  document.getElementById("storageInfo").innerText = `Drive: ${summary.total} items`;
}
initDrive();

// Run agent when button clicked
document.getElementById("runBtn").addEventListener("click", runAgent)

let currentSessionId = null
let lastQuestion = null

async function runAgent() {

  const instruction = document.getElementById("instruction").value
  const url = document.getElementById("url").value

  if (!currentSessionId) {
    currentSessionId = Date.now().toString()
  }

  const status = document.getElementById("status")
  status.innerText = "Running AI agent..."

  // Fetch local profile data to send with request
  const profileData = await getProfileCategorized()

  // Fetch files so the agent knows what exists
  const documents = await getAllDocuments()
  const images = await getAllImages()

  // Make a combined structure
  const userDataPayload = {
    profile: profileData,
    documents: documents.map(d => ({ name: d.name, type: d.type, mimeType: d.mimeType, content: d.content })),
    images: images.map(i => ({ name: i.name, mimeType: i.mimeType, content: i.content }))
  }

  const res = await fetch("http://127.0.0.1:8000/run-agent", {
    method: "POST",
    headers: {
      "Content-Type": "application/json"
    },
    body: JSON.stringify({
      instruction: instruction,
      url: url,
      action_type: "CLICK_INPUT_ALL",
      session_id: currentSessionId,
      user_data: userDataPayload
    })
  })

  const data = await res.json()

  // If Gemini needs input
  if (data.status === "ask_user") {
    lastQuestion = data.question;
    showUserQuestion(data.question)
  }
  else {
    status.innerText = "Task completed"
    currentSessionId = null // Reset for next run
  }
}


function showUserQuestion(question) {

  const container = document.getElementById("userInputContainer")

  container.innerHTML = `
      <p style="font-weight:bold">${question}</p>
      <input id="userAnswer" placeholder="Type answer" style="width:100%; margin:5px 0; padding:5px;"/>
      <div style="margin:5px 0; display:flex; align-items:center; gap:5px; font-size:13px;">
         <input type="checkbox" id="saveToDrive" checked>
         <label for="saveToDrive">Save to Drive for next time</label>
      </div>
      <button id="submitAnswer">Submit</button>
  `

  document
    .getElementById("submitAnswer")
    .addEventListener("click", sendAnswer)
}


async function sendAnswer() {

  const answer = document.getElementById("userAnswer").value
  const saveToDrive = document.getElementById("saveToDrive").checked

  const status = document.getElementById("status")
  status.innerText = "Sending answer..."

  // Automatically save to Drive if checked
  if (saveToDrive && lastQuestion && answer) {
    // Very basic natural language extraction attempt to get a reasonable field name
    // e.g. "What is your mother's name?" -> "mother's name"
    let fieldName = lastQuestion.replace(/what is|please enter|enter your|your|the/gi, "").replace(/[?.,]/g, "").trim();
    if (!fieldName || fieldName.length > 30) fieldName = "Saved Field " + Date.now().toString().slice(-4);

    await addProfileEntry(fieldName, answer, "other");
    initDrive(); // Update count
  }

  await fetch("http://127.0.0.1:8000/user-response", {
    method: "POST",
    headers: {
      "Content-Type": "application/json"
    },
    body: JSON.stringify({
      answer: answer,
      session_id: currentSessionId
    })
  })

  status.innerText = "Answer submitted. Agent continuing..."

  // Clear question container
  document.getElementById("userInputContainer").innerHTML = "";

  // Continue the agent
  runAgent()
}