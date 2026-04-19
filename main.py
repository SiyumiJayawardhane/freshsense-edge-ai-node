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



if __name__ == "__main__":
    run_checkup()

