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
MQ135_BASELINE_WINDOW=60
MQ135_SMOOTHING_WINDOW=5
MQ135_RATIO_AT_RISK=1.15
MQ135_RATIO_SPOILED=1.35
MQ135_CONSECUTIVE_CONFIRMATIONS=3
MQ135_WEIGHT=0.7
MQ3_WEIGHT=0.3
VISION_FUSION_WEIGHT=0.75
SENSOR_FUSION_WEIGHT=0.25
VISION_LOCK_CONFIDENCE=0.85
SENSOR_CONFIDENCE_FALLBACK=0.60
GAS_SENSOR_AGREE_BONUS=0.15
GAS_SENSOR_DISAGREE_PENALTY=0.20
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
- insert per-item fusion audit rows into `inference_logs` (if table exists)

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

## Store and visualize predictions

1) Create `inference_logs` table by running:

```bash
sql/inference_logs.sql
```

2) Edge node now writes one row per detected item with:
- vision status/confidence
- sensor model status/confidence (temp + humidity + MQ135 + MQ3 model)
- gas trend status
- final fused status/score

3) Example SQL for visualization:

```sql
-- Final class distribution
select final_status, count(*)
from public.inference_logs
group by final_status
order by count(*) desc;

-- Vision vs final comparison
select vision_status, final_status, count(*)
from public.inference_logs
group by vision_status, final_status
order by count(*) desc;

-- Recent timeline for one user
select captured_at, item_name, vision_status, sensor_status, gas_trend_status, final_status
from public.inference_logs
where user_id = '<your-user-id>'
order by captured_at desc
limit 200;
```
