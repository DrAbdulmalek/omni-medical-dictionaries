#!/usr/bin/env bash
# ============================================================
# setup_manjaro.sh — Omni Medical Suite
# Simple automated setup for Manjaro / Arch Linux
# ============================================================
set -e

echo "=========================================="
echo "  Omni Medical Suite — Setup (Manjaro)"
echo "=========================================="
echo ""

# --- 1. System packages ---
echo "[1/5] Installing system packages..."
sudo pacman -S --needed --noconfirm \
    python python-pip \
    tesseract tesseract-data-ara tesseract-data-eng \
    poppler \
    git wget curl

# --- 2. Project directory ---
echo "[2/5] Creating project directory..."
PROJECT_DIR="$HOME/omni-medical-suite"
mkdir -p "$PROJECT_DIR"/{app,packages/preprocessors,packages/ocr,packages/collectors,scripts,tests,logs,downloads,colab,data}

# --- 3. Python virtual environment ---
echo "[3/5] Setting up Python virtual environment..."
cd "$PROJECT_DIR"
python -m venv venv
source venv/bin/activate

# --- 4. Python packages ---
echo "[4/5] Installing Python packages..."
pip install --upgrade pip
pip install -r requirements.txt

# --- 5. Init files ---
echo "[5/5] Creating package init files..."
touch packages/__init__.py
touch packages/preprocessors/__init__.py
touch packages/ocr/__init__.py
touch packages/collectors/__init__.py

echo ""
echo "=========================================="
echo "  Setup complete!"
echo "=========================================="
echo ""
echo "Next steps:"
echo "  cd $PROJECT_DIR"
echo "  source venv/bin/activate"
echo "  python app/advanced_review_app.py"
echo ""
echo "  # Or for glossary builder:"
echo "  python app/hitti_glossary_app.py"
echo ""
echo "  # Or for CLI extraction:"
echo "  python scripts/archive_book_extractor.py --help"
echo "=========================================="