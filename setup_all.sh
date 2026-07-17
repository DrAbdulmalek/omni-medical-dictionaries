#!/bin/bash
# Omni Hitti Complete - Full Setup Script
# Creates entire project structure on Manjaro/Arch
set -e

PROJECT_DIR="${1:-$HOME/omni-hitti-complete}"
echo "Installing to: $PROJECT_DIR"

# 1. System dependencies
echo "==> Installing system packages..."
sudo pacman -S --needed --noconfirm python python-pip tesseract tesseract-data-ara tesseract-data-eng poppler git wget curl chromium chromedriver

# 2. Create structure
echo "==> Creating project structure..."
mkdir -p "$PROJECT_DIR"/{app,scripts,packages/preprocessors,training,logs,downloads,glossary_output}
cd "$PROJECT_DIR"

# 3. Python environment
echo "==> Setting up Python environment..."
python -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install gradio Pillow opencv-python-headless pytesseract requests img2pdf numpy selenium webdriver-manager

# 4. Create __init__.py files
touch packages/__init__.py
touch packages/preprocessors/__init__.py

echo "==> Setup complete!"
echo ""
echo "Next: Copy the Python files (scanner_fixer.py, advanced_review_app.py, hitti_glossary_app.py, archive_book_extractor.py) into their folders"
echo "Then run: source venv/bin/activate && python app/advanced_review_app.py"