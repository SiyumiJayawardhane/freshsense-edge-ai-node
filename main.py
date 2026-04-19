"""
FreshGuard - Raspberry Pi Freshness Monitor
Runs every 6 hours via cron or systemd timer.
Captures image → simulated YOLOv5 → sensor readings → push to Supabase
"""

import os
import sys
sys.stdout.reconfigure(encoding='utf-8')
import time
import logging
from datetime import datetime
from dotenv import load_dotenv


from camera import capture_image
from yolo_sim import analyze_image
from sensor_sim import read_sensors
from supabase_client import SupabaseClient
from notifier import generate_notifications

# ── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("logs/freshguard.log"), #should be changed in raspbery pi board to /home/pi/freshguard/logs/freshguard.log
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger(__name__)

load_dotenv()

def run_checkup():
    log.info("=" * 50)
    log.info("FreshGuard checkup started")
    log.info("=" * 50)

    db = SupabaseClient()
    user_id = os.getenv("SUPABASE_USER_ID")

    if not user_id:
        log.error("SUPABASE_USER_ID not set in .env — aborting.")
        sys.exit(1)

    # ── 1. Capture image ──────────────────────────────────────────────────────
    log.info("Capturing image from camera...")
    image_path = capture_image()
    log.info(f"Image saved: {image_path}")

    # ── 2. Analyse with simulated YOLOv5 ─────────────────────────────────────
    log.info("Running YOLOv5 analysis (simulated)...")
    detections = analyze_image(image_path)
    log.info(f"Detections: {detections}")

    # ── 3. Read sensors ───────────────────────────────────────────────────────
    log.info("Reading sensor data (simulated)...")
    sensor_data = read_sensors()
    log.info(f"Sensor data: {sensor_data}")