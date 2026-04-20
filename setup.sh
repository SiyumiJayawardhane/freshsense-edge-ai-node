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

