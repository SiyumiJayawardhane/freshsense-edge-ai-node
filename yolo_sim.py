"""
yolo_sim.py - Simulated YOLOv5 food detection.

Reads ALL items from fridge_items.json and simulates detection + freshness
for each one. This mirrors real YOLOv5 behavior where everything visible
in the frame gets detected.

To add a new food item (e.g. cucumber was placed in the fridge):
    - Add it to fridge_items.json
    - Next checkup will detect it and insert it into the database

To remove a food item (e.g. it was eaten):
    - Remove it from fridge_items.json
    - It will stop being updated (existing DB record stays)

Replace analyze_image() body with real YOLOv5 torch inference later:
    model = torch.hub.load('ultralytics/yolov5', 'custom', path='best.pt')
    results = model(image_path)
    ...
"""

import os
import json
import random
import hashlib
import logging
from datetime import datetime

log = logging.getLogger(__name__)

FRIDGE_CONFIG = os.path.join(os.path.dirname(__file__), "fridge_items.json")


def _score_to_status(score: float) -> str:
    if score >= 65:
        return "fresh"
    elif score >= 30:
        return "at_risk"
    else:
        return "spoiled"


def _days_to_score(days: int, max_days: int) -> float:
    ratio = days / max_days
    return round(min(100, max(0, ratio * 100)), 1)


def _load_fridge_items() -> list:
    if not os.path.exists(FRIDGE_CONFIG):
        log.warning(f"fridge_items.json not found at {FRIDGE_CONFIG}. Using empty list.")
        return []
    with open(FRIDGE_CONFIG, "r") as f:
        items = json.load(f)
    log.info(f"Loaded {len(items)} item(s) from fridge_items.json: {[i['name'] for i in items]}")
    return items


def analyze_image(image_path: str) -> list:
    """
    Simulates YOLOv5 detection. Detects ALL items in fridge_items.json.
    Each item gets its own deterministic freshness score based on today's date.
    """
    log.info(f"[SIMULATED] Analyzing image: {image_path}")

    fridge_items = _load_fridge_items()
    if not fridge_items:
        log.warning("No items in fridge_items.json - nothing to detect.")
        return []

    base_seed = _image_seed(image_path)

    detections = []
    for food in fridge_items:
        # Each item gets its own seed so they have independent freshness scores
        item_seed = base_seed ^ hash(food["name"]) ^ datetime.now().toordinal()
        rng = random.Random(item_seed)

        days_range = food.get("days_range", [1, 7])
        max_days = days_range[1]
        days_left = rng.randint(days_range[0], max_days)
        score = _days_to_score(days_left, max_days)
        status = _score_to_status(score)
        confidence = round(rng.uniform(0.72, 0.98), 2)

        detection = {
            "name": food["name"],
            "category": food.get("category", "general"),
            "freshness_status": status,
            "freshness_score": score,
            "confidence": confidence,
            "estimated_days_to_spoil": days_left,
            "storage_tips": food.get("storage_tips", []),
        }
        detections.append(detection)
        log.info(f"  -> {food['name']}: {status} (score={score}, days_left={days_left})")

    return detections


def _image_seed(image_path: str) -> int:
    try:
        with open(image_path, "rb") as f:
            file_bytes = f.read(1024)
        h = hashlib.md5(file_bytes).hexdigest()
    except Exception:
        h = hashlib.md5(b"placeholder").hexdigest()
    return int(h[:8], 16)
