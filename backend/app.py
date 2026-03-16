from fastapi import FastAPI
from pydantic import BaseModel
import subprocess
import json
from fastapi.middleware.cors import CORSMiddleware
from playwright.async_api import async_playwright
from PIL import Image, ImageDraw, ImageFilter
import io
import base64
from google import genai
from dotenv import load_dotenv
import os
import re

app = FastAPI()

# -----------------------------
# CORS (allow Chrome extension)
# -----------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -----------------------------
# Temporary user input storage
# -----------------------------
USER_INPUT = None

# -----------------------------
# Session storage
# -----------------------------
sessions = {}

# -----------------------------
# Configuration
# -----------------------------
load_dotenv()
GOOGLE_CLOUD_PROJECT = os.getenv("GOOGLE_CLOUD_PROJECT")
GOOGLE_CLOUD_LOCATION = os.getenv("GOOGLE_CLOUD_LOCATION", "us-central1")
MODEL_ID = "gemini-2.0-flash"
MAX_STEPS = 30

# -----------------------------
# Request Models
# -----------------------------
class Task(BaseModel):
    instruction: str
    url: str
    action_type: str
    session_id: str = "default"
    user_data: dict = {}


class UserResponse(BaseModel):
    answer: str
    session_id: str = "default"


# -----------------------------
# Element Collection
# -----------------------------
def detect_category(tag_name, input_type, role):
    if input_type in ["text", "search"]:
        return "text_input"
    elif tag_name == "textarea":
        return "textarea"
    elif input_type == "radio" or role == "radio":
        return "radio"
    elif input_type == "checkbox" or role == "checkbox":
        return "checkbox"
    elif tag_name == "button" or role == "button":
        return "button"
    elif tag_name == "a":
        return "link"
    elif tag_name == "select" or role == "combobox":
        return "dropdown"
    else:
        return "unknown"


def collect_elements(page, action_type):
    collected_data = []
    index = 1

    page.wait_for_load_state("load")
    page.wait_for_timeout(2000)

    if action_type == "CLICK_BUTTON":
        selector = "button, input[type='submit'], input[type='button']"

    elif action_type == "FILL_INPUT":
        selector = "input[type='text'], input[type='search'], textarea"

    elif action_type == "SELECT_DROPDOWN":
        selector = "select, [role='combobox'], .MuiSelect-root"

    elif action_type == "CLICK_LINK":
        selector = "a"

    elif action_type == "SELECT_RADIO":
        selector = "input[type='radio'], [role='radio']"

    elif action_type == "CLICK_INPUT_ALL":
        selector = """
            button,
            a,
            input,
            textarea,
            select,
            [role='button'],
            [role='radio'],
            [role='checkbox'],
            [role='combobox']
        """
    else:
        selector = ""

    elements = page.query_selector_all(selector)

    for element in elements:
        try:
            if not element.is_visible():
                continue

            box = element.bounding_box()
            if not box:
                continue

            if box["width"] < 5 or box["height"] < 5:
                continue

            tag_name = element.evaluate("el => el.tagName.toLowerCase()")
            text = element.evaluate("el => el.innerText || el.textContent || ''").strip()
            placeholder = element.get_attribute("placeholder") or ""
            name = element.get_attribute("name") or ""
            input_type = element.get_attribute("type") or ""
            aria_label = element.get_attribute("aria-label") or ""
            role = element.get_attribute("role") or ""
            element_id_attr = element.get_attribute("id") or ""
            class_attr = element.get_attribute("class") or ""
            value = element.get_attribute("value") or ""

            category = detect_category(tag_name, input_type, role)
            label = text or placeholder or aria_label or name or tag_name

            collected_data.append({
                "id": index,
                "tag": tag_name,
                "label": label,
                "text": text,
                "placeholder": placeholder,
                "name": name,
                "input_type": input_type,
                "aria_label": aria_label,
                "role": role,
                "value": value,
                "element_id_attr": element_id_attr,
                "class_attr": class_attr,
                "box": box
            })

            index += 1

        except Exception:
            continue

    return collected_data


# -----------------------------
# Async Element Collection
# -----------------------------
async def collect_elements_async(page, action_type):
    collected_data = []
    index = 1

    await page.wait_for_load_state("load")
    await page.wait_for_timeout(2000)

    if action_type == "CLICK_BUTTON":
        selector = "button, input[type='submit'], input[type='button']"

    elif action_type == "FILL_INPUT":
        selector = "input[type='text'], input[type='search'], textarea"

    elif action_type == "SELECT_DROPDOWN":
        selector = "select, [role='combobox'], .MuiSelect-root"

    elif action_type == "CLICK_LINK":
        selector = "a"

    elif action_type == "SELECT_RADIO":
        selector = "input[type='radio'], [role='radio']"

    elif action_type == "CLICK_INPUT_ALL":
        selector = """
            button,
            a,
            input,
            textarea,
            select,
            [role='button'],
            [role='radio'],
            [role='checkbox'],
            [role='combobox']
        """
    else:
        selector = ""

    elements = await page.query_selector_all(selector)

    for element in elements:
        try:
            if not await element.is_visible():
                continue

            box = await element.bounding_box()
            if not box:
                continue

            if box["width"] < 5 or box["height"] < 5:
                continue

            tag_name = await element.evaluate("el => el.tagName.toLowerCase()")
            text = (await element.evaluate("el => el.innerText || el.textContent || ''")).strip()
            
            # For inputs, aggressively try to find an associated label or surrounding text (crucial for Google Forms)
            if tag_name in ['input', 'textarea', 'select'] and not text:
                text = (await element.evaluate("""el => {
                    if (el.labels && el.labels.length > 0) return el.labels[0].innerText;
                    let id = el.getAttribute('id');
                    if (id) {
                        let label = document.querySelector('label[for="' + id + '"]');
                        if (label) return label.innerText;
                    }
                    // Google forms specific: look up the tree for the question title container
                    let container = el.closest('[role="listitem"]');
                    if (container) {
                        let title = container.querySelector('[role="heading"]');
                        if (title) return title.innerText;
                    }
                    return '';
                }""")).strip()
                
            placeholder = await element.get_attribute("placeholder") or ""
            name = await element.get_attribute("name") or ""
            input_type = await element.get_attribute("type") or ""
            aria_label = await element.get_attribute("aria-label") or ""
            role = await element.get_attribute("role") or ""
            element_id_attr = await element.get_attribute("id") or ""
            class_attr = await element.get_attribute("class") or ""
            value = await element.get_attribute("value") or ""

            category = detect_category(tag_name, input_type, role)
            label = aria_label or text or placeholder or name or tag_name

            collected_data.append({
                "id": index,
                "tag": tag_name,
                "label": label,
                "text": text,
                "placeholder": placeholder,
                "name": name,
                "input_type": input_type,
                "aria_label": aria_label,
                "role": role,
                "value": value,
                "element_id_attr": element_id_attr,
                "class_attr": class_attr,
                "box": box
            })

            index += 1

        except Exception:
            continue

    return collected_data


# -----------------------------
# Async Execute Action
# -----------------------------
async def execute_action_async(page, action, elements):
    act = action.get("action")

    if act == "click":
        el = next((e for e in elements if e["id"] == action["element_id"]), None)

        if not el:
            return False

        box = el["box"]

        await page.mouse.click(
            box["x"] + box["width"]/2,
            box["y"] + box["height"]/2
        )

        await page.wait_for_timeout(1500)
        return True

    elif act == "type":
        el = next((e for e in elements if e["id"] == action["element_id"]), None)

        if not el:
            return False

        box = el["box"]

        await page.mouse.click(
            box["x"] + box["width"]/2,
            box["y"] + box["height"]/2
        )

        await page.keyboard.type(action.get("text",""))

        return True

    elif act == "clear_and_type":
        el = next((e for e in elements if e["id"] == action["element_id"]), None)

        if not el:
            return False

        box = el["box"]

        await page.mouse.click(
            box["x"] + box["width"]/2,
            box["y"] + box["height"]/2
        )

        await page.keyboard.press("Control+A")
        await page.keyboard.press("Backspace")
        await page.keyboard.type(action.get("text",""))

        return True

    elif act == "upload_file":
        el = next((e for e in elements if e["id"] == action["element_id"]), None)

        if not el:
            return False
            
        filename = action.get("filename")
        if not filename:
             return False
             
        # We need the base64 content from user_data
        user_data = page.context.user_data_cache if hasattr(page.context, 'user_data_cache') else {}
        doc = None
        
        # Search in documents first
        if "documents" in user_data:
            doc = next((d for d in user_data["documents"] if d["name"] == filename), None)
            
        # If not found, search in images
        if not doc and "images" in user_data:
            doc = next((i for i in user_data["images"] if i["name"] == filename), None)
            
        if not doc:
             print(f"File {filename} not found in USER_DATA (checked documents and images)")
             return False
             
        import base64
        file_buffer = base64.b64decode(doc["content"])
        
        file_payload = {
            "name": doc["name"],
            "mimeType": doc["mimeType"],
            "buffer": file_buffer
        }
        
        # 1. Click the element first (which is the "Add file" button) to open the iframe
        box = el["box"]
        await page.mouse.click(
            box["x"] + box["width"]/2,
            box["y"] + box["height"]/2
        )
        
        # 2. Wait for the iframe to pop up and settle
        await page.wait_for_timeout(2000)
        
        # 3. Google Forms opens a cross-origin Google Drive iframe.
        #    We must scan all frames for an input[type='file'].
        print(f"File upload requested for {filename}, injecting into iframe picker...")
        uploaded = False
        
        for frame in page.frames:
            try:
                # This could fail if the frame is completely isolated, but often Chrome extensions
                # or Playwright can pierce it if --disable-web-security isn't needed or if it's accessible.
                inputs = await frame.locator("input[type='file']").count()
                if inputs > 0:
                    await frame.locator("input[type='file']").first.set_input_files([file_payload])
                    uploaded = True
                    print(f"Successfully injected file {filename} into an iframe.")
                    break
            except Exception as e:
                continue
                
        if not uploaded:
            # Fallback for standard forms that just hide the input on the main page
            try:
                await page.locator("input[type='file']").first.set_input_files([file_payload])
                print(f"Successfully injected file {filename} into main page.")
            except Exception as e:
                print("Failed to upload file to any frame or main page:", e)
                return False

        await page.wait_for_timeout(2000)
        return True

    elif act == "scroll":
        delta = 500 if action.get("direction") == "down" else -500
        await page.mouse.wheel(0, delta)

        return True

    elif act == "key":
        await page.keyboard.press(action.get("key","Enter"))

        return True

    elif act == "wait":
        await page.wait_for_timeout(int(action.get("seconds",2)*1000))

        return True

    elif act == "go_back":
        await page.go_back()
        return True

    elif act in ["ask_user","done"]:
        return True

    return False


# -----------------------------
# Draw Boxes
# -----------------------------
def get_color(category):
    color_map = {
        "button": "green",
        "text_input": "orange",
        "textarea": "orange",
        "dropdown": "purple",
        "link": "blue",
        "radio": "red",
        "checkbox": "pink",
        "unknown": "gray"
    }
    return color_map.get(category, "black")


def draw_boxes(image, elements):
    draw = ImageDraw.Draw(image)

    for item in elements:
        box = item["box"]

        x1 = int(box["x"])
        y1 = int(box["y"])
        x2 = int(box["x"] + box["width"])
        y2 = int(box["y"] + box["height"])

        box_color = get_color(item.get("category"))

        if item.get("input_type") == "password":
            cropped = image.crop((x1, y1, x2, y2))
            blurred = cropped.filter(ImageFilter.GaussianBlur(15))
            image.paste(blurred, (x1, y1))
        else:
            draw.rectangle(
                [(x1, y1), (x2, y2)],
                outline=box_color,
                width=3
            )
            draw.text((x1, y1 - 12), str(item["id"]), fill=box_color)

    return image


# -----------------------------
# Gemini Client
# -----------------------------
def get_gemini_client():
    if not GOOGLE_CLOUD_PROJECT:
        print("❌ GOOGLE_CLOUD_PROJECT not found in .env")
        return None

    print(f"🔐 Vertex AI — Project: {GOOGLE_CLOUD_PROJECT}")

    return genai.Client(
        vertexai=True,
        project=GOOGLE_CLOUD_PROJECT,
        location=GOOGLE_CLOUD_LOCATION,
    )


# -----------------------------
# Element Summary
# -----------------------------
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


# -----------------------------
# System Prompt
# -----------------------------
SYSTEM_PROMPT = """You are a PRECISE UI Navigator Agent controlling a real web browser via Playwright.

You see an annotated screenshot with numbered elements.

Complete the user's goal step-by-step.

Respond with EXACTLY ONE JSON object.

Available actions:

{"action": "click", "element_id": 5}
{"action": "type", "element_id": 3, "text": "shoes"}
{"action": "clear_and_type", "element_id": 3, "text": "shoes"}
{"action": "upload_file", "element_id": 7, "filename": "resume.pdf"}
{"action": "scroll", "direction": "down"}
{"action": "scroll", "direction": "up"}
{"action": "key", "key": "Enter"}
{"action": "wait", "seconds": 2}
{"action": "ask_user", "question": "..."}
{"action": "done", "summary": "..."}
{"action": "go_back"}

Rules:
1. You will be provided with a LOCAL DRIVE (USER_DATA) containing the user's personal information, documents, and images.
2. ALWAYS check USER_DATA first! Use SEMANTIC MATCHING to map form fields to USER_DATA keys. If the USER_DATA key has typos or slight variations (e.g., "Far's Name" = "Father's Name", "Mother Name" = "Mother's Name"), YOU MUST STILL USE THAT DATA directly in a `type` or `upload_file` action!
3. STRICT ANTI-HALLUCINATION RULE: If the needed data is COMPLETELY MISSING from USER_DATA, you MUST use `ask_user` to request it. 
4. NEVER GUESS or make up ANY personal information or fake file names. If a semantic match is not available, you MUST output `ask_user`.
5. Be specific about the field name in your `ask_user` question so the system can save it to the DB (e.g. "What is your Father's Name?").
6. STRICT DONE RULE: Do NOT use the `done` action early. Keep filling out the form until there is a submit button, click the submit button, wait for the page to load, and ONLY call `done` when you see a clear form submission confirmation or success message.
7. If popup appears, close it.
8. If element not visible, scroll to make it visible.
9. Scroll if needed to find more elements.
"""


# -----------------------------
# Ask Gemini
# -----------------------------
def ask_gemini(client, screenshot_b64, elements, goal, history, user_input=None, user_data=None):
    el_text = element_summary(elements)

    hist_text = ""
    if history:
        hist_text = "\nACTION HISTORY:\n"

        for h in history[-10:]:
            hist_text += json.dumps(h) + "\n"

    user_info = ""
    if user_input:
        user_info = f"\nUSER PROVIDED INFO: {user_input}\n"
        
    drive_info = ""
    if user_data and isinstance(user_data, dict):
        drive_info = "\n--- LOCAL DRIVE (USER_DATA) ---\n"
        
        # Format profile data simply
        if "profile" in user_data and isinstance(user_data["profile"], list):
            drive_info += "Profile Information:\n"
            for item in user_data["profile"]:
                if "key" in item and "value" in item:
                    drive_info += f"- {item['key']}: {item['value']}\n"
                    
        # Format documents
        if "documents" in user_data and isinstance(user_data["documents"], list):
            drive_info += "\nAvailable Documents (use exact filename in upload_file action):\n"
            for item in user_data["documents"]:
                if "name" in item:
                    drive_info += f"- {item['name']}\n"
                    
        # Format images
        if "images" in user_data and isinstance(user_data["images"], list):
            drive_info += "\nAvailable Images:\n"
            for item in user_data["images"]:
                if "name" in item:
                    drive_info += f"- {item['name']}\n"
                    
        drive_info += "-------------------------------\n"

    prompt = f"""
USER GOAL: {goal}

{drive_info}

VISIBLE ELEMENTS:
{el_text}

{user_info}
{hist_text}

CRITICAL: Before typing ANY personal data, verify it exists in LOCAL DRIVE or USER PROVIDED INFO. If it does not exist, you MUST return {{"action": "ask_user"}}.
CRITICAL: Do not return "done" unless the form has been successfully submitted and a confirmation page is visible.

What is the SINGLE next action?
Return ONLY JSON.
"""

    image_part = genai.types.Part.from_bytes(
        data=base64.b64decode(screenshot_b64),
        mime_type="image/png",
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


# -----------------------------
# Execute Action (Sync - Unused)
# -----------------------------
def execute_action(page, action, elements):
    # This function is not used but kept for reference
    pass


# -----------------------------
# Start Playwright Agent
# -----------------------------
@app.post("/run-agent")
async def run_agent(task: Task):
    session_id = task.session_id
    action_type = task.action_type
    goal = task.instruction
    user_data = task.user_data
    history = []
    if session_id not in sessions:
        p = await async_playwright().start()
        
        import glob
        user_data_dir = os.path.join(os.getcwd(), "chrome_profile")
        for lock_file in glob.glob(os.path.join(user_data_dir, "Singleton*")):
            try:
                os.remove(lock_file)
            except Exception:
                pass
                
        browser = await p.chromium.launch_persistent_context(
            user_data_dir=user_data_dir,
            headless=False,
            channel="chrome",
            args=["--disable-blink-features=AutomationControlled"]
        )
        
        # Store user data on the context so execute_action can access it for files
        browser.user_data_cache = user_data
        
        page = browser.pages[0] if browser.pages else await browser.new_page()
        await page.goto(task.url)
        sessions[session_id] = {
            "p": p,
            "browser": browser,
            "page": page,
            "history": [],
            "goal": task.instruction,
            "action_type": task.action_type,
            "user_data": user_data
        }
    else:
        page = sessions[session_id]["page"]
        history = sessions[session_id]["history"]
        goal = sessions[session_id]["goal"]
        action_type = sessions[session_id]["action_type"]

    client = get_gemini_client()
    if not client:
        return {"status": "error", "message": "Gemini client not initialized"}

    for step in range(MAX_STEPS):
        elements = await collect_elements_async(page, action_type)
        if len(elements) == 0:
            # Scroll down to find more elements
            await page.mouse.wheel(0, 500)
            await page.wait_for_timeout(1000)
            elements = await collect_elements_async(page, action_type)
        screenshot_bytes = await page.screenshot(full_page=False)
        img = Image.open(io.BytesIO(screenshot_bytes))
        processed_img = draw_boxes(img, elements)
        buffered = io.BytesIO()
        processed_img.save(buffered, format="PNG")
        screenshot_b64 = base64.b64encode(buffered.getvalue()).decode()

        action = ask_gemini(
            client, 
            screenshot_b64, 
            elements, 
            goal, 
            history, 
            sessions[session_id].get("user_input"),
            sessions[session_id].get("user_data")
        )
        if "user_input" in sessions[session_id]:
            del sessions[session_id]["user_input"]

        if action.get("action") == "done":
            history.append(action)
            # Clean up session
            await sessions[session_id]["browser"].close()
            await sessions[session_id]["p"].stop()
            del sessions[session_id]
            return {"status": "done", "summary": action.get("summary")}

        if action.get("action") == "ask_user":
            history.append(action)
            sessions[session_id]["history"] = history
            return {"status": "ask_user", "question": action.get("question")}

        await execute_action_async(page, action, elements)
        history.append(action)

    # Clean up if max steps
    await sessions[session_id]["browser"].close()
    sessions[session_id]["p"].stop()
    del sessions[session_id]
    return {"status": "done", "summary": "Max steps reached"}


# -----------------------------
# Receive answer from extension
# -----------------------------
@app.post("/user-response")
def user_response(resp: UserResponse):
    session_id = resp.session_id
    if session_id in sessions:
        sessions[session_id]["user_input"] = resp.answer
    return {"status": "received"}


# -----------------------------
# Agent fetches answer
# -----------------------------
@app.get("/get-user-response")
def get_user_response():
    global USER_INPUT

    if USER_INPUT:
        answer = USER_INPUT
        USER_INPUT = None

        return {
            "status": "answered",
            "answer": answer
        }

    return {
        "status": "waiting",
        "answer": None
    }