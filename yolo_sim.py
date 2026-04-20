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


