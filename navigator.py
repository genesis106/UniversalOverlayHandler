"""
Universal Overlay Navigator — AI-Powered Autonomous UI Agent
Uses Playwright for browser control + Gemini 2.0 Flash (Vertex AI) for visual reasoning.
Works on ANY website. Completes FULL end-to-end tasks with user-in-the-loop.

Usage:
    python navigator.py
"""

from playwright.sync_api import sync_playwright
from PIL import Image, ImageDraw, ImageFilter
from google import genai
from dotenv import load_dotenv
import io
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
VIEWPORT_WIDTH = 1280
VIEWPORT_HEIGHT = 800
MAX_ELEMENTS = 50


# ================================
# GEMINI CLIENT
# ================================

def get_gemini_client():
    """Initialize Gemini client via Vertex AI."""
    if not GOOGLE_CLOUD_PROJECT:
        print("❌ GOOGLE_CLOUD_PROJECT not found in .env")
        print("   Fix: Add GOOGLE_CLOUD_PROJECT=your-project-id to .env")
        sys.exit(1)
    print(f"🔐 Vertex AI — Project: {GOOGLE_CLOUD_PROJECT}, Location: {GOOGLE_CLOUD_LOCATION}")
    return genai.Client(
        vertexai=True,
        project=GOOGLE_CLOUD_PROJECT,
        location=GOOGLE_CLOUD_LOCATION,
    )


# ================================
# ELEMENT COLLECTION
# ================================

INTERACTIVE_SELECTORS = [
    "input[type='text']", "input[type='search']", "input[type='email']",
    "input[type='password']", "input[type='number']", "input[type='tel']",
    "input[type='submit']", "input[type='button']", "input[type='checkbox']",
    "input[type='radio']",
    "textarea", "select", "button",
    "[role='combobox']", "[role='button']", "[role='tab']",
    "[role='menuitem']", "[role='checkbox']", "[role='radio']",
    "[role='switch']", "[role='option']",
    "a[href]", "[role='link']",
    "[onclick]", "[contenteditable='true']",
]

HIGH_PRIORITY_TAGS = {"input", "textarea", "select", "button"}


def collect_elements(page):
    """Collect all visible interactive elements in the current viewport."""
    collected = []
    index = 1
    seen_boxes = set()

    page.wait_for_load_state("domcontentloaded")
    page.wait_for_timeout(1500)

    for selector in INTERACTIVE_SELECTORS:
        try:
            elements = page.query_selector_all(selector)
        except Exception:
            continue

        for el in elements:
            try:
                if not el.is_visible():
                    continue

                box = el.bounding_box()
                if not box or box["width"] < 5 or box["height"] < 5:
                    continue

                if box["y"] + box["height"] < 0 or box["y"] > VIEWPORT_HEIGHT:
                    continue

                box_key = (round(box["x"]), round(box["y"]),
                           round(box["width"]), round(box["height"]))
                if box_key in seen_boxes:
                    continue
                seen_boxes.add(box_key)

                text = (el.evaluate("e => e.textContent?.trim()") or "")[:80]
                tag = el.evaluate("e => e.tagName.toLowerCase()") or ""
                placeholder = el.get_attribute("placeholder") or ""
                name = el.get_attribute("name") or ""
                input_type = el.get_attribute("type") or ""
                aria_label = el.get_attribute("aria-label") or ""
                href = el.get_attribute("href") or ""
                el_id = el.get_attribute("id") or ""
                value = el.get_attribute("value") or ""

                label_parts = []
                if text:
                    label_parts.append(text)
                if placeholder:
                    label_parts.append(f'placeholder="{placeholder}"')
                if aria_label and aria_label != text:
                    label_parts.append(f'aria="{aria_label}"')
                if name:
                    label_parts.append(f'name="{name}"')

                collected.append({
                    "id": index,
                    "tag": tag,
                    "type": input_type,
                    "text": text,
                    "placeholder": placeholder,
                    "name": name,
                    "aria_label": aria_label,
                    "href": href[:100],
                    "element_id": el_id,
                    "value": value[:50],
                    "label": " | ".join(label_parts) if label_parts else tag,
                    "box": box,
                })
                index += 1
            except Exception:
                continue

    if len(collected) > MAX_ELEMENTS:
        hi = [e for e in collected if e["tag"] in HIGH_PRIORITY_TAGS]
        lo = [e for e in collected if e["tag"] not in HIGH_PRIORITY_TAGS]
        collected = (hi + lo)[:MAX_ELEMENTS]
        for i, e in enumerate(collected, 1):
            e["id"] = i

    return collected


# ================================
# ANNOTATED SCREENSHOT
# ================================

COLOR_MAP = {
    "button": "#00FF88", "input": "#FF8800", "a": "#4488FF",
    "select": "#AA44FF", "textarea": "#FF8800",
}


def take_screenshot(page, elements):
    """Take viewport screenshot with numbered bounding boxes. Returns (img, b64)."""
    raw = page.screenshot(full_page=False)
    img = Image.open(io.BytesIO(raw))
    draw = ImageDraw.Draw(img)

    for el in elements:
        box = el["box"]
        x1, y1 = int(box["x"]), int(box["y"])
        x2, y2 = int(box["x"] + box["width"]), int(box["y"] + box["height"])

        if y2 < 0 or y1 > VIEWPORT_HEIGHT:
            continue

        if el.get("type") == "password":
            try:
                region = img.crop((x1, y1, x2, y2))
                img.paste(region.filter(ImageFilter.GaussianBlur(15)), (x1, y1))
            except Exception:
                pass
            continue

        color = COLOR_MAP.get(el["tag"], "#FF4444")
        draw.rectangle([(x1, y1), (x2, y2)], outline=color, width=3)

        bid = str(el["id"])
        bx, by = x1, max(y1 - 18, 0)
        draw.rectangle([(bx, by), (bx + 22, by + 16)], fill=color)
        draw.text((bx + 3, by + 1), bid, fill="black")

    img.save("current_step.png")

    buf = io.BytesIO()
    img.convert("RGB").save(buf, format="JPEG", quality=65)
    return img, base64.b64encode(buf.getvalue()).decode()


# ================================
# ELEMENT SUMMARY FOR PROMPT
# ================================

def element_summary(elements):
    """Compact text list of elements for the LLM."""
    lines = []
    for el in elements:
        b = el["box"]
        if b["y"] + b["height"] < 0 or b["y"] > VIEWPORT_HEIGHT:
            continue
        line = f"[{el['id']}] <{el['tag']}> {el['label']}"
        if el["type"]:
            line += f" type={el['type']}"
        if el["href"]:
            line += f" href={el['href'][:50]}"
        lines.append(line)
    return "\n".join(lines)


# ================================
# SYSTEM PROMPT
# ================================

SYSTEM_PROMPT = """You are a PRECISE UI Navigator Agent controlling a real web browser via Playwright.
You see an annotated screenshot with numbered bounding boxes and a list of interactive elements.

## YOUR OBJECTIVE
Complete the user's goal END-TO-END. Do NOT stop midway.

## OUTPUT FORMAT
Respond with EXACTLY ONE raw JSON object. No markdown, no explanation, no text outside the JSON.

## AVAILABLE ACTIONS

{"action": "click", "element_id": 5, "reason": "..."}
{"action": "type", "element_id": 3, "text": "shoes", "reason": "..."}
{"action": "clear_and_type", "element_id": 3, "text": "shoes", "reason": "..."}
{"action": "scroll", "direction": "down", "reason": "..."}
{"action": "scroll", "direction": "up", "reason": "..."}
{"action": "key", "key": "Enter", "reason": "..."}
{"action": "key", "key": "Escape", "reason": "..."}
{"action": "key", "key": "Tab", "reason": "..."}
{"action": "wait", "seconds": 2, "reason": "..."}
{"action": "ask_user", "question": "...", "reason": "..."}
{"action": "done", "summary": "...", "reason": "..."}
{"action": "go_back", "reason": "..."}

## TASK COMPLETION RULES

### Shopping / "Buy X" tasks:
1. Search for the product
2. When results appear → ASK USER which product they want (list top 3-4 with prices)
3. Click chosen product to open detail page
4. On product page → ASK USER to confirm size/color/quantity
5. Click "Add to Cart" / "Buy Now"
6. Proceed to checkout → ASK USER for address/payment if needed
7. At final confirmation → ASK USER "Should I place this order?"
8. Only say "done" after order placed OR user says stop

### Form Filling tasks:
1. Fill ALL fields, not just the first one
2. ASK USER for any information you don't have
3. Submit the form
4. Confirm submission was successful

### General Navigation tasks:
1. Navigate step by step
2. ASK USER when there are choices to make
3. Only say "done" when the final destination/action is reached

## CRITICAL RULES
- If a popup/modal/cookie-banner appears → dismiss it first
- NEVER say "done" just because search results appeared
- NEVER say "done" just because item was added to cart
- When you see a product list → describe top options and ASK USER
- When you need personal info → ASK USER
- If you can't find an element → scroll down
- If an action fails → try an alternative approach
- If a page seems stuck → try scrolling or going back
- Don't repeat failed actions — try alternatives
- For "type" action: target must be an input/textarea
"""


# ================================
# ASK GEMINI
# ================================

def ask_gemini(client, screenshot_b64, elements, goal, history):
    """Send screenshot + elements + goal to Gemini, return action dict."""
    el_text = element_summary(elements)

    hist_text = ""
    if history:
        hist_text = "\n\nACTION HISTORY (previous steps, most recent last):\n"
        for i, h in enumerate(history[-10:], 1):
            compact = {k: v for k, v in h.items()
                       if k in ("action", "element_id", "text", "reason",
                                "question", "user_response", "summary")}
            hist_text += f"  Step {i}: {json.dumps(compact)}\n"

    prompt = f"""USER'S GOAL: {goal}

VISIBLE ELEMENTS ON PAGE:
{el_text}
{hist_text}
Based on the screenshot and elements, what is the SINGLE next action?
Output ONLY a JSON object."""

    image_part = genai.types.Part.from_bytes(
        data=base64.b64decode(screenshot_b64),
        mime_type="image/jpeg",
    )

    try:
        resp = client.models.generate_content(
            model=MODEL_ID,
            contents=[genai.types.Content(
                role="user",
                parts=[image_part, genai.types.Part.from_text(text=prompt)],
            )],
            config=genai.types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
                temperature=0.1,
                max_output_tokens=500,
            ),
        )
    except Exception as e:
        print(f"⚠️  Gemini API error: {e}")
        return {"action": "wait", "seconds": 2, "reason": f"API error: {str(e)[:80]}"}

    raw = resp.text.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        print(f"⚠️  Invalid JSON from Gemini: {raw[:200]}")
        return {"action": "wait", "seconds": 1, "reason": "Retrying after bad response"}


# ================================
# EXECUTE ACTION
# ================================

def execute_action(page, action, elements):
    """Execute a single action on the page. Returns True/False."""
    act = action.get("action", "")

    if act == "click":
        target = next((e for e in elements if e["id"] == action.get("element_id")), None)
        if not target:
            print(f"⚠️  Element {action.get('element_id')} not found")
            return False
        box = target["box"]
        page.mouse.click(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
        page.wait_for_timeout(1500)
        return True

    elif act == "type":
        target = next((e for e in elements if e["id"] == action.get("element_id")), None)
        if not target:
            print(f"⚠️  Element {action.get('element_id')} not found")
            return False
        box = target["box"]
        page.mouse.click(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
        page.wait_for_timeout(200)
        page.keyboard.type(action.get("text", ""), delay=40)
        page.wait_for_timeout(500)
        return True

    elif act == "clear_and_type":
        target = next((e for e in elements if e["id"] == action.get("element_id")), None)
        if not target:
            return False
        box = target["box"]
        page.mouse.click(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
        page.wait_for_timeout(200)
        page.keyboard.press("Meta+a")
        page.wait_for_timeout(100)
        page.keyboard.type(action.get("text", ""), delay=40)
        page.wait_for_timeout(500)
        return True

    elif act == "scroll":
        delta = 500 if action.get("direction", "down") == "down" else -500
        page.mouse.wheel(0, delta)
        page.wait_for_timeout(1000)
        return True

    elif act == "key":
        page.keyboard.press(action.get("key", "Enter"))
        page.wait_for_timeout(1000)
        return True

    elif act == "wait":
        page.wait_for_timeout(int(action.get("seconds", 2) * 1000))
        return True

    elif act == "go_back":
        page.go_back()
        page.wait_for_timeout(2000)
        return True

    elif act in ("ask_user", "done"):
        return True

    else:
        print(f"⚠️  Unknown action: {act}")
        return False


# ================================
# AGENT LOOP
# ================================

def run_agent(url, goal):
    """Main autonomous agent loop."""
    client = get_gemini_client()
    history = []
    consecutive_waits = 0

    print(f"\n{'='*60}")
    print(f"🤖 UNIVERSAL OVERLAY NAVIGATOR")
    print(f"{'='*60}")
    print(f"🌐 URL:  {url}")
    print(f"🎯 Goal: {goal}")
    print(f"📊 Max steps: {MAX_STEPS}")
    print(f"{'='*60}\n")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        ctx = browser.new_context(
            viewport={"width": VIEWPORT_WIDTH, "height": VIEWPORT_HEIGHT},
            device_scale_factor=1,
        )
        page = ctx.new_page()

        print(f"🌐 Navigating to {url}...")
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
        except Exception as e:
            print(f"❌ Failed to load: {e}")
            browser.close()
            return

        page.wait_for_timeout(3000)

        for step in range(1, MAX_STEPS + 1):
            print(f"\n{'─'*50}")
            print(f"📍 STEP {step}/{MAX_STEPS}")
            print(f"{'─'*50}")

            # 1) Collect elements
            print("🔍 Scanning elements...")
            elements = collect_elements(page)
            print(f"   Found {len(elements)} elements")

            # 2) Screenshot
            print("📸 Screenshot...")
            _, shot_b64 = take_screenshot(page, elements)

            # 3) Ask Gemini
            print("🧠 Thinking...")
            action = ask_gemini(client, shot_b64, elements, goal, history)

            act_type = action.get("action", "unknown")
            reason = action.get("reason", "")
            print(f"   ➤ Action: {act_type}")
            print(f"   ➤ Reason: {reason}")

            # Consecutive wait detection
            if act_type == "wait":
                consecutive_waits += 1
                if consecutive_waits >= 3:
                    print("⚠️  3 consecutive waits — scrolling to try something new")
                    page.mouse.wheel(0, 400)
                    page.wait_for_timeout(1000)
                    consecutive_waits = 0
                    continue
            else:
                consecutive_waits = 0

            # Handle done
            if act_type == "done":
                summary = action.get("summary", "Task completed")
                print(f"\n✅ AGENT COMPLETE: {summary}")
                history.append(action)
                break

            # Handle ask_user
            if act_type == "ask_user":
                question = action.get("question", "What should I do?")
                print(f"\n💬 AGENT ASKS: {question}")
                user_input = input("👤 Your answer: ").strip()
                if user_input.lower() in ("quit", "exit", "stop", "cancel"):
                    print("\n🛑 User cancelled.")
                    break
                action["user_response"] = user_input
                history.append(action)
                goal = f"{goal}. User responded: '{user_input}'"
                continue

            # Execute
            print("⚡ Executing...")
            ok = execute_action(page, action, elements)
            print(f"   {'✓ Done' if ok else '✗ Failed'}")
            history.append(action)

            page.wait_for_timeout(1500)

        else:
            print(f"\n⚠️  Max steps ({MAX_STEPS}) reached.")

        # Save outputs
        print("\n📸 Saving final screenshot...")
        page.screenshot(path="final_screenshot.png")
        print("✅ final_screenshot.png")

        with open("action_log.json", "w") as f:
            json.dump({"url": url, "goal": goal, "steps": history}, f, indent=2)
        print("✅ action_log.json")

        input("\n⏸  Press Enter to close browser...")
        browser.close()


# ================================
# CLI
# ================================

def main():
    print("""
╔══════════════════════════════════════════════════════════╗
║        🤖 UNIVERSAL OVERLAY NAVIGATOR                   ║
║   AI-Powered End-to-End Task Agent (Gemini + Playwright) ║
╚══════════════════════════════════════════════════════════╝
    """)

    url = input("🌐 Enter URL: ").strip()
    if not url:
        url = "https://www.google.com"
    if not url.startswith("http"):
        url = "https://" + url

    goal = input("🎯 What's your goal? ").strip()
    if not goal:
        goal = "Explore the page and describe what you see"

    print()
    run_agent(url, goal)


if __name__ == "__main__":
    main()
