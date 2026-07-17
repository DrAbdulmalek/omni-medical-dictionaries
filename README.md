# Omni Medical Suite

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
- Selenium fallback for protected books
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

### Tampermonkey Script (Bonus)
- Fast browser-based download of borrowed Archive.org books
- 300ms per page (~2-3 min for 282 pages)
- See `scripts/archive-downloader.user.js`

## Quick Start (Manjaro)

```bash
# Clone
git clone https://github.com/DrAbdulmalek/omni-medical-suite.git
cd omni-medical-suite

# One-script setup
chmod +x setup_all.sh
./setup_all.sh

# Run
source venv/bin/activate
python app/advanced_review_app.py
# Open http://localhost:7860
```

### Manual Setup

```bash
# System packages
sudo pacman -S python-opencv tesseract poppler tesseract-data-ara tesseract-data-eng

# Python
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Run
python app/advanced_review_app.py
```

### Ubuntu/Debian

```bash
sudo apt install libgl1 libglib2.0-0 tesseract-ocr tesseract-ocr-ara tesseract-ocr-eng poppler-utils
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
python app/advanced_review_app.py
```

## Download a Book from Archive.org

### Option A: Tampermonkey (Fastest — 300ms/page)
1. Install [Tampermonkey](https://chrome.google.com/webstore/detail/tampermonkey/dhdgffkkebhmkfjojejmpbldmpobfkfo)
2. Copy `scripts/archive-downloader.user.js` into a new Tampermonkey script
3. Open the book on Archive.org, borrow it, click the orange START DOWNLOAD button

### Option B: Python CLI
```bash
python scripts/archive_book_extractor.py \
    --url "https://archive.org/details/hittisnewmedical0000hitt" \
    --email your_email@archive.org \
    --password your_password \
    --start-page 1 --end-page 50
```

### Option C: Gradio UI (Tab 3)
Open http://localhost:7860, go to "Archive Extractor" tab, fill in details, click Start.

## Google Colab

Open `colab/Omni_Hitti_Complete_Colab.ipynb` in Google Colab and run all cells.

## Project Structure

```
omni-medical-suite/
  app/
    advanced_review_app.py            # Main Gradio UI (4 tabs, port 7860)
    hitti_glossary_app.py             # Standalone glossary builder (port 7861)
    hf_space_app.py                   # HF Space: 5 OCR models
  packages/
    preprocessors/
      scanner_fixer.py                # Core engine v2.1
    ocr/
      ocr_engine.py                   # Multi-engine OCR
    collectors/
      archive_book_downloader.py      # Archive.org IIIF downloader
      glossary_parser.py              # 7-pattern glossary parser
  scripts/
    archive_book_extractor.py         # CLI v2.0 (IIIF + Selenium + Manual)
    archive-downloader.user.js        # Tampermonkey script v3.6
  tests/
    test_scanner_fixer.py             # Unit tests (pytest)
  colab/
    Omni_Hitti_Complete_Colab.ipynb   # Google Colab notebook
  data/                               # Runtime databases
  logs/                               # Runtime logs
  downloads/                          # User-saved files
  setup.sh                            # Scanner-only installer
  setup_all.sh                        # Full installer (Manjaro)
  setup_manjaro.sh                    # Simple Manjaro setup
  requirements.txt                    # Complete Python deps
  requirements-scanner.txt            # Scanner-only Python deps
  requirements-hf.txt                 # HF Space deps
  packages.txt                        # HF Space system deps
  DEPLOY_GUIDE.md                     # HF Space deployment guide
  STATE_OF_TRUTH.md                   # Architecture & status
  IDEAS.md                            # Development roadmap
```

## Running Tests

```bash
pip install pytest
python -m pytest tests/ -v
```

## Sources & Inspiration

- [Archive-Borrowed-Book-Downloader](https://github.com/AllLiveSupport/Archive-Borrowed-Book-Downloader) — Tampermonkey v3.6
- OmniFile AI Processor — 5-engine OCR system
- Medical Glossary Collector — 15 medical terminology collectors

## License

MIT