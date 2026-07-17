# OmniFile Medical Suite

Smart scanner image correction + Archive.org book downloader + bilingual medical glossary extraction.

## Features

### Scanner Fixer v2.1
- **Auto-Rotate**: Multi-method detection (Tesseract OSD + Hough Lines + Projection Profile)
- **Deskew**: MinAreaRect contour analysis
- **Denoise**: Non-Local Means
- **Sharpen**: Unsharp Mask
- **Contrast Fix**: CLAHE
- **Border Removal**: Content bounding box
- **Batch Mode**: Folder + multi-page PDF + ZIP export
- **Gradio UI**: Before/After preview, manual save only

### Archive.org Book Downloader
- IIIF API page download (no browser needed)
- Skip-if-exists for resumable downloads
- Scanner fix applied before OCR
- SQLite storage with `verified` flag for review workflow

### Multi-Engine OCR
- Tesseract (primary) + EasyOCR + PaddleOCR (fallback)
- Lazy loading + graceful degradation
- Batch processing support

### Glossary Parser (7 Patterns)
- En-Ar comma, Ar-En comma, Bold dict, Colon, Numbered, Table, Parentheses
- Language detection (Arabic ratio > 0.3)
- Confidence-based deduplication

## Quick Start (Manjaro)

```bash
# System packages
sudo pacman -S python-opencv tesseract poppler tesseract-data-ara tesseract-data-eng

# Python
python -m venv venv
source venv/bin/activate
pip install -r requirements-scanner.txt

# Run Scanner Fixer UI
python app/advanced_review_app.py
# Open http://localhost:7860
```

## Download a Book from Archive.org

```bash
python -m packages.collectors.archive_book_downloader \
    --book-id hittisnewmedical0000hitt \
    --output ./hitti_output \
    --pages 850 \
    --lang eng+ara
```

## One-Script Setup

```bash
chmod +x setup.sh
./setup.sh
```

## Project Structure

```
omni-medical-suite/
  app/
    advanced_review_app.py            # Gradio UI (Scanner Fixer)
  packages/
    preprocessors/
      scanner_fixer.py                # Core engine v2.1
    ocr/
      ocr_engine.py                   # Multi-engine OCR (Tesseract + EasyOCR + PaddleOCR)
    collectors/
      archive_book_downloader.py      # Archive.org IIIF downloader + glossary extraction
      glossary_parser.py             # 7-pattern bilingual glossary parser
  data/                              # Runtime data (glossaries, DBs)
  logs/                              # Runtime logs
  downloads/                         # User-saved files
  setup.sh                           # One-script installer
  requirements-scanner.txt           # Python deps
  IDEAS.md                           # Development roadmap & ideas
  STATE_OF_TRUTH.md                  # Architecture & status
```

## Sources & Inspiration

- [Archive-Borrowed-Book-Downloader](https://github.com/AllLiveSupport/Archive-Borrowed-Book-Downloader) — Tampermonkey v3.6
- OmniFile AI Processor — 5-engine OCR system
- Medical Glossary Collector — 15 medical terminology collectors

## License

MIT