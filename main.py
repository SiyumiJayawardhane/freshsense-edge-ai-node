import base64
import logging
import os
import threading
import time
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path

import requests
from dotenv import load_dotenv

from notifier import generate_notifications
from raspberrypi.sensors.sensor_detection import run_sensor_loop
from raspberrypi.vision.yolo_detection import run_vision_loop
from storage_client import StorageClient
from supabase_client import SupabaseClient

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(dotenv_path=BASE_DIR / ".env")
LOG_DIR = BASE_DIR / "logs"
LOG_FILE = LOG_DIR / "raspberrypi-runtime.log"

API_URL = os.getenv("FRESHSENSE_API_URL", "http://127.0.0.1:8000/api/ingest")
SUPABASE_USER_ID = os.getenv("SUPABASE_USER_ID")
DIRECT_DB_ENABLED = os.getenv("DIRECT_DB_ENABLED", "true").lower() == "true"
API_FORWARD_ENABLED = os.getenv("API_FORWARD_ENABLED", "false").lower() == "true"
INGEST_INTERVAL_SECONDS = int(os.getenv("INGEST_INTERVAL_SECONDS", "5"))


def setup_logging() -> logging.Logger:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    level_name = os.getenv("LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    file_handler = RotatingFileHandler(LOG_FILE, maxBytes=2_000_000, backupCount=5, encoding="utf-8")
    file_handler.setFormatter(formatter)
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    logging.basicConfig(level=level, handlers=[file_handler, stream_handler], force=True)
    return logging.getLogger("raspberrypi.main")


def image_to_base64(path: str | None) -> str | None:
    if not path:
        return None
    p = Path(path)
    if not p.exists():
        return None
    with p.open("rb") as f:
        return base64.b64encode(f.read()).decode("ascii")


def parse_food_name(label: str) -> str:
    text = (label or "").strip().lower()
    if "_" in text:
        return text.split("_", 1)[1]
    return text or "food_item"


def parse_status(label: str) -> str:
    text = (label or "").strip().lower()
    status = text.split("_", 1)[0] if "_" in text else "fresh"
    if status in {"atrisk", "at"}:
        return "at_risk"
    if status in {"fresh", "at_risk", "spoiled"}:
        return status
    return "fresh"


def estimate_days_to_spoil(status: str, confidence: float) -> int:
    pct = max(0.0, min(1.0, confidence))
    if status == "spoiled":
        return 0
    if status == "at_risk":
        return max(1, int(round(1 + (1 - pct) * 2)))
    return max(3, int(round(3 + pct * 4)))


def freshness_score(status: str, confidence: float) -> float:
    pct = round(max(0.0, min(1.0, confidence)) * 100, 1)
    if status == "fresh":
        return max(70.0, pct)
    if status == "at_risk":
        return min(69.9, max(35.0, pct))
    return min(34.9, pct)


def storage_tips_for(status: str, item_name: str) -> list[str]:
    if status == "spoiled":
        return [f"Discard {item_name} safely.", "Clean nearby storage area."]
    if status == "at_risk":
        return [f"Use {item_name} soon.", "Store sealed and refrigerated."]
    return [f"Keep {item_name} chilled.", "Check freshness daily."]


def build_detected_items(vision_data: dict, storage: StorageClient | None) -> list[dict]:
    full_image_b64 = image_to_base64(vision_data.get("saved_image"))
    items: list[dict] = []
    for obj in vision_data.get("detected_objects", []):
        label = obj.get("label", "unknown_item")
        crop_path = obj.get("crop_path")
        image_url = None
        image_b64 = None
        if storage and crop_path:
            image_url = storage.upload_image(SUPABASE_USER_ID, crop_path, parse_food_name(label))
        if not image_url:
            image_b64 = image_to_base64(crop_path) or full_image_b64
        item = {"label": label, "confidence": float(obj.get("score", 0.0))}
        if image_url:
            item["image_url"] = image_url
        elif image_b64:
            item["image_base64"] = image_b64
        items.append(item)
    return items


def build_detection_record(item: dict) -> dict:
    label = item.get("label", "fresh_food_item")
    confidence = float(item.get("confidence", 0.0))
    status = parse_status(label)
    name = parse_food_name(label).replace("_", " ").strip().title()
    days = estimate_days_to_spoil(status, confidence)
    return {
        "name": name,
        "category": "Produce",
        "freshness_status": status,
        "freshness_score": freshness_score(status, confidence),
        "confidence": round(confidence * 100, 2),
        "estimated_days_to_spoil": days,
        "storage_tips": storage_tips_for(status, name.lower()),
        "image_url": item.get("image_url"),
    }


def _first_non_none(data: dict, keys: list[str]):
    for key in keys:
        value = data.get(key)
        if value is not None:
            return value
    return None


def main():
    log = setup_logging()
    if not SUPABASE_USER_ID:
        raise RuntimeError("SUPABASE_USER_ID must be set in edge-ai-node .env")

    shared_state = {"sensor": None, "vision": None}
    storage: StorageClient | None = None
    db: SupabaseClient | None = None
    try:
        storage = StorageClient()
        log.info("Supabase storage upload enabled")
    except Exception as ex:
        log.warning("Supabase storage upload disabled: %s", ex)
    if DIRECT_DB_ENABLED:
        try:
            db = SupabaseClient()
            log.info("Direct Supabase writes enabled")
        except Exception as ex:
            log.warning("Direct Supabase writes disabled: %s", ex)

    sensor_thread = threading.Thread(target=run_sensor_loop, args=(shared_state,), daemon=True)
    vision_thread = threading.Thread(target=run_vision_loop, args=(shared_state,), daemon=True)
    sensor_thread.start()
    vision_thread.start()
    log.info("Raspberry Pi runtime started")
    last_sent_signature = None

    try:
        while True:
            time.sleep(INGEST_INTERVAL_SECONDS)
            sensor_data = shared_state.get("sensor")
            vision_data = shared_state.get("vision")
            if sensor_data is None or vision_data is None:
                continue
            signature = (
                sensor_data.get("timestamp"),
                vision_data.get("timestamp"),
                tuple(obj.get("label") for obj in vision_data.get("detected_objects", [])),
            )
            if signature == last_sent_signature:
                continue

            debug = sensor_data.get("debug", {})
            mq3_value = _first_non_none(debug, ["mq3_model_value", "mq3_gas_value", "mq3", "mq3_raw_ads"])
            mq135_value = _first_non_none(
                debug,
                ["mq135_model_value", "mq135_gas_value", "mq135", "mq35_model_value", "mq35_gas_value", "mq135_raw_ads"],
            )
            if mq3_value is None or mq135_value is None:
                log.warning(
                    "Gas value missing from sensor debug. mq3=%s mq135=%s keys=%s",
                    mq3_value,
                    mq135_value,
                    sorted(debug.keys()),
                )

            payload = {
                "user_id": SUPABASE_USER_ID,
                "sensor": {
                    "humidity": debug.get("humidity"),
                    "temperature": debug.get("temp"),
                    "mq3_gas_value": mq3_value,
                    "mq135_gas_value": mq135_value,
                },
                "detected_items": build_detected_items(vision_data, storage),
                "captured_at": datetime.now(timezone.utc).isoformat(),
            }

            if db:
                try:
                    sensor_db = {
                        "humidity": payload["sensor"]["humidity"],
                        "temperature": payload["sensor"]["temperature"],
                        "mq3_gas_value": payload["sensor"]["mq3_gas_value"],
                        "mq135_gas_value": payload["sensor"]["mq135_gas_value"],
                    }
                    food_item_ids: list[tuple[str, dict]] = []
                    for item in payload["detected_items"]:
                        detection = build_detection_record(item)
                        food_id = db.insert_food_item(SUPABASE_USER_ID, detection, sensor_db)
                        db.insert_sensor_reading(SUPABASE_USER_ID, food_id, sensor_db)
                        food_item_ids.append((food_id, detection))
                    notifications = generate_notifications(food_item_ids)
                    for notif in notifications:
                        db.insert_notification(SUPABASE_USER_ID, notif)
                    log.info("DB sync complete: items=%s notifications=%s", len(food_item_ids), len(notifications))
                except Exception as ex:
                    log.exception("DB sync failed: %s", ex)

            if API_FORWARD_ENABLED:
                try:
                    response = requests.post(API_URL, json=payload, timeout=20)
                    response.raise_for_status()
                    log.info("API forward OK status=%s", response.status_code)
                except Exception as ex:
                    log.exception("API forward failed: %s", ex)

            last_sent_signature = signature
    except KeyboardInterrupt:
        log.info("Stopped by user")
    finally:
        if db:
            db.close()
            log.info("DB connection closed")


if __name__ == "__main__":
    main()
