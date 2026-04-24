import os
import time
import logging
from pathlib import Path

import cv2
import numpy as np
import onnxruntime as ort

BASE_DIR = Path(__file__).resolve().parents[2]
MODELS_DIR = Path(os.getenv("FRESHSENSE_MODELS_DIR", str(BASE_DIR / "models")))

MODEL_PATH = str(MODELS_DIR / "best_pruned_quantized.onnx")
INPUT_WIDTH = 640
INPUT_HEIGHT = 640
CONF_THRESHOLD = 0.25
NMS_THRESHOLD = 0.45

SAVE_FOLDER = str(BASE_DIR / "captured_results")
CROPS_FOLDER = str(BASE_DIR / "captured_crops")
CAMERA_INDEX = int(os.getenv("CAMERA_INDEX", "0"))

CLASS_NAMES = [
    "fresh_banana",
    "atrisk_banana",
    "spoiled_banana",
    "fresh_cucumber",
    "atrisk_cucumber",
    "spoiled_cucumber",
    "fresh_tomato",
    "atrisk_tomato",
    "spoiled_tomato",
]

os.makedirs(SAVE_FOLDER, exist_ok=True)
os.makedirs(CROPS_FOLDER, exist_ok=True)
log = logging.getLogger("raspberrypi.vision")

STATUS_COLORS = {
    "fresh": (0, 200, 0),      # green
    "atrisk": (0, 215, 255),   # yellow/orange
    "at_risk": (0, 215, 255),  # yellow/orange
    "spoiled": (0, 0, 255),    # red
}


def _color_for_label(label: str) -> tuple[int, int, int]:
    normalized = (label or "").strip().lower()
    status = normalized.split("_", 1)[0] if "_" in normalized else normalized
    return STATUS_COLORS.get(status, (255, 255, 255))


def preprocess_for_model(frame_bgr):
    frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
    img = cv2.resize(frame_rgb, (INPUT_WIDTH, INPUT_HEIGHT)).astype(np.float32) / 255.0
    img = np.transpose(img, (2, 0, 1))
    img = np.expand_dims(img, axis=0)
    return np.ascontiguousarray(img)


def decode_output(output, frame_w, frame_h):
    if len(output.shape) == 3:
        output = output[0]
        if output.shape[0] < output.shape[1]:
            output = output.transpose(1, 0)

    boxes, scores, class_ids = [], [], []
    x_factor = frame_w / INPUT_WIDTH
    y_factor = frame_h / INPUT_HEIGHT

    for row in output:
        if len(row) < 6:
            continue
        cx, cy, bw, bh = row[:4]
        objectness = float(row[4])
        class_scores = row[5:]
        if len(class_scores) == 0:
            continue
        class_id = int(np.argmax(class_scores))
        class_score = float(class_scores[class_id])
        score = objectness * class_score
        if score < CONF_THRESHOLD:
            continue

        x = int((cx - bw / 2) * x_factor)
        y = int((cy - bh / 2) * y_factor)
        box_w = int(bw * x_factor)
        box_h = int(bh * y_factor)
        boxes.append([x, y, box_w, box_h])
        scores.append(score)
        class_ids.append(class_id)

    return boxes, scores, class_ids


def draw_detections(frame_bgr, boxes, scores, class_ids, frame_index: int):
    h, w = frame_bgr.shape[:2]
    indices = cv2.dnn.NMSBoxes(boxes, scores, CONF_THRESHOLD, NMS_THRESHOLD)
    detected_objects = []

    if len(indices) > 0:
        for i in indices.flatten():
            x, y, box_w, box_h = boxes[i]
            x = max(0, x)
            y = max(0, y)
            box_w = max(0, min(box_w, w - x))
            box_h = max(0, min(box_h, h - y))

            label = CLASS_NAMES[class_ids[i]] if class_ids[i] < len(CLASS_NAMES) else str(class_ids[i])
            crop_file = os.path.join(CROPS_FOLDER, f"crop_{int(time.time())}_{frame_index:04d}_{i}.jpg")
            crop = frame_bgr[y : y + box_h, x : x + box_w]
            if crop.size > 0:
                cv2.imwrite(crop_file, crop)
            else:
                crop_file = None

            color = _color_for_label(label)
            detected_objects.append({"label": label, "score": float(scores[i]), "crop_path": crop_file})
            cv2.rectangle(frame_bgr, (x, y), (x + box_w, y + box_h), color, 2)
            cv2.putText(
                frame_bgr,
                f"{label}: {scores[i]:.2f}",
                (x, max(20, y - 10)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.6,
                color,
                2,
            )

    return frame_bgr, detected_objects


def run_vision_loop(shared_state):
    log.info("Loading vision model from %s", MODEL_PATH)
    session = ort.InferenceSession(MODEL_PATH, providers=["CPUExecutionProvider"])
    input_name = session.get_inputs()[0].name
    output_names = [output.name for output in session.get_outputs()]
    log.info("Vision model loaded")

    cap = cv2.VideoCapture(CAMERA_INDEX)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
    if not cap.isOpened():
        raise RuntimeError(f"Could not open webcam at index {CAMERA_INDEX}")
    log.info("Camera opened at index %s", CAMERA_INDEX)

    count = 0
    try:
        while True:
            ok, frame_bgr = cap.read()
            if not ok:
                log.warning("Failed to capture image frame")
                time.sleep(1)
                continue

            h, w = frame_bgr.shape[:2]
            input_tensor = preprocess_for_model(frame_bgr)
            output = session.run(output_names, {input_name: input_tensor})[0]
            boxes, scores, class_ids = decode_output(output, w, h)
            annotated_frame, detected_objects = draw_detections(frame_bgr.copy(), boxes, scores, class_ids, count)

            timestamp = time.strftime("%Y%m%d_%H%M%S")
            filename = os.path.join(SAVE_FOLDER, f"capture_{timestamp}_{count:04d}.jpg")
            cv2.imwrite(filename, annotated_frame)

            shared_state["vision"] = {
                "detected_objects": detected_objects,
                "saved_image": filename,
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            }
            count += 1
            time.sleep(1)
    finally:
        cap.release()
        log.info("Camera released")
