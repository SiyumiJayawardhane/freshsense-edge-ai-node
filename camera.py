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








