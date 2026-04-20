"""
sensor_sim.py - Simulates DHT22 (temperature/humidity) and MQ gas sensor.

When real sensors are wired up, replace _read_dht() and _read_mq()
with actual GPIO/Adafruit_DHT calls.

Real DHT22 example (uncomment when hardware is ready):
    import Adafruit_DHT
    sensor = Adafruit_DHT.DHT22
    humidity, temperature = Adafruit_DHT.read_retry(sensor, DHT_GPIO_PIN)

Real MQ sensor example (MQ-135 via MCP3008 ADC):
    import spidev
    spi = spidev.SpiDev()
    spi.open(0, 0)
    gas_value = spi.xfer2([1, (8 + channel) << 4, 0])[1] & 3) << 8 | ...
"""

import random
import logging
from datetime import datetime

log = logging.getLogger(__name__)

# GPIO pin config (for when real hardware is connected)
DHT_GPIO_PIN = 4   # BCM pin 4
MQ_SPI_CHANNEL = 0  # MCP3008 channel 0


def read_sensors() -> dict:
    """
    Returns simulated sensor readings.
    Swap internals with real GPIO reads when hardware is ready.
    """
    temperature = _read_temperature()
    humidity = _read_humidity()
    gas_value = _read_gas()

    log.info(f"[SIMULATED] Temp={temperature}°C, Humidity={humidity}%, Gas={gas_value}")

    return {
        "temperature": temperature,
        "humidity": humidity,
        "gas_value": gas_value,
    }


def _read_temperature() -> float:
    """
    Simulates DHT22 temperature in Celsius.
    Real range in a fridge: 2–8°C | Room: 22–30°C
    Simulates a mixed environment (some fridge, some room).
    """
    # Simulate slightly realistic variation across the day
    hour = datetime.now().hour
    base = 24.0 if 8 <= hour <= 20 else 22.0  # slightly cooler at night
    noise = random.uniform(-2.0, 2.0)
    return round(base + noise, 1)


def _read_humidity() -> float:
    """
    Simulates DHT22 relative humidity (%).
    Kitchen/storage: typically 50–75%
    """
    return round(random.uniform(52.0, 74.0), 1)


