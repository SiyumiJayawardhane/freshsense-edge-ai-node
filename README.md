# \# 🍌 Smart Freshness Detection System (Backend)

# 

# \## 📌 Overview

# 

# This project is a \*\*backend system for an AI + IoT-based freshness detection platform\*\*.

# 

# It simulates and processes:

# 

# \* 🌡️ Environmental sensor data (DHT22, MQ135, MQ3)

# \* 🤖 AI model outputs (YOLO – fruit freshness detection)

# \* ☁️ Cloud storage via Supabase

# 

# The system is designed to run on a \*\*Raspberry Pi 4B (2GB)\*\* and supports \*\*multi-user, multi-device environments\*\*.

# 

# \---

# 

# \## 🧠 Architecture

# 

# ```

# \[Sensors / Simulation]

# &#x20;       ↓

# \[Python Backend Script]

# &#x20;       ↓

# \[Supabase Database]

# &#x20;       ↑

# \[AI Agent via MCP (Optional)]

# ```

# 

# \---

# 

# \## ⚙️ Features

# 

# \* ✅ Simulated sensor data (temperature, humidity, gas levels)

# \* ✅ Simulated YOLO output (fresh / rotten classification)

# \* ✅ Device-specific data tracking

# \* ✅ User-based data segregation

# \* ✅ Automatic data logging every 6 hours

# \* ✅ Supabase integration

# \* ✅ Ready for real hardware integration

# 

# \---

# 

# \## 🧩 Tech Stack

# 

# \* Python 3.x

# \* Supabase (PostgreSQL + API)

# \* Cron (task scheduling)

# \* Virtual Environment (venv)

# 

# \---

# 

# \## 📁 Project Structure

# 

# ```

# backend/

# │

# ├── main.py              # Main execution script

# ├── .env                # Environment variables

# ├── requirements.txt    # Python dependencies

# └── README.md

# ```

# 

# \---

# 

# \## 🔐 Environment Variables

# 

# Create a `.env` file in the root directory:

# 

# ```

# SUPABASE\_URL=your\_supabase\_url

# SUPABASE\_KEY=your\_supabase\_anon\_key

# 

# DEVICE\_ID=device\_001

# USER\_ID=user\_123

# ```

# 

# \---

# 

# \## 📦 Installation

# 

# ```bash

# \# Clone repository

# git clone <your-repo-url>

# cd backend

# 

# \# Create virtual environment

# python3 -m venv yolo-env

# source yolo-env/bin/activate

# 

# \# Install dependencies

# pip install -r requirements.txt

# ```

# 

# \---

# 

# \## 📜 requirements.txt

# 

# ```

# supabase

# python-dotenv

# ```

# 

# \---

# 

# \## 🚀 Running the Project

# 

# ```bash

# python main.py

# ```

# 

# \---

# 

# \## ⏱️ Scheduling (Run Every 6 Hours)

# 

# Edit cron jobs:

# 

# ```bash

# crontab -e

# ```

# 

# Add:

# 

# ```

# 0 \*/6 \* \* \* /usr/bin/python3 /home/pi/backend/main.py

# ```

# 

# \---

# 

# \## 🧪 Simulation Logic

# 

# \### Sensor Simulation

# 

# \* Temperature: 25°C – 35°C

# \* Humidity: 50% – 80%

# \* MQ135 (Air Quality): 200 – 600

# \* MQ3 (Alcohol): 50 – 300

# 

# \### YOLO Simulation

# 

# ```

# banana → fresh / rotten

# cucumber → fresh / rotten

# ```

# 

# \---

# 

# \## 🧠 Sample Payload

# 

# ```json

# {

# &#x20; "device\_id": "device\_001",

# &#x20; "user\_id": "user\_123",

# &#x20; "timestamp": "2026-04-19T10:00:00Z",

# &#x20; "temperature": 30.5,

# &#x20; "humidity": 65.2,

# &#x20; "mq135": 420,

# &#x20; "mq3": 120,

# &#x20; "item": "banana",

# &#x20; "status": "fresh"

# }

# ```

# 

# \---

# 

# \## 🗄️ Database Schema (Supabase)

# 

# ```sql

# CREATE TABLE readings (

# &#x20; id BIGSERIAL PRIMARY KEY,

# &#x20; device\_id TEXT,

# &#x20; user\_id TEXT,

# &#x20; timestamp TIMESTAMP,

# &#x20; temperature FLOAT,

# &#x20; humidity FLOAT,

# &#x20; mq135 INTEGER,

# &#x20; mq3 INTEGER,

# &#x20; item TEXT,

# &#x20; status TEXT

# );

# ```

# 

# \---

# 

# \## 🔌 Future Hardware Integration

# 

# Replace simulation functions with real sensor logic:

# 

# | Component  | Replace Function   |

# | ---------- | ------------------ |

# | DHT22      | `simulate\_dht22()` |

# | MQ Sensors | `simulate\_mq()`    |

# | YOLO Model | `simulate\_yolo()`  |

# 

# \---

# 

# \## 🤖 AI Agent Integration (MCP)

# 

# Supports integration with AI agents via MCP for:

# 

# \* Data querying

# \* Pattern detection

# \* Alerts

# \* Analytics

# 

# \---

# 

# \## 📈 Future Improvements

# 

# \* 🔔 Real-time alerts (SMS / WhatsApp)

# \* 📊 Dashboard (React + Supabase)

# \* 🎥 Live camera + YOLO integration

# \* 📡 MQTT / IoT communication layer

# \* 🔐 Device authentication system

# 

# \---

# 

# \## 🏁 Summary

# 

# This backend provides a \*\*complete simulation and data pipeline\*\* for:

# 

# \* AI-based freshness detection

# \* IoT sensor integration

# \* Cloud-based storage and analysis

# 

# Designed to be:

# 

# \* Lightweight ⚡

# \* Scalable 📈

# \* Hardware-ready 🔌

# 

# \---

# 

# \## 👨‍💻 Author

# 

# Your Team / Project Name

# 

# \---



