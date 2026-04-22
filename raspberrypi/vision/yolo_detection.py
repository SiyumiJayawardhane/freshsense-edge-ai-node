import cv2
import numpy as np
import time
import os
import onnxruntime as ort

MODEL_PATH = "models/best_pruned_quantized.onnx"
INPUT_WIDTH = 640
INPUT_HEIGHT = 640
CONF_THRESHOLD = 0.25
NMS_THRESHOLD = 0.45

SAVE_FOLDER = "captured_results"
CAMERA_INDEX = 0   # change to 1 if needed

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

def preprocess_for_model(frame_bgr):
    frame_rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
    img = cv2.resize(frame_rgb, (INPUT_WIDTH, INPUT_HEIGHT))
    img = img.astype(np.float32) / 255.0
    img = np.transpose(img, (2, 0, 1))
    img = np.expand_dims(img, axis=0)
    img = np.ascontiguousarray(img)
    return img

def decode_output(output, frame_w, frame_h):
    if len(output.shape) == 3:
        output = output[0]
        if output.shape[0] < output.shape[1]:
            output = output.transpose(1, 0)

    boxes = []
    scores = []
    class_ids = []

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

def draw_detections(frame_bgr, boxes, scores, class_ids):
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
            detected_objects.append({
                "label": label,
                "score": float(scores[i])
            })

            cv2.rectangle(frame_bgr, (x, y), (x + box_w, y + box_h), (0, 255, 0), 2)
            cv2.putText(
                frame_bgr,
                f"{label}: {scores[i]:.2f}",
                (x, max(20, y - 10)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.6,
                (0, 255, 0),
                2
            )

    return frame_bgr, detected_objects

def run_vision_loop(shared_state):
    print("[VISION] Loading model...")
    session = ort.InferenceSession(
        MODEL_PATH,
        providers=["CPUExecutionProvider"]
    )
    input_name = session.get_inputs()[0].name
    output_names = [output.name for output in session.get_outputs()]
    print("[VISION] Model loaded")

    cap = cv2.VideoCapture(CAMERA_INDEX)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

    if not cap.isOpened():
        raise RuntimeError(f"Could not open webcam at index {CAMERA_INDEX}")

    time.sleep(2)
    count = 0

    try:
        while True:
            ok, frame_bgr = cap.read()
            if not ok:
                print("[VISION ERROR] Failed to capture image")
                time.sleep(1)
                continue

            h, w = frame_bgr.shape[:2]

            input_tensor = preprocess_for_model(frame_bgr)
            outputs = session.run(output_names, {input_name: input_tensor})
            output = outputs[0]

            boxes, scores, class_ids = decode_output(output, w, h)
            annotated_frame, detected_objects = draw_detections(frame_bgr.copy(), boxes, scores, class_ids)

            timestamp = time.strftime("%Y%m%d_%H%M%S")
            filename = os.path.join(SAVE_FOLDER, f"capture_{timestamp}_{count:04d}.jpg")
            cv2.imwrite(filename, annotated_frame)

            shared_state["vision"] = {
                "detected_objects": detected_objects,
                "saved_image": filename,
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
            }

            print("\n[VISION]")
            if detected_objects:
                for obj in detected_objects:
                    print(f"  Detected: {obj['label']} ({obj['score']:.2f})")
            else:
                print("  No objects detected")

            print(f"  Saved: {filename}")

            count += 1
            time.sleep(1)

    finally:
        cap.release()
        print("[VISION] Webcam released")