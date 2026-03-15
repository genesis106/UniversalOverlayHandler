"""
Universal Overlay Handler — Element Collection & Screenshot Tool
Final Extended Version (Dynamic Categories + Radio Groups + Universal Mode)
"""

from playwright.sync_api import sync_playwright
from PIL import Image, ImageDraw, ImageFilter
import io
import json
import base64
import sys

# ================================
# CONFIGURATION
# ================================

# ================================
# INPUT FROM FASTAPI / TERMINAL
# ================================

if len(sys.argv) >= 4:
    TARGET_URL = sys.argv[1]
    ACTION_TYPE = sys.argv[2]
    INSTRUCTION = sys.argv[3]
else:
    print("❌ Missing arguments")
    print("Usage: python playwright_runner.py <url> <action_type> <instruction>")
    sys.exit(1)

# ================================
# ELEMENT COLLECTION
# ================================

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


# ================================
# RADIO GROUPING
# ================================

def group_radio_buttons(elements):
    radio_groups = {}

    for el in elements:
        if el.get("category") == "radio":
            group_name = el.get("name") or el.get("aria_label") or "radio_group"

            if group_name not in radio_groups:
                radio_groups[group_name] = {
                    "category": "radio_group",
                    "group_name": group_name,
                    "options": []
                }

            option_label = el.get("text") or el.get("value") or "option"

            radio_groups[group_name]["options"].append({
                "id": el["id"],
                "label": option_label
            })

    return list(radio_groups.values())


# ================================
# DRAW BOXES
# ================================

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
        box = item["coordinates"]

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


# ================================
# MAIN EXECUTION
# ================================

if __name__ == "__main__":
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page(device_scale_factor=1)

        page.goto(TARGET_URL)

        print(f"🔍 Collecting elements for action: {ACTION_TYPE}")
        elements = collect_elements(page, ACTION_TYPE)
        print(f"✅ Collected {len(elements)} elements")

        print("📸 Taking FULL-PAGE screenshot...")
        screenshot_bytes = page.screenshot(full_page=False)
        img = Image.open(io.BytesIO(screenshot_bytes))

        print("🖌 Drawing boxes...")
        processed_img = draw_boxes(img, elements)

        processed_img.save("processed.png")

        buffered = io.BytesIO()
        processed_img.save(buffered, format="PNG")
        image_base64 = base64.b64encode(buffered.getvalue()).decode()

        radio_groups = group_radio_buttons(elements)

        
        
        payload = {
            "instruction": INSTRUCTION,
            "action_type": ACTION_TYPE,
            "elements": elements,
            "screenshot": image_base64
        }

        print(json.dumps(payload))

        print("✅ processed.png saved")
        print("✅ payload.json saved (Ready for Gemini)")

        browser.close()
        