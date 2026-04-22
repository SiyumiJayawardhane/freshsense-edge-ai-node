import time
import joblib
import pandas as pd
import board
import busio
import adafruit_dht
import adafruit_ads1x15.ads1115 as ADS
from adafruit_ads1x15.analog_in import AnalogIn

# ============================================
# MODEL FILES
# ============================================
MODEL_PATH = "models/fruit_model.pkl"
SCALER_PATH = "models/scaler.pkl"
ENCODER_PATH = "models/label_encoder.pkl"

model = joblib.load(MODEL_PATH)
scaler = joblib.load(SCALER_PATH)
label_encoder = joblib.load(ENCODER_PATH)

FEATURES = ["temp", "humidity", "mq135", "mq3"]

# ============================================
# SENSOR SETUP
# ============================================
dht = adafruit_dht.DHT22(board.D4)

i2c = busio.I2C(board.SCL, board.SDA)
ads = ADS.ADS1115(i2c)
ads.gain = 1

mq135_sensor = AnalogIn(ads, 0)   # A0
mq3_sensor = AnalogIn(ads, 1)     # A1

# ============================================
# ADS1115 -> ESP32 STYLE MAPPING
# Adjust if needed later
# ============================================
ADS_MIN = 0
ADS_MAX = 32767

def ads_to_esp32(raw_ads, ads_min=ADS_MIN, ads_max=ADS_MAX):
    raw_ads = max(ads_min, min(raw_ads, ads_max))
    return int((raw_ads - ads_min) * 4095 / (ads_max - ads_min))

# ============================================
# READ SENSOR DATA
# ============================================
def read_sensor_data():
    temperature = dht.temperature
    humidity = dht.humidity

    if temperature is None or humidity is None:
        raise ValueError("DHT22 reading failed")

    mq135_raw_ads = mq135_sensor.value
    mq3_raw_ads = mq3_sensor.value

    mq135_model_value = ads_to_esp32(mq135_raw_ads)
    mq3_model_value = ads_to_esp32(mq3_raw_ads)

    sensor_input = {
        "temp": float(temperature),
        "humidity": float(humidity),
        "mq135": float(mq135_model_value),
        "mq3": float(mq3_model_value)
    }

    debug_info = {
        "temp": float(temperature),
        "humidity": float(humidity),
        "mq135_raw_ads": int(mq135_raw_ads),
        "mq3_raw_ads": int(mq3_raw_ads),
        "mq135_voltage": float(mq135_sensor.voltage),
        "mq3_voltage": float(mq3_sensor.voltage),
        "mq135_model_value": int(mq135_model_value),
        "mq3_model_value": int(mq3_model_value)
    }

    return sensor_input, debug_info

# ============================================
# PREDICT
# ============================================
def predict_status(sensor_input):
    df = pd.DataFrame([sensor_input])
    X = df[FEATURES]

    X_scaled = scaler.transform(X)

    pred_encoded = model.predict(X_scaled)[0]
    pred_label = label_encoder.inverse_transform([pred_encoded])[0]

    prob_dict = None
    if hasattr(model, "predict_proba"):
        probs = model.predict_proba(X_scaled)[0]
        classes = label_encoder.classes_
        prob_dict = {
            str(classes[i]): float(probs[i])
            for i in range(len(classes))
        }

    return pred_label, prob_dict

# ============================================
# THREAD FUNCTION
# ============================================
def run_sensor_loop(shared_state):
    print("[SENSOR] Sensor loop started")

    while True:
        try:
            sensor_input, debug_info = read_sensor_data()
            prediction, probabilities = predict_status(sensor_input)

            shared_state["sensor"] = {
                "prediction": prediction,
                "probabilities": probabilities,
                "debug": debug_info,
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
            }

            print("\n[SENSOR]")
            print(f"  Temp            : {debug_info['temp']:.2f} C")
            print(f"  Humidity        : {debug_info['humidity']:.2f} %")
            print(f"  MQ135 ADS Raw   : {debug_info['mq135_raw_ads']}")
            print(f"  MQ135 Voltage   : {debug_info['mq135_voltage']:.4f} V")
            print(f"  MQ135 Model Val : {debug_info['mq135_model_value']}")
            print(f"  MQ3 ADS Raw     : {debug_info['mq3_raw_ads']}")
            print(f"  MQ3 Voltage     : {debug_info['mq3_voltage']:.4f} V")
            print(f"  MQ3 Model Val   : {debug_info['mq3_model_value']}")
            print(f"  Prediction      : {prediction}")

            if probabilities is not None:
                print("  Probabilities:")
                for label, prob in probabilities.items():
                    print(f"    {label}: {prob:.4f}")

            time.sleep(1)

        except Exception as e:
            print("[SENSOR ERROR]", e)
            time.sleep(1)