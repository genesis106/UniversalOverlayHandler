// Run agent when button clicked
document.getElementById("runBtn").addEventListener("click", runAgent)

let currentSessionId = null

async function runAgent() {

  const instruction = document.getElementById("instruction").value
  const url = document.getElementById("url").value

  if (!currentSessionId) {
    currentSessionId = Date.now().toString()
  }

  const status = document.getElementById("status")
  status.innerText = "Running AI agent..."

  const res = await fetch("http://127.0.0.1:8000/run-agent", {
    method: "POST",
    headers: {
      "Content-Type": "application/json"
    },
    body: JSON.stringify({
      instruction: instruction,
      url: url,
      action_type: "CLICK_INPUT_ALL",
      session_id: currentSessionId
    })
  })

  const data = await res.json()

  // If Gemini needs input
  if(data.status === "ask_user"){
      showUserQuestion(data.question)
  } 
  else {
      status.innerText = "Task completed"
      currentSessionId = null // Reset for next run
  }
}


function showUserQuestion(question){

  const container = document.getElementById("userInputContainer")

  container.innerHTML = `
      <p>${question}</p>
      <input id="userAnswer" placeholder="Type answer"/>
      <button id="submitAnswer">Submit</button>
  `

  document
    .getElementById("submitAnswer")
    .addEventListener("click", sendAnswer)
}


async function sendAnswer(){

  const answer = document.getElementById("userAnswer").value

  const status = document.getElementById("status")
  status.innerText = "Sending answer..."

  await fetch("http://127.0.0.1:8000/user-response",{
      method:"POST",
      headers:{
        "Content-Type":"application/json"
      },
      body:JSON.stringify({
        answer:answer,
        session_id: currentSessionId
      })
  })

  status.innerText = "Answer submitted. Agent continuing..."

  // Continue the agent
  runAgent()
}