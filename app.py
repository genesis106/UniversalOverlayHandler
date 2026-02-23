from playwright.sync_api import sync_playwright
from PIL import Image, ImageDraw, ImageFilter
import io
import json
import time
import base64

# ================================
# CONFIGURATION
# ================================

TARGET_URL = "https://www.amazon.com/"
ACTION_TYPE = "CLICK_BUTTON"  # CLICK_BUTTON | FILL_INPUT | SELECT_DROPDOWN | CLICK_LINK
INSTRUCTION = "Search for shoes"

# ================================
# ELEMENT COLLECTION (ACTION-AWARE)
# ================================

def collect_elements(page, action_type):
    collected_data = []
    index = 1

    # Ensure page fully loaded
    page.wait_for_load_state("load")
    page.wait_for_timeout(2000)

    # Ensure Amazon search bar is present
    try:
        page.wait_for_selector("#twotabsearchtextbox", timeout=5000)
    except:
        pass

    if action_type == "CLICK_BUTTON":
        elements = page.query_selector_all(
            "button, input[type='submit'], input[type='button']"
        )

    elif action_type == "FILL_INPUT":
        # Cleaner filtering (avoid hidden garbage inputs)
        elements = page.query_selector_all(
            "input[type='text'], input[type='search'], textarea"
        )

    elif action_type == "SELECT_DROPDOWN":
        elements = page.query_selector_all(
            "select, [role='combobox'], .MuiSelect-root"
        )

    elif action_type == "CLICK_LINK":
        elements = page.query_selector_all("a")

    else:
        elements = []

    for element in elements:
        try:
            if not element.is_visible():
                continue

            box = element.bounding_box()
            if not box:
                continue

            # Skip zero-size elements
            if box["width"] < 5 or box["height"] < 5:
                continue

            text = element.evaluate("el => el.textContent.trim()") or ""
            placeholder = element.get_attribute("placeholder") or ""
            name = element.get_attribute("name") or ""
            input_type = element.get_attribute("type") or ""
            aria_label = element.get_attribute("aria-label") or ""
            role = element.get_attribute("role") or ""
            element_id_attr = element.get_attribute("id") or ""
            class_attr = element.get_attribute("class") or ""

            collected_data.append({
                "id": index,
                "action_type": action_type,
                "text": text,
                "placeholder": placeholder,
                "name": name,
                "input_type": input_type,
                "aria_label": aria_label,
                "role": role,
                "element_id_attr": element_id_attr,
                "class_attr": class_attr,
                "coordinates": box
            })

            index += 1

        except Exception:
            continue

    return collected_data


# ================================
# DRAW FILTERED BOXES
# ================================

def draw_boxes(image, elements, action_type):
    draw = ImageDraw.Draw(image)

    color_map = {
        "CLICK_BUTTON": "green",
        "FILL_INPUT": "orange",
        "SELECT_DROPDOWN": "purple",
        "CLICK_LINK": "blue"
    }

    box_color = color_map.get(action_type, "red")

    for item in elements:
        box = item["coordinates"]

        x1 = int(box["x"])
        y1 = int(box["y"])
        x2 = int(box["x"] + box["width"])
        y2 = int(box["y"] + box["height"])

        # Blur password fields
        if item.get("input_type") == "password":
            cropped = image.crop((x1, y1, x2, y2))
            blurred = cropped.filter(ImageFilter.GaussianBlur(15))
            image.paste(blurred, (x1, y1))
        else:
            draw.rectangle(
                [(x1, y1), (x2, y2)],
                outline=box_color,
                width=4
            )
            draw.text((x1, y1 - 15), str(item["id"]), fill=box_color)

    return image


# ================================
# MAIN EXECUTION
# ================================

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)
    page = browser.new_page(device_scale_factor=1)

    page.goto(TARGET_URL)

    print(f"🔍 Collecting elements for action: {ACTION_TYPE}")
    elements = collect_elements(page, ACTION_TYPE)
    print(f"✅ Collected {len(elements)} relevant elements")

    print("📸 Taking FULL-PAGE screenshot...")
    screenshot_bytes = page.screenshot(full_page=True)  # NOT CHANGED
    img = Image.open(io.BytesIO(screenshot_bytes))

    print("🖌 Drawing filtered boxes...")
    processed_img = draw_boxes(img, elements, ACTION_TYPE)

    processed_img.save("processed.png")

    # Convert processed image to base64
    buffered = io.BytesIO()
    processed_img.save(buffered, format="PNG")
    image_base64 = base64.b64encode(buffered.getvalue()).decode()

    payload = {
        "instruction": INSTRUCTION,
        "action_type": ACTION_TYPE,
        "elements": elements,
        "image_base64": image_base64
    }

    with open("payload.json", "w") as f:
        json.dump(payload, f, indent=4)

    print("✅ processed.png saved")
    print("✅ payload.json saved (Ready for Gemini)")

    browser.close()