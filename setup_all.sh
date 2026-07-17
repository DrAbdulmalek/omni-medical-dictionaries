#!/bin/bash
# ============================================================
# setup_all.sh — Omni Medical Suite — Full Setup
# Manjaro/Arch Linux — Fixed: no chromedriver (uses webdriver-manager)
# ============================================================
set -e

PROJECT_DIR="${1:-$HOME/omni-medical-suite}"
echo "Installing to: $PROJECT_DIR"

# --- 1. System dependencies (NO chromedriver — pip:webdriver-manager handles it) ---
echo "==> [1/5] Installing system packages..."
sudo pacman -S --needed --noconfirm \
    python python-pip \
    tesseract tesseract-data-ara tesseract-data-eng \
    poppler \
    git wget curl

# --- 2. Create project structure ---
echo "==> [2/5] Creating project structure..."
mkdir -p "$PROJECT_DIR"/{app,scripts,packages/preprocessors,packages/ocr,packages/collectors,tests,logs,downloads,colab,data,glossary_output}

# --- 3. Python virtual environment ---
echo "==> [3/5] Setting up Python environment..."
cd "$PROJECT_DIR"
python -m venv venv
source venv/bin/activate

# --- 4. Python packages (webdriver-manager auto-downloads chromedriver) ---
echo "==> [4/5] Installing Python packages..."
pip install --upgrade pip
pip install -r requirements.txt

# --- 5. Init files ---
echo "==> [5/5] Creating package init files..."
touch packages/__init__.py
touch packages/preprocessors/__init__.py
touch packages/ocr/__init__.py
touch packages/collectors/__init__.py

echo ""
echo "============================================"
echo "  Setup complete!"
echo "============================================"
echo ""
echo "Available commands:"
echo "  cd $PROJECT_DIR"
echo "  source venv/bin/activate"
echo ""
echo "  # Scanner Fixer UI (port 7860):"
echo "  python app/advanced_review_app.py"
echo ""
echo "  # Glossary Builder UI (port 7861):"
echo "  python app/hitti_glossary_app.py"
echo ""
echo "  # CLI extraction:"
echo "  python scripts/archive_book_extractor.py --help"
echo "============================================"