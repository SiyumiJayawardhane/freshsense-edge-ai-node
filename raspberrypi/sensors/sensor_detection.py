import os
import random
import time
import logging
from datetime import datetime
from pathlib import Path

import adafruit_ads1x15.ads1115 as ADS
import adafruit_dht
import board
import busio
import joblib
import pandas as pd
from adafruit_ads1x15.analog_in import AnalogIn

BASE_DIR = Path(__file__).resolve().parents[2]
MODELS_DIR = Path(os.getenv("FRESHSENSE_MODELS_DIR", str(BASE_DIR / "models")))

MODEL_PATH = MODELS_DIR / "rf_model.pkl"
SCALER_PATH = MODELS_DIR / "scaler.pkl"
ENCODER_PATH = MODELS_DIR / "label_encoder.pkl"

model = joblib.load(MODEL_PATH)
scaler = joblib.load(SCALER_PATH)
label_encoder = joblib.load(ENCODER_PATH)

FEATURES = ["temp", "humidity", "mq135", "mq3"]

dht = adafruit_dht.DHT22(board.D4)
i2c = busio.I2C(board.SCL, board.SDA)
ads = ADS.ADS1115(i2c)
ads.gain = 1
mq135_sensor = AnalogIn(ads, 0)
mq3_sensor = AnalogIn(ads, 1)

USE_SIM_FALLBACK = os.getenv("SENSOR_SIM_FALLBACK", "true").lower() == "true"
DHT_READ_RETRIES = int(os.getenv("DHT_READ_RETRIES", "3"))
log = logging.getLogger("raspberrypi.sensor")

FEATURE_ALIASES = {
    "temp": ["temp", "temperature", "Temp", "Temperature"],
    "humidity": ["humidity", "Humidity"],
    "mq135": ["mq135", "MQ135", "mq135_gas_value", "MQ135_gas_value"],
    "mq3": ["mq3", "MQ3", "mq3_gas_value", "MQ3_gas_value"],
}


def read_sensor_data():
    # Read MQ sensors independently so gas values can still be real even if DHT fails.
    mq135_raw_ads = mq135_sensor.value
    mq3_raw_ads = mq3_sensor.value
    mq135_model_value = int(mq135_raw_ads)
    mq3_model_value = int(mq3_raw_ads)

    temperature = None
    humidity = None
    dht_error = None
    for _ in range(max(1, DHT_READ_RETRIES)):
        try:
            temperature = dht.temperature
            humidity = dht.humidity
            if temperature is not None and humidity is not None:
                break
        except Exception as ex:
            dht_error = ex
        time.sleep(0.2)

    if temperature is None or humidity is None:
        if USE_SIM_FALLBACK:
            simulated = _read_sensors_simulated()
            temperature = simulated["temperature"]
            humidity = simulated["humidity"]
            log.warning("DHT22 read failed, using simulated temp/humidity: %s", dht_error or "empty reading")
        else:
            raise ValueError(f"DHT22 reading failed: {dht_error}")

    sensor_input = {
        "temp": float(temperature),
        "humidity": float(humidity),
        "mq135": float(mq135_model_value),
        "mq3": float(mq3_model_value),
    }

    debug_info = {
        "temp": float(temperature),
        "humidity": float(humidity),
        "mq135_raw_ads": int(mq135_raw_ads),
        "mq3_raw_ads": int(mq3_raw_ads),
        "mq135_voltage": float(mq135_sensor.voltage),
        "mq3_voltage": float(mq3_sensor.voltage),
        "mq135_model_value": int(mq135_model_value),
        "mq3_model_value": int(mq3_model_value),
    }
    return sensor_input, debug_info


def predict_status(sensor_input):
    try:
        x = _build_scaler_input(sensor_input)
        x_scaled = scaler.transform(x)
        # Keep feature names after scaling to avoid sklearn warnings.
        x_scaled_df = pd.DataFrame(x_scaled, columns=list(x.columns))
        pred_encoded = model.predict(x_scaled_df)[0]
        pred_label = label_encoder.inverse_transform([pred_encoded])[0]

        prob_dict = None
        if hasattr(model, "predict_proba"):
            probs = model.predict_proba(x_scaled_df)[0]
            classes = label_encoder.classes_
            prob_dict = {str(classes[i]): float(probs[i]) for i in range(len(classes))}
        return pred_label, prob_dict
    except Exception as ex:
        # Never let schema mismatch crash the sensor thread.
        log.warning("Sensor model inference failed, using rule fallback: %s", ex)
        return _fallback_predict(sensor_input), None


def _build_scaler_input(sensor_input: dict) -> pd.DataFrame:
    scaler_features = getattr(scaler, "feature_names_in_", None)
    if scaler_features is None:
        return pd.DataFrame(
            [
                {
                    "temp": float(sensor_input.get("temp", 0.0)),
                    "humidity": float(sensor_input.get("humidity", 0.0)),
                    "mq135": float(sensor_input.get("mq135", 0.0)),
                    "mq3": float(sensor_input.get("mq3", 0.0)),
                }
            ],
            columns=FEATURES,
        )

    row = {}
    for feature in scaler_features:
        value = 0.0
        feature_text = str(feature)
        normalized = feature_text.lower()

        for canonical, aliases in FEATURE_ALIASES.items():
            if normalized == canonical or feature_text in aliases:
                raw = sensor_input.get(canonical)
                value = float(raw) if raw is not None else 0.0
                break

        row[feature_text] = value
    return pd.DataFrame([row], columns=list(scaler_features))


def _fallback_predict(sensor_input: dict) -> str:
    mq135 = float(sensor_input.get("mq135", 0.0))
    mq3 = float(sensor_input.get("mq3", 0.0))
    humidity = float(sensor_input.get("humidity", 0.0))
    temperature = float(sensor_input.get("temp", 0.0))

    # Conservative rule-based fallback when model/scaler schema does not match.
    if mq135 >= 26000 or mq3 >= 22000 or humidity >= 85:
        return "spoiled"
    if mq135 >= 18000 or mq3 >= 15000 or humidity >= 75 or temperature >= 31:
        return "at_risk"
    return "fresh"


def run_sensor_loop(shared_state):
    log.info("Sensor loop started")
    while True:
        try:
            sensor_input, debug_info = read_sensor_data()
            prediction, probabilities = predict_status(sensor_input)
            shared_state["sensor"] = {
                "prediction": prediction,
                "probabilities": probabilities,
                "debug": debug_info,
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            }
        except Exception as e:
            if USE_SIM_FALLBACK:
                # Full fallback only when MQ or entire read path fails.
                simulated = _read_sensors_simulated()
                prediction, probabilities = predict_status(
                    {
                        "temp": simulated["temperature"],
                        "humidity": simulated["humidity"],
                        "mq135": simulated["mq135_gas_value"],
                        "mq3": simulated["mq3_gas_value"],
                    }
                )
                shared_state["sensor"] = {
                    "prediction": prediction,
                    "probabilities": probabilities,
                    "debug": {
                        "temp": simulated["temperature"],
                        "humidity": simulated["humidity"],
                        "mq135_model_value": simulated["mq135_gas_value"],
                        "mq3_model_value": simulated["mq3_gas_value"],
                    },
                    "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                }
                log.warning("Real sensor read failed, simulated fallback active: %s", e)
            else:
                log.exception("Sensor read failed: %s", e)
        time.sleep(1)


def _read_sensors_simulated() -> dict:
    hour = datetime.now().hour
    temp_base = 24.0 if 8 <= hour <= 20 else 22.0
    temperature = round(temp_base + random.uniform(-2.0, 2.0), 1)
    humidity = round(random.uniform(52.0, 74.0), 1)
    mq135_value = random.randint(180, 520)
    mq3_value = random.randint(120, 460)
    return {
        "temperature": temperature,
        "humidity": humidity,
        "mq135_gas_value": mq135_value,
        "mq3_gas_value": mq3_value,
    }
