# FreshSense Edge AI Node (Raspberry Pi Only)

This folder now runs only the Raspberry Pi application.
No separate API backend is required inside `freshsense-edge-ai-node`.

## Structure

- `models/` -> real model files used on Pi
- `main.py` -> continuous runtime entrypoint
- `raspberrypi/sensors/sensor_detection.py` -> sensor + sensor model inference
- `raspberrypi/vision/yolo_detection.py` -> YOLO ONNX vision inference

## Required model files

Place these in `models/`:

- `best_pruned_quantized.onnx`
- `fruit_model.pkl`
- `scaler.pkl`
- `label_encoder.pkl`

Optional override:

```bash
FRESHSENSE_MODELS_DIR=/absolute/path/to/models
```

## Environment (`.env` in edge-ai-node root)

```bash
SUPABASE_USER_ID=<auth.users.id>
FRESHSENSE_API_URL=http://<your-backend-host>:8000/api/ingest
CAMERA_INDEX=0
DIRECT_DB_ENABLED=true
API_FORWARD_ENABLED=false
INGEST_INTERVAL_SECONDS=5
SUPABASE_STORAGE_BUCKET=food-images
CLEANUP_ENABLED=true
CLEANUP_INTERVAL_SECONDS=3600
CLEANUP_TABLES=notification_email_dispatches,notifications,sensor_readings,food_items
```

## Install + Run on Raspberry Pi

```bash
pip install -r requirements.txt
python main.py
```

The Pi app continuously reads sensors + camera, runs models, and posts data to `FRESHSENSE_API_URL`.

Default behavior now mirrors the previous simulation pipeline:
- upload per-item crop image to Supabase Storage
- upsert into `food_items`
- insert `sensor_readings` per detected item
- generate and insert `notifications`
- run scheduled table cleanup for configured tables (`profiles` is never cleaned)

`API_FORWARD_ENABLED=true` is optional if you also want to forward payloads to an ingest API.

## Runtime logs

Logs are persisted at:

```bash
logs/raspberrypi-runtime.log
```

Rotation is enabled (max ~2MB each, 5 backups).
Optional log level:

```bash
LOG_LEVEL=INFO
```

## Added from previous sim flow

- YOLO runtime now saves **cropped object images** under `captured_crops/`.
- Pi sender attempts **Supabase Storage upload** for each crop using `storage_client.py`.
- If upload is unavailable, it falls back to sending base64 image.
- Sensor loop supports fallback behavior from old `sensor_sim`:
  - `SENSOR_SIM_FALLBACK=true` (default) keeps app running if hardware read fails.
