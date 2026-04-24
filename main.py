import base64
import json
import logging
import os
import threading
import time
from collections import deque
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
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
INGEST_INTERVAL_SECONDS = int(os.getenv("INGEST_INTERVAL_SECONDS", "60"))
MANUAL_TRIGGER_ENABLED = os.getenv("MANUAL_TRIGGER_ENABLED", "true").lower() == "true"
MANUAL_TRIGGER_HOST = os.getenv("MANUAL_TRIGGER_HOST", "0.0.0.0")
MANUAL_TRIGGER_PORT = int(os.getenv("MANUAL_TRIGGER_PORT", "8010"))
MANUAL_TRIGGER_TOKEN = os.getenv("MANUAL_TRIGGER_TOKEN", "").strip()
CLEANUP_ENABLED = os.getenv("CLEANUP_ENABLED", "true").lower() == "true"
CLEANUP_INTERVAL_SECONDS = int(os.getenv("CLEANUP_INTERVAL_SECONDS", "3600"))
CLEANUP_TABLES = [
    table.strip()
    for table in os.getenv(
        "CLEANUP_TABLES",
        "notification_email_dispatches,notifications,sensor_readings,food_items",
    ).split(",")
    if table.strip()
]
MQ135_BASELINE_WINDOW = int(os.getenv("MQ135_BASELINE_WINDOW", "60"))
MQ135_SMOOTHING_WINDOW = int(os.getenv("MQ135_SMOOTHING_WINDOW", "5"))
MQ135_RATIO_AT_RISK = float(os.getenv("MQ135_RATIO_AT_RISK", "1.15"))
MQ135_RATIO_SPOILED = float(os.getenv("MQ135_RATIO_SPOILED", "1.35"))
MQ135_CONSECUTIVE_CONFIRMATIONS = int(os.getenv("MQ135_CONSECUTIVE_CONFIRMATIONS", "3"))
MQ3_WEIGHT = float(os.getenv("MQ3_WEIGHT", "0.3"))
MQ135_WEIGHT = float(os.getenv("MQ135_WEIGHT", "0.7"))
VISION_FUSION_WEIGHT = float(os.getenv("VISION_FUSION_WEIGHT", "0.75"))
SENSOR_FUSION_WEIGHT = float(os.getenv("SENSOR_FUSION_WEIGHT", "0.25"))
VISION_LOCK_CONFIDENCE = float(os.getenv("VISION_LOCK_CONFIDENCE", "0.85"))
SENSOR_CONFIDENCE_FALLBACK = float(os.getenv("SENSOR_CONFIDENCE_FALLBACK", "0.60"))
GAS_SENSOR_AGREE_BONUS = float(os.getenv("GAS_SENSOR_AGREE_BONUS", "0.15"))
GAS_SENSOR_DISAGREE_PENALTY = float(os.getenv("GAS_SENSOR_DISAGREE_PENALTY", "0.20"))
 
 
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
 
 
def normalize_status(status: str | None) -> str:
    text = (status or "").strip().lower()
    if text in {"atrisk", "at"}:
        return "at_risk"
    if text in {"fresh", "at_risk", "spoiled"}:
        return text
    return "fresh"


def _status_to_score(status: str) -> float:
    # 1.0 = fresh, 0.5 = at_risk, 0.0 = spoiled
    if status == "fresh":
        return 1.0
    if status == "at_risk":
        return 0.5
    return 0.0


def _score_to_status(value: float) -> str:
    if value >= 0.75:
        return "fresh"
    if value >= 0.35:
        return "at_risk"
    return "spoiled"


def status_from_sensor_prediction(sensor_prediction: str | None) -> str | None:
    if sensor_prediction is None:
        return None
    text = str(sensor_prediction).strip().lower()
    if text in {"fresh", "at_risk", "spoiled", "atrisk"}:
        return normalize_status(text)
    # Support labels like "fresh_banana" if model returns item-attached labels.
    if "_" in text:
        return normalize_status(text.split("_", 1)[0])
    return None


def sensor_prediction_confidence(sensor_data: dict, sensor_status: str | None) -> float:
    if sensor_status is None:
        return 0.0
    probs = sensor_data.get("probabilities")
    if isinstance(probs, dict):
        direct = probs.get(sensor_status)
        if direct is not None:
            return float(max(0.0, min(1.0, direct)))
        if sensor_status == "at_risk" and probs.get("atrisk") is not None:
            return float(max(0.0, min(1.0, probs["atrisk"])))
    return float(max(0.0, min(1.0, SENSOR_CONFIDENCE_FALLBACK)))


def adjusted_sensor_confidence(sensor_status: str | None, gas_status: str | None, base_confidence: float) -> float:
    if sensor_status is None:
        return 0.0
    if gas_status is None:
        return float(max(0.0, min(1.0, base_confidence)))
    if normalize_status(sensor_status) == normalize_status(gas_status):
        return float(max(0.0, min(1.0, base_confidence + GAS_SENSOR_AGREE_BONUS)))
    return float(max(0.0, min(1.0, base_confidence - GAS_SENSOR_DISAGREE_PENALTY)))


def fuse_freshness_status(
    vision_status: str,
    sensor_status: str | None,
    vision_confidence: float,
    sensor_confidence: float = 0.0,
) -> tuple[str, float]:
    """
    Vision-led fusion:
    - Vision has higher base weight
    - Sensor influence scales with sensor confidence
    """
    vision_normalized = normalize_status(vision_status)
    if sensor_status is None:
        return vision_normalized
    sensor_normalized = normalize_status(sensor_status)
    sensor_weight = max(0.0, SENSOR_FUSION_WEIGHT * max(0.0, min(1.0, sensor_confidence)))
    vision_weight = max(0.0, VISION_FUSION_WEIGHT)
    total_weight = max(vision_weight + sensor_weight, 1e-6)
    fused_score = (
        (vision_weight * _status_to_score(vision_normalized))
        + (sensor_weight * _status_to_score(sensor_normalized))
    ) / total_weight

    # Keep very confident vision classifications stable.
    if vision_confidence >= VISION_LOCK_CONFIDENCE:
        return vision_normalized, _status_to_score(vision_normalized)
    return _score_to_status(fused_score), fused_score


class GasSignalTracker:
    """
    Tracks MQ135 + MQ3 baseline and trend to infer freshness signal.
    """

    def __init__(self):
        self._mq135_baseline_samples: deque[float] = deque(maxlen=max(1, MQ135_BASELINE_WINDOW))
        self._mq3_baseline_samples: deque[float] = deque(maxlen=max(1, MQ135_BASELINE_WINDOW))
        self._mq135_recent_samples: deque[float] = deque(maxlen=max(1, MQ135_SMOOTHING_WINDOW))
        self._mq3_recent_samples: deque[float] = deque(maxlen=max(1, MQ135_SMOOTHING_WINDOW))
        self._mq135_baseline: float | None = None
        self._mq3_baseline: float | None = None
        self._candidate_status: str | None = None
        self._candidate_count = 0
        self._stable_status: str = "fresh"

    def _median(self, values: list[float]) -> float:
        ordered = sorted(values)
        n = len(ordered)
        mid = n // 2
        if n % 2 == 1:
            return float(ordered[mid])
        return float((ordered[mid - 1] + ordered[mid]) / 2.0)

    def baseline_ready(self) -> bool:
        return self._mq135_baseline is not None and self._mq3_baseline is not None

    def baseline_progress(self) -> tuple[int, int]:
        return len(self._mq135_baseline_samples), len(self._mq3_baseline_samples)

    def baselines(self) -> tuple[float | None, float | None]:
        return self._mq135_baseline, self._mq3_baseline

    def update(self, mq135_value: float | int | None, mq3_value: float | int | None) -> str | None:
        if mq135_value is None or mq3_value is None:
            return None
        current_mq135 = float(mq135_value)
        current_mq3 = float(mq3_value)
        if current_mq135 <= 0 or current_mq3 <= 0:
            return None

        self._mq135_recent_samples.append(current_mq135)
        self._mq3_recent_samples.append(current_mq3)
        smoothed_mq135 = self._median(list(self._mq135_recent_samples))
        smoothed_mq3 = self._median(list(self._mq3_recent_samples))

        if not self.baseline_ready():
            if self._mq135_baseline is None:
                self._mq135_baseline_samples.append(smoothed_mq135)
                if len(self._mq135_baseline_samples) >= max(1, MQ135_BASELINE_WINDOW):
                    self._mq135_baseline = self._median(list(self._mq135_baseline_samples))
            if self._mq3_baseline is None:
                self._mq3_baseline_samples.append(smoothed_mq3)
                if len(self._mq3_baseline_samples) >= max(1, MQ135_BASELINE_WINDOW):
                    self._mq3_baseline = self._median(list(self._mq3_baseline_samples))
            return None

        baseline_mq135 = max(self._mq135_baseline or 0.0, 1e-6)
        baseline_mq3 = max(self._mq3_baseline or 0.0, 1e-6)
        ratio_mq135 = smoothed_mq135 / baseline_mq135
        ratio_mq3 = smoothed_mq3 / baseline_mq3

        total_weight = max(MQ135_WEIGHT + MQ3_WEIGHT, 1e-6)
        combined_ratio = ((MQ135_WEIGHT * ratio_mq135) + (MQ3_WEIGHT * ratio_mq3)) / total_weight

        if combined_ratio >= MQ135_RATIO_SPOILED:
            candidate = "spoiled"
        elif combined_ratio >= MQ135_RATIO_AT_RISK:
            candidate = "at_risk"
        else:
            candidate = "fresh"

        if candidate == self._candidate_status:
            self._candidate_count += 1
        else:
            self._candidate_status = candidate
            self._candidate_count = 1

        if self._candidate_count >= max(1, MQ135_CONSECUTIVE_CONFIRMATIONS):
            self._stable_status = candidate
        return self._stable_status


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
 
 
def build_detection_record(
    item: dict,
    sensor_prediction: str | None = None,
    sensor_confidence: float = 0.0,
) -> tuple[dict, dict]:
    label = item.get("label", "fresh_food_item")
    confidence = float(item.get("confidence", 0.0))
    vision_status = parse_status(label)
    status, fused_score = fuse_freshness_status(vision_status, sensor_prediction, confidence, sensor_confidence)
    name = parse_food_name(label).replace("_", " ").strip().title()
    days = estimate_days_to_spoil(status, confidence)
    record = {
        "name": name,
        "category": "Produce",
        "freshness_status": status,
        "freshness_score": freshness_score(status, confidence),
        "confidence": round(confidence * 100, 2),
        "estimated_days_to_spoil": days,
        "storage_tips": storage_tips_for(status, name.lower()),
        "image_url": item.get("image_url"),
    }
    debug = {
        "item_name": name,
        "vision_status": vision_status,
        "vision_confidence": confidence,
        "sensor_status": sensor_prediction,
        "sensor_confidence": sensor_confidence,
        "final_status": status,
        "final_score": float(fused_score),
    }
    return record, debug
 
 
def _first_non_none(data: dict, keys: list[str]):
    for key in keys:
        value = data.get(key)
        if value is not None:
            return value
    return None


def run_cleanup_loop():
    """
    Background maintenance loop for periodic DB table cleanup.
    Uses a dedicated DB connection for thread-safe operation.
    """
    log = logging.getLogger("raspberrypi.cleanup")
    if not CLEANUP_ENABLED:
        log.info("Cleanup loop disabled")
        return
    if not DIRECT_DB_ENABLED:
        log.info("Cleanup loop disabled because DIRECT_DB_ENABLED=false")
        return
    if CLEANUP_INTERVAL_SECONDS <= 0:
        log.warning("Cleanup loop disabled due to invalid CLEANUP_INTERVAL_SECONDS=%s", CLEANUP_INTERVAL_SECONDS)
        return

    db: SupabaseClient | None = None
    try:
        db = SupabaseClient()
        log.info(
            "Cleanup loop started interval=%ss tables=%s",
            CLEANUP_INTERVAL_SECONDS,
            CLEANUP_TABLES,
        )
        while True:
            try:
                cleaned_count = db.cleanup_tables(CLEANUP_TABLES)
                log.info("Scheduled cleanup done: tables_cleaned=%s", cleaned_count)
            except Exception as ex:
                log.exception("Scheduled cleanup failed: %s", ex)
            time.sleep(CLEANUP_INTERVAL_SECONDS)
    except Exception as ex:
        log.exception("Cleanup loop startup failed: %s", ex)
    finally:
        if db:
            db.close()
 
 
class ManualTriggerState:
    def __init__(self) -> None:
        self._event = threading.Event()
        self._lock = threading.Lock()
        self._pending: dict | None = None
 
    def queue(self, source: str) -> None:
        with self._lock:
            self._pending = {"source": source, "triggered_at": datetime.now(timezone.utc).isoformat()}
            self._event.set()
 
    def wait(self, timeout_seconds: int) -> dict | None:
        if not self._event.wait(timeout=timeout_seconds):
            return None
        with self._lock:
            pending = self._pending
            self._pending = None
            self._event.clear()
            return pending
 
 
def start_manual_trigger_server(state: ManualTriggerState, log: logging.Logger) -> None:
    if not MANUAL_TRIGGER_ENABLED:
        log.info("Manual trigger API disabled")
        return
    if not MANUAL_TRIGGER_TOKEN:
        log.warning("Manual trigger API running without token protection")
 
    class ManualTriggerHandler(BaseHTTPRequestHandler):
        def _send_json(self, status: int, payload: dict) -> None:
            body = json.dumps(payload).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
 
        def do_POST(self) -> None:
            if self.path != "/trigger-run":
                self._send_json(404, {"ok": False, "error": "not_found"})
                return
            if MANUAL_TRIGGER_TOKEN:
                token = self.headers.get("X-Edge-Trigger-Token", "").strip()
                if token != MANUAL_TRIGGER_TOKEN:
                    log.warning("Manual trigger rejected due to invalid token")
                    self._send_json(401, {"ok": False, "error": "unauthorized"})
                    return
 
            source = "live-backend"
            raw_len = self.headers.get("Content-Length", "0").strip()
            try:
                body_len = int(raw_len or "0")
            except ValueError:
                body_len = 0
            if body_len > 0:
                try:
                    payload = json.loads(self.rfile.read(body_len).decode("utf-8"))
                    source = str(payload.get("source") or source)
                except Exception as ex:
                    log.warning("Manual trigger payload parse failed: %s", ex)
                    source = "live-backend"
 
            log.info("Manual trigger request accepted source=%s", source)
            state.queue(source=source)
            self._send_json(202, {"ok": True, "message": "manual trigger queued"})
 
        def do_GET(self) -> None:
            if self.path == "/health":
                self._send_json(200, {"status": "ok"})
                return
            self._send_json(404, {"ok": False, "error": "not_found"})
 
        def log_message(self, fmt: str, *args) -> None:
            log.debug("manual-trigger-server: " + fmt, *args)
 
    server = ThreadingHTTPServer((MANUAL_TRIGGER_HOST, MANUAL_TRIGGER_PORT), ManualTriggerHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    log.info("Manual trigger API listening on %s:%s", MANUAL_TRIGGER_HOST, MANUAL_TRIGGER_PORT)
 
 
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
    cleanup_thread = threading.Thread(target=run_cleanup_loop, daemon=True)
    sensor_thread.start()
    vision_thread.start()
    cleanup_thread.start()
    manual_trigger_state = ManualTriggerState()
    start_manual_trigger_server(manual_trigger_state, log)
    log.info("Raspberry Pi runtime started")
    last_sent_signature = None
    gas_tracker = GasSignalTracker()
 
    try:
        while True:
            manual_trigger = manual_trigger_state.wait(timeout_seconds=INGEST_INTERVAL_SECONDS)
            sensor_data = shared_state.get("sensor")
            vision_data = shared_state.get("vision")
            if sensor_data is None or vision_data is None:
                continue
            signature = (
                sensor_data.get("timestamp"),
                vision_data.get("timestamp"),
                tuple(obj.get("label") for obj in vision_data.get("detected_objects", [])),
            )
            if signature == last_sent_signature and manual_trigger is None:
                continue
            if manual_trigger:
                log.info("Manual run requested by source=%s", manual_trigger.get("source"))
 
            debug = sensor_data.get("debug", {})
            sensor_model_status = status_from_sensor_prediction(sensor_data.get("prediction"))
            base_sensor_conf = sensor_prediction_confidence(sensor_data, sensor_model_status)
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
            gas_sensor_status = gas_tracker.update(mq135_value, mq3_value)
            if not gas_tracker.baseline_ready():
                progress_135, progress_3 = gas_tracker.baseline_progress()
                log.info(
                    "Gas baseline calibration in progress (mq135=%s/%s mq3=%s/%s)",
                    progress_135,
                    max(1, MQ135_BASELINE_WINDOW),
                    progress_3,
                    max(1, MQ135_BASELINE_WINDOW),
                )
            elif gas_sensor_status:
                baseline_mq135, baseline_mq3 = gas_tracker.baselines()
                ratio_135 = float(mq135_value) / max(baseline_mq135 or 1.0, 1e-6)
                ratio_3 = float(mq3_value) / max(baseline_mq3 or 1.0, 1e-6)
                log.info(
                    "Gas trend status=%s mq135_ratio=%.3f mq3_ratio=%.3f mq135_base=%.2f mq3_base=%.2f",
                    gas_sensor_status,
                    ratio_135,
                    ratio_3,
                    baseline_mq135 or 0.0,
                    baseline_mq3 or 0.0,
                )
            effective_sensor_conf = adjusted_sensor_confidence(sensor_model_status, gas_sensor_status, base_sensor_conf)
            if sensor_model_status:
                log.info(
                    "Sensor model status=%s base_conf=%.3f effective_conf=%.3f gas_status=%s",
                    sensor_model_status,
                    base_sensor_conf,
                    effective_sensor_conf,
                    gas_sensor_status,
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
                        detection, inference_debug = build_detection_record(item, sensor_model_status, effective_sensor_conf)
                        food_id = db.insert_food_item(SUPABASE_USER_ID, detection, sensor_db)
                        db.insert_sensor_reading(SUPABASE_USER_ID, food_id, sensor_db)
                        db.insert_inference_log(
                            SUPABASE_USER_ID,
                            food_id,
                            {
                                **inference_debug,
                                "gas_trend_status": gas_sensor_status,
                                "mq135_value": payload["sensor"]["mq135_gas_value"],
                                "mq3_value": payload["sensor"]["mq3_gas_value"],
                                "temperature": payload["sensor"]["temperature"],
                                "humidity": payload["sensor"]["humidity"],
                                "captured_at": payload["captured_at"],
                            },
                        )
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