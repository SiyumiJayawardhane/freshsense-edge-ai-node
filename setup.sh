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
