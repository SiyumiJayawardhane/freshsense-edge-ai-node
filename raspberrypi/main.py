import threading
import time
from sensors.sensor_detection import run_sensor_loop
from vision.yolo_prediction import run_vision_loop

def main():
    shared_state = {
        "sensor": None,
        "vision": None
    }

    sensor_thread = threading.Thread(
        target=run_sensor_loop,
        args=(shared_state,),
        daemon=True
    )

    vision_thread = threading.Thread(
        target=run_vision_loop,
        args=(shared_state,),
        daemon=True
    )

    sensor_thread.start()
    vision_thread.start()

    print("System started. Sensor + Vision running together.\nPress Ctrl+C to stop.\n")

    try:
        while True:
            time.sleep(1)

            sensor_data = shared_state.get("sensor")
            vision_data = shared_state.get("vision")

            print("\n========== COMBINED STATUS ==========")

            if sensor_data is not None:
                print(f"Sensor Prediction : {sensor_data['prediction']}")
            else:
                print("Sensor Prediction : Not available")

            if vision_data is not None and vision_data["detected_objects"]:
                labels = [obj["label"] for obj in vision_data["detected_objects"]]
                print("Vision Detection  :", ", ".join(labels))
            else:
                print("Vision Detection  : No objects detected")

            print("=====================================\n")

    except KeyboardInterrupt:
        print("\nStopped by user.")

if __name__ == "__main__":
    main()