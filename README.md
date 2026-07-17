# OmniFile Processor — Scanner Fixer v2.1

Smart scanner image correction engine for scanned documents.

## Features

- **Auto-Rotate**: Multi-method detection (Tesseract OSD + Hough Lines + Projection Profile)
- **Deskew**: MinAreaRect contour analysis
- **Denoise**: Non-Local Means
- **Sharpen**: Unsharp Mask
- **Contrast Fix**: CLAHE
- **Border Removal**: Content bounding box
- **Batch Mode**: Folder + multi-page PDF + ZIP export
- **Gradio UI**: Before/After preview, manual save only

## Quick Start (Manjaro)

```bash
# System packages
sudo pacman -S python-opencv tesseract poppler tesseract-data-ara tesseract-data-eng

# Python
python -m venv venv
source venv/bin/activate
pip install -r requirements-scanner.txt

# Run
python app/advanced_review_app.py
# Open http://localhost:7860
```

## One-Script Setup

```bash
chmod +x setup.sh
./setup.sh
```

## Project Structure

```
omni-medical-suite/
  app/advanced_review_app.py      # Gradio UI
  packages/preprocessors/
    scanner_fixer.py              # Core engine v2.1
  requirements-scanner.txt       # Python deps
  setup.sh                        # One-script installer
  STATE_OF_TRUTH.md              # Architecture & status
```

## License

MIT