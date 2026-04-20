"""
FreshGuard - Raspberry Pi Freshness Monitor
Runs every 6 hours via cron or systemd timer.
Captures image -> simulated YOLOv5 -> sensor readings -> push to Supabase
"""

import os
import sys
import logging
from datetime import datetime
from dotenv import load_dotenv

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), ".env"))

from camera import capture_image, capture_food_image
from yolo_sim import analyze_image
from sensor_sim import read_sensors
from supabase_client import SupabaseClient
from storage_client import StorageClient
from notifier import generate_notifications

# ── Logging ───────────────────────────────────────────────────────────────────
os.makedirs(os.path.join(os.path.dirname(__file__), "logs"), exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(
            os.path.join(os.path.dirname(__file__), "logs", "freshguard.log"),
            encoding="utf-8",
        ),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger(__name__)


def run_checkup():
    log.info("=" * 50)
    log.info("FreshGuard checkup started")
    log.info("=" * 50)

    db = SupabaseClient()
    storage = StorageClient()
    user_id = os.getenv("SUPABASE_USER_ID")

    if not user_id:
        log.error("SUPABASE_USER_ID not set in .env -- aborting.")
        sys.exit(1)

    # ── 1. Capture scene image ────────────────────────────────────────────────
    log.info("Capturing scene image...")
    scene_image_path = capture_image()
    log.info(f"Scene image: {scene_image_path}")

    # ── 2. Analyse with simulated YOLOv5 ─────────────────────────────────────
    log.info("Running YOLOv5 analysis (simulated)...")
    detections = analyze_image(scene_image_path)
    log.info(f"Detected {len(detections)} item(s): {[d['name'] for d in detections]}")

    # ── 3. Read sensors ───────────────────────────────────────────────────────
    log.info("Reading sensor data (simulated)...")
    sensor_data = read_sensors()
    log.info(f"Sensor -> Temp={sensor_data['temperature']}C, Humidity={sensor_data['humidity']}%, Gas={sensor_data['gas_value']}")

    # ── 4. Per-food: generate image, upload, upsert to DB ─────────────────────
    log.info("Processing each detected food item...")
    food_item_ids = []

    for detection in detections:
        name = detection["name"]

        # Generate a labeled food image for this specific item
        food_img_path = capture_food_image(
            food_name=name,
            freshness_status=detection["freshness_status"],
            score=detection["freshness_score"],
            days_left=detection["estimated_days_to_spoil"],
        )

        # Upload to Supabase Storage -> get public URL
        image_url = storage.upload_image(user_id, food_img_path, name)
        if image_url:
            log.info(f"  [UPLOAD] {name} -> {image_url}")
        else:
            log.warning(f"  [UPLOAD FAILED] {name} -- continuing without image URL")

        # Attach URL to detection before DB write
        detection["image_url"] = image_url

        # Upsert food item into database
        food_id = db.upsert_food_item(user_id, detection, sensor_data)
        food_item_ids.append((food_id, detection))
        log.info(f"  [DB] {name} ({detection['freshness_status']}) -> food_item: {food_id}")

    # ── 5. Log sensor readings ────────────────────────────────────────────────
    for food_id, _ in food_item_ids:
        db.insert_sensor_reading(user_id, food_id, sensor_data)

    # ── 6. Generate and insert notifications ──────────────────────────────────
    notifications = generate_notifications(food_item_ids)
    for notif in notifications:
        db.insert_notification(user_id, notif)
        log.info(f"  [NOTIF] [{notif['severity']}] {notif['title']}")

    db.close()
    log.info("Checkup complete. Next run in 6 hours.")


if __name__ == "__main__":
    run_checkup()
