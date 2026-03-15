"""
Universal Overlay Navigator — AI-Powered Autonomous UI Agent
Uses Playwright for browser control + Gemini 2.0 Flash (Vertex AI) for reasoning.

IMPORTANT CHANGE:
Screenshot + elements now come from playwright_runner.py
"""

from playwright.sync_api import sync_playwright
from google import genai
from dotenv import load_dotenv
import json
import base64
import os
import sys
import re

# ================================
# CONFIGURATION
# ================================

load_dotenv()

GOOGLE_CLOUD_PROJECT = os.getenv("GOOGLE_CLOUD_PROJECT")
GOOGLE_CLOUD_LOCATION = os.getenv("GOOGLE_CLOUD_LOCATION", "us-central1")
MODEL_ID = "gemini-2.0-flash"

MAX_STEPS = 30


# ================================
# GEMINI CLIENT
# ================================

def get_gemini_client():
    if not GOOGLE_CLOUD_PROJECT:
        print("❌ GOOGLE_CLOUD_PROJECT not found in .env")
        sys.exit(1)

    print(f"🔐 Vertex AI — Project: {GOOGLE_CLOUD_PROJECT}")

    return genai.Client(
        vertexai=True,
        project=GOOGLE_CLOUD_PROJECT,
        location=GOOGLE_CLOUD_LOCATION,
    )


# ================================
# ELEMENT SUMMARY FOR PROMPT
# ================================

def element_summary(elements):
    lines = []

    for el in elements:

        line = f"[{el['id']}] <{el['tag']}> {el.get('label','')}"

        if el.get("type"):
            line += f" type={el['type']}"

        if el.get("href"):
            line += f" href={el['href'][:50]}"

        lines.append(line)

    return "\n".join(lines)


# ================================
# SYSTEM PROMPT
# ================================

SYSTEM_PROMPT = """You are a PRECISE UI Navigator Agent controlling a real web browser via Playwright.

You see an annotated screenshot with numbered elements.

Complete the user's goal step-by-step.

Respond with EXACTLY ONE JSON object.

Available actions:

{"action": "click", "element_id": 5}
{"action": "type", "element_id": 3, "text": "shoes"}
{"action": "clear_and_type", "element_id": 3, "text": "shoes"}
{"action": "scroll", "direction": "down"}
{"action": "scroll", "direction": "up"}
{"action": "key", "key": "Enter"}
{"action": "wait", "seconds": 2}
{"action": "ask_user", "question": "..."}
{"action": "done", "summary": "..."}
{"action": "go_back"}

Rules:
- Use ask_user if you need information
- Do NOT stop early
- If popup appears close it
- If element not visible scroll
"""


# ================================
# ASK GEMINI
# ================================

def ask_gemini(client, screenshot_b64, elements, goal, history):

    el_text = element_summary(elements)

    hist_text = ""
    if history:
        hist_text = "\nACTION HISTORY:\n"

        for h in history[-10:]:
            hist_text += json.dumps(h) + "\n"

    prompt = f"""
USER GOAL: {goal}

VISIBLE ELEMENTS:
{el_text}

{hist_text}

What is the SINGLE next action?
Return ONLY JSON.
"""

    image_part = genai.types.Part.from_bytes(
        data=base64.b64decode(screenshot_b64),
        mime_type="image/jpeg",
    )

    try:
        resp = client.models.generate_content(
            model=MODEL_ID,
            contents=[
                genai.types.Content(
                    role="user",
                    parts=[
                        image_part,
                        genai.types.Part.from_text(text=prompt)
                    ],
                )
            ],
            config=genai.types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
                temperature=0.1,
                max_output_tokens=400,
            ),
        )

    except Exception as e:
        print("Gemini error:", e)
        return {"action": "wait", "seconds": 2}

    raw = resp.text.strip()

    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?", "", raw)
        raw = re.sub(r"```$", "", raw)

    try:
        return json.loads(raw)

    except:
        print("Invalid JSON:", raw)
        return {"action": "wait", "seconds": 1}


# ================================
# EXECUTE ACTION
# ================================

def execute_action(page, action, elements):

    act = action.get("action")

    if act == "click":

        el = next((e for e in elements if e["id"] == action["element_id"]), None)

        if not el:
            return False

        box = el["box"]

        page.mouse.click(
            box["x"] + box["width"]/2,
            box["y"] + box["height"]/2
        )

        page.wait_for_timeout(1500)
        return True


    elif act == "type":

        el = next((e for e in elements if e["id"] == action["element_id"]), None)

        if not el:
            return False

        box = el["box"]

        page.mouse.click(
            box["x"] + box["width"]/2,
            box["y"] + box["height"]/2
        )

        page.keyboard.type(action.get("text",""), delay=40)

        return True


    elif act == "clear_and_type":

        el = next((e for e in elements if e["id"] == action["element_id"]), None)

        if not el:
            return False

        box = el["box"]

        page.mouse.click(
            box["x"] + box["width"]/2,
            box["y"] + box["height"]/2
        )

        page.keyboard.press("Control+A")
        page.keyboard.type(action.get("text",""), delay=40)

        return True


    elif act == "scroll":

        delta = 500 if action.get("direction") == "down" else -500
        page.mouse.wheel(0, delta)

        return True


    elif act == "key":

        page.keyboard.press(action.get("key","Enter"))

        return True


    elif act == "wait":

        page.wait_for_timeout(int(action.get("seconds",2)*1000))

        return True


    elif act == "go_back":

        page.go_back()
        return True


    elif act in ["ask_user","done"]:
        return True

    return False


# ================================
# AGENT LOOP
# ================================

def run_agent(page, goal):

    client = get_gemini_client()

    history = []

    for step in range(MAX_STEPS):

        print(f"\nSTEP {step+1}")

        # ================================
        # RECEIVE RUNNER PAYLOAD
        # ================================

        print("Waiting for screenshot + elements from runner...")

        try:

            payload = json.loads(input("RUNNER_JSON: "))

            screenshot_b64 = payload["screenshot"]

            elements = payload["elements"]

        except Exception as e:

            print("Invalid runner payload:", e)
            break


        # ================================
        # GEMINI THINK
        # ================================

        action = ask_gemini(
            client,
            screenshot_b64,
            elements,
            goal,
            history
        )

        print("Action:", action)

        act_type = action.get("action")


        # ================================
        # DONE
        # ================================

        if act_type == "done":

            print("Task Complete:", action.get("summary"))
            break


        # ================================
        # ASK USER
        # ================================

        if act_type == "ask_user":

            question = action.get("question","")

            print("\nAGENT:", question)

            # user_input = input("YOU: ")
            # if act_type == "ask_user":

            return {
                "status": "ask_user",
                "question": question
            }


        # ================================
        # EXECUTE ACTION
        # ================================

        ok = execute_action(page, action, elements)

        print("Executed:", ok)

        history.append(action)


# ================================
# MAIN
# ================================

def main():

    print("Universal Overlay Navigator")

    url = input("URL: ")

    if not url.startswith("http"):
        url = "https://" + url

    goal = input("Goal: ")

    with sync_playwright() as p:

        browser = p.chromium.launch(headless=False)

        ctx = browser.new_context()

        page = ctx.new_page()

        page.goto(url)

        run_agent(page, goal)

        input("Press Enter to exit")


if __name__ == "__main__":
    main()