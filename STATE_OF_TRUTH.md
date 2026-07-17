# STATE_OF_TRUTH.md — Omni Medical Suite
# Last Updated: 2026-07-18

## Project Status

| Component | Status | Version | Notes |
|-----------|--------|---------|-------|
| scanner_fixer.py | Done | v2.1 | Multi-method rotation (OSD+Hough+Projection), auto-cleanup |
| advanced_review_app.py | Done | v2.2 | 4 tabs: Single + Batch + Archive Extractor + Glossary Search |
| hitti_glossary_app.py | Done | v1.0 | Standalone glossary builder (port 7861) |
| archive_book_extractor.py | Done | v2.0 | IIIF + Selenium + Manual modes |
| ocr_engine.py | Done | v1.0 | Multi-engine OCR (Tesseract + EasyOCR + PaddleOCR) |
| glossary_parser.py | Done | v1.0 | 7-pattern bilingual glossary parser |
| archive_book_downloader.py | Done | v1.0 | Archive.org IIIF downloader + SQLite storage |
| hf_space_app.py | Done | v3.0 | HF Space: 5 OCR models + Model Comparison + Fine-tuning |
| setup.sh | Done | — | One-script installer (Scanner only) |
| setup_all.sh | Done | — | Full setup (fixed: no chromedriver, uses webdriver-manager) |
| setup_manjaro.sh | Done | — | Simple Manjaro setup |
| requirements.txt | Done | — | Complete dependencies |
| requirements-scanner.txt | Done | — | Scanner-only dependencies |
| tests/test_scanner_fixer.py | Done | — | Unit tests (pytest) |
| colab/Omni_Hitti_Complete_Colab.ipynb | Done | — | 10-cell Colab notebook |

## Architecture

```
omni-medical-suite/
  app/
    advanced_review_app.py          # Main Gradio UI (4 tabs, port 7860)
    hitti_glossary_app.py           # Standalone glossary builder (port 7861)
    hf_space_app.py                 # HF Space app (5 OCR models)
  packages/
    preprocessors/
      scanner_fixer.py              # Core engine v2.1
    ocr/
      ocr_engine.py                 # Multi-engine OCR
    collectors/
      archive_book_downloader.py    # Archive.org IIIF downloader
      glossary_parser.py            # 7-pattern glossary parser
  scripts/
    archive_book_extractor.py       # CLI v2.0 (IIIF + Selenium + Manual)
    archive-downloader.user.js      # Tampermonkey script reference
  tests/
    test_scanner_fixer.py           # Unit tests
  colab/
    Omni_Hitti_Complete_Colab.ipynb # Google Colab notebook
  data/                             # Runtime data (databases)
  logs/                             # Runtime logs
  downloads/                        # User-saved files
  glossary_output/                  # Glossary extraction output
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

## Archive.org Integration

### Three extraction modes:
1. **IIIF API** — Fastest, no browser needed
2. **Selenium** — Fallback when IIIF fails
3. **Manual** — User provides pre-downloaded pages

### Glossary Extraction (7 patterns):
1. EN->AR comma/semicolon separator
2. AR->EN comma/semicolon separator
3. Dictionary bold format (ALL CAPS — definition)
4. Colon separator (term : translation)
5. Numbered entries (1. term — translation)
6. Table format
7. Parentheses format

### Export formats:
- JSON (with metadata)
- CSV (UTF-8 BOM for Excel)
- TXT (formatted)
- SQL (INSERT statements)
- PDF (via img2pdf)

## Gradio UI Tabs

### Tab 1: Single Image
- Upload, preview Before/After via gr.State
- Individual pipeline step toggles
- Manual save only (no auto-save)

### Tab 2: Batch Mode
- Folder or PDF input
- Random preview (Before/After gallery)
- Save All as ZIP (manual)

### Tab 3: Archive Extractor
- Book URL, email/password
- Page range, mode selection
- IIIF/Selenium/Manual modes

### Tab 4: Glossary Search
- Bidirectional search (EN->AR, AR->EN)
- Statistics display
- Export all as ZIP

## Manjaro Setup

```bash
# Quick setup
chmod +x setup_all.sh
./setup_all.sh

# Or manual:
sudo pacman -S python-opencv tesseract poppler tesseract-data-ara tesseract-data-eng
cd omni-medical-suite
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python app/advanced_review_app.py
```

## Design Decisions

1. **Manual save only** — No auto-save. User must click Save.
2. **gr.State for Before/After** — Stable, no file I/O until user saves.
3. **No chromedriver in pacman** — Uses pip:webdriver-manager instead.
4. **Headless OpenCV** — No GUI dependency, works on servers.
5. **pdf2image requires poppler** — System package, not pip.
6. **SQLite for glossary** — No server needed, file-based.
7. **Lazy OCR loading** — Engines loaded on first use, graceful degradation.