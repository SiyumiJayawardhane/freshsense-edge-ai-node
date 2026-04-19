"""
camera.py - Captures image using Raspberry Pi 5MP camera module.
Falls back to a placeholder image if camera is unavailable.
"""

import os
import logging
from datetime import datetime

log = logging.getLogger(__name__)

IMAGE_DIR = "/home/pi/freshguard/images"


def capture_image() -> str:
    """
    Captures a still image using libcamera (Pi Camera Module).
    Returns the saved image file path.
    """
    os.makedirs(IMAGE_DIR, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    image_path = os.path.join(IMAGE_DIR, f"capture_{timestamp}.jpg")

    try:
        # libcamera-still is the standard tool for Pi Camera Module v2/v3
        # -o : output path
        # --width / --height : resolution
        # --nopreview : no display preview (headless Pi)
        # -t 2000 : 2 second warmup (auto-exposure settle)
        ret = os.system(
            f"libcamera-still -o {image_path} --width 2592 --height 1944 --nopreview -t 2000"
        )

        if ret != 0:
            raise RuntimeError(f"libcamera-still exited with code {ret}")

        log.info(f"Camera capture successful: {image_path}")
        return image_path

    except Exception as e:
        log.warning(f"Camera capture failed: {e}. Using placeholder image.")
        # Create a small placeholder so the pipeline doesn't break
        placeholder = os.path.join(IMAGE_DIR, f"placeholder_{timestamp}.jpg")
        _create_placeholder(placeholder)
        return placeholder


def _create_placeholder(path: str):
    """Creates a minimal JPEG placeholder (solid grey 64x64)."""
    try:
        from PIL import Image
        img = Image.new("RGB", (64, 64), color=(180, 180, 180))
        img.save(path, "JPEG")
    except ImportError:
        # If PIL isn't available, just create an empty file
        open(path, "w").close()
