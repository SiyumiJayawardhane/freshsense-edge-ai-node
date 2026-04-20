"""
camera.py - Captures or simulates a food image.

On Windows / no Pi camera: generates a realistic simulated image per food item
using PIL, with color coding by freshness status.

On Raspberry Pi with camera: uses libcamera-still to capture a real photo.
"""

import os
import sys
import logging
from datetime import datetime

log = logging.getLogger(__name__)

IMAGE_DIR = os.path.join(os.path.dirname(__file__), "images")

# Color palette per freshness status
STATUS_COLORS = {
    "fresh":    {"bg": (76, 175, 80),   "text": (255, 255, 255)},   # green
    "at_risk":  {"bg": (255, 152, 0),   "text": (255, 255, 255)},   # orange
    "spoiled":  {"bg": (211, 47, 47),   "text": (255, 255, 255)},   # red
    "unknown":  {"bg": (158, 158, 158), "text": (255, 255, 255)},   # grey
}

# Food item accent colors (for the icon circle)
FOOD_COLORS = {
    "apple":         (239, 83, 80),
    "banana":        (255, 235, 59),
    "carrot":        (255, 112, 67),
    "cucumber":      (102, 187, 106),
    "tomato":        (239, 83, 80),
    "lettuce":       (129, 199, 132),
    "strawberry":    (236, 64, 122),
    "chicken breast":(255, 183, 77),
}


def capture_image() -> str:
    """
    On a real Pi: captures via libcamera-still.
    On Windows/no camera: falls back to simulation mode.
    Returns path to a single 'scene' image (like a real camera frame).
    """
    os.makedirs(IMAGE_DIR, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    image_path = os.path.join(IMAGE_DIR, f"capture_{timestamp}.jpg")

    # Try real camera first
    if sys.platform != "win32":
        ret = os.system(
            f"libcamera-still -o {image_path} --width 2592 --height 1944 --nopreview -t 2000 2>/dev/null"
        )
        if ret == 0 and os.path.exists(image_path):
            log.info(f"Camera capture successful: {image_path}")
            return image_path
        log.warning("libcamera-still failed. Falling back to simulated image.")

    # Simulate a fridge scene image
    image_path = _generate_fridge_scene(timestamp)
    return image_path


def capture_food_image(food_name: str, freshness_status: str, score: float, days_left: int) -> str:
    """
    Generates a labeled food image for a specific detected item.
    This is what gets uploaded to Supabase Storage per food item.
    """
    os.makedirs(IMAGE_DIR, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    image_path = os.path.join(IMAGE_DIR, f"{food_name}_{timestamp}.jpg")
    _generate_food_image(image_path, food_name, freshness_status, score, days_left)
    return image_path


def _generate_fridge_scene(timestamp: str) -> str:
    """Generates a placeholder 'fridge overview' image."""
    path = os.path.join(IMAGE_DIR, f"scene_{timestamp}.jpg")
    try:
        from PIL import Image, ImageDraw, ImageFont
        W, H = 800, 500
        img = Image.new("RGB", (W, H), color=(240, 240, 240))
        draw = ImageDraw.Draw(img)

        # Background gradient feel
        for y in range(H):
            shade = int(220 + (y / H) * 20)
            draw.line([(0, y), (W, y)], fill=(shade, shade, shade + 5))

        # Title
        draw.rectangle([0, 0, W, 60], fill=(38, 50, 56))
        draw.text((20, 18), "FreshGuard - Fridge Scan", fill=(255, 255, 255))
        draw.text((20, 38), f"Captured: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", fill=(176, 190, 197))

        img.save(path, "JPEG", quality=90)
        log.info(f"Simulated fridge scene image saved: {path}")
    except ImportError:
        open(path, "wb").close()
    return path


def _generate_food_image(path: str, food_name: str, freshness_status: str, score: float, days_left: int):
    """
    Generates a per-food labeled image with:
    - Color-coded background (green/orange/red by freshness)
    - Food name and freshness details
    - A colored circle representing the food item
    """
    try:
        from PIL import Image, ImageDraw, ImageFont
        W, H = 400, 400
        colors = STATUS_COLORS.get(freshness_status, STATUS_COLORS["unknown"])
        bg_color = colors["bg"]
        text_color = colors["text"]

        img = Image.new("RGB", (W, H), color=(245, 245, 245))
        draw = ImageDraw.Draw(img)

        # Header bar (colored by status)
        draw.rectangle([0, 0, W, 80], fill=bg_color)

        # Food name in header
        draw.text((20, 15), food_name.upper(), fill=text_color)
        draw.text((20, 45), freshness_status.upper(), fill=text_color)

        # Food icon circle
        food_color = FOOD_COLORS.get(food_name.lower(), (150, 150, 150))
        cx, cy, r = W // 2, 185, 80
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=food_color, outline=(200, 200, 200), width=3)

        # Food initial letter in circle
        draw.text((cx - 20, cy - 28), food_name[0].upper(), fill=(255, 255, 255))

        # Freshness details box
        draw.rectangle([20, 290, W - 20, 380], fill=(255, 255, 255), outline=(220, 220, 220), width=1)
        draw.text((35, 300), f"Freshness Score : {score}/100", fill=(50, 50, 50))
        draw.text((35, 325), f"Days to Spoil   : {days_left} day(s)", fill=(50, 50, 50))
        draw.text((35, 350), f"Scanned         : {datetime.now().strftime('%Y-%m-%d %H:%M')}", fill=(120, 120, 120))

        # Footer
        draw.rectangle([0, 385, W, H], fill=(38, 50, 56))
        draw.text((20, 390), "FreshGuard | Simulated Detection", fill=(120, 144, 156))

        img.save(path, "JPEG", quality=92)
        log.info(f"Food image generated: {path}")

    except ImportError:
        log.warning("Pillow not installed — cannot generate food image.")
        open(path, "wb").close()
    except Exception as e:
        log.warning(f"Image generation error: {e}")
        open(path, "wb").close()
