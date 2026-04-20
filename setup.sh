#!/bin/bash
# ─────────────────────────────────────────────────────────────────────────────
# FreshGuard Setup Script for Raspberry Pi 4 Model B
# Run as: chmod +x setup.sh && ./setup.sh
# ─────────────────────────────────────────────────────────────────────────────

set -e  # exit on any error

INSTALL_DIR="/home/pi/freshguard"
VENV_DIR="$INSTALL_DIR/venv"

echo "================================================"
echo "  FreshGuard Setup"
echo "================================================"

# ── 1. System dependencies ────────────────────────────────────────────────────
echo "[1/6] Installing system packages..."
sudo apt-get update -q
sudo apt-get install -y -q \
    python3 \
    python3-pip \
    python3-venv \
    libcamera-apps \
    libjpeg-dev \
    zlib1g-dev \
    libfreetype6-dev

# ── 2. Create install directory ───────────────────────────────────────────────
echo "[2/6] Setting up directory structure..."
mkdir -p "$INSTALL_DIR"
mkdir -p "$INSTALL_DIR/logs"
mkdir -p "$INSTALL_DIR/images"

# Copy project files
cp -r ./* "$INSTALL_DIR/"

# ── 3. Python virtual environment ─────────────────────────────────────────────
echo "[3/6] Creating Python virtual environment..."
python3 -m venv "$VENV_DIR"
source "$VENV_DIR/bin/activate"

# ── 4. Install Python packages ─────────────────────────────────────────────────
echo "[4/6] Installing Python packages..."
pip install --upgrade pip -q
pip install -r "$INSTALL_DIR/requirements.txt" -q

# ── 5. Environment file ────────────────────────────────────────────────────────
echo "[5/6] Checking .env file..."
if [ ! -f "$INSTALL_DIR/.env" ]; then
    cp "$INSTALL_DIR/.env.example" "$INSTALL_DIR/.env"
    echo ""
    echo "    .env file created at $INSTALL_DIR/.env"
    echo "    Please fill in your Supabase credentials before starting:"
    echo "      nano $INSTALL_DIR/.env"
    echo ""
fi

# ── 6. Systemd service & timer ─────────────────────────────────────────────────
echo "[6/6] Installing systemd service and timer..."

# Write the service file
sudo bash -c "cat > /etc/systemd/system/freshguard.service" << 'EOF'
[Unit]
Description=FreshGuard Food Freshness Monitor
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
User=pi
WorkingDirectory=/home/pi/freshguard
ExecStart=/home/pi/freshguard/venv/bin/python /home/pi/freshguard/main.py
StandardOutput=journal
StandardError=journal
EnvironmentFile=/home/pi/freshguard/.env

[Install]
WantedBy=multi-user.target
EOF

# Write the timer file
sudo bash -c "cat > /etc/systemd/system/freshguard.timer" << 'EOF'
[Unit]
Description=Run FreshGuard every 6 hours
Requires=freshguard.service
