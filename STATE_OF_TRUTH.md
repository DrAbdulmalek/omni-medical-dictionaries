# STATE_OF_TRUTH.md — OmniFile Processor / omni-medical-suite
# Last Updated: 2026-07-17

## Project Status

| Component | Status | Version | Notes |
|-----------|--------|---------|-------|
| scanner_fixer.py | Done | v2.1 | Multi-method rotation (OSD+Hough+Projection), auto-cleanup |
| advanced_review_app.py | Done | v2.1 | Single + Batch tabs, gr.State, manual save |
| requirements-scanner.txt | Done | — | Manjaro-ready |
| training/ | Stub | — | Fine-tuning scripts placeholder |
| logs/ | Auto | — | Auto-created at runtime |

## Architecture

```
omni-medical-suite/
  app/
    advanced_review_app.py     # Gradio UI (main entry point)
  packages/
    preprocessors/
      scanner_fixer.py         # Core engine v2.1
  training/                     # Fine-tuning scripts (future)
  logs/                         # Runtime logs
  downloads/                    # User-saved files
  requirements-scanner.txt     # Python deps
  STATE_OF_TRUTH.md            # This file
```

## Scanner Fixer v2.1 Features

### Rotation Detection (auto_rotate_strong)
- Tesseract OSD — weight 3 (primary)
- Hough Line Transform — weight 2
- Horizontal Projection Profile — weight 1
- Weighted voting for final angle decision

### Processing Pipeline
1. Auto-Rotate (multi-method)
2. Deskew (minAreaRect)
3. Denoise (Non-Local Means)
4. Contrast Fix (CLAHE)
5. Sharpen (Unsharp Mask)
6. Border Removal (content bounding box)

### Batch Mode
- Folder processing (recursive)
- Multi-page PDF (pdf2image + poppler)
- Random preview (Before/After pairs)
- ZIP export (manual save only)

### Error Handling
- Per-operation try/except with fallback to original
- Logging to file + console
- User-friendly error messages in UI

### Temp File Cleanup
- atexit handler cleans all temp directories
- Context-safe (no orphaned files)

## Manjaro Setup

```bash
# System packages
sudo pacman -S python-opencv tesseract poppler tesseract-data-ara tesseract-data-eng

# Python packages
cd omni-medical-suite
python -m venv venv
source venv/bin/activate
pip install -r requirements-scanner.txt

# Run
python app/advanced_review_app.py
```

## Design Decisions

1. **Manual save only** — No auto-save. User must click Save.
2. **gr.State for Before/After** — Stable, no file I/O until user saves.
3. **No automatic cleanup of downloads** — User controls saved files.
4. **Headless OpenCV** — No GUI dependency, works on servers.
5. **pdf2image requires poppler** — System package, not pip.