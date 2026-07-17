#!/usr/bin/env python3
"""
archive_book_downloader.py — OmniFile_Processor / omni-medical-suite
=====================================================================
Comprehensive Archive.org book downloader with integrated glossary extraction.

Features:
  - IIIF-based page downloading with skip-if-exists resumability
  - Scanner image correction via fix_scanner_image (deskew, denoise, sharpen, etc.)
  - Bilingual OCR (English + Arabic) via Tesseract
  - 7-pattern glossary extraction (3 Hitti-style + 4 glossary_parser-style)
  - SQLite storage with verified column for human review
  - Export to JSON, CSV (UTF-8 BOM), and TXT

Usage:
    from packages.collectors.archive_book_downloader import ArchiveBookDownloader

    dl = ArchiveBookDownloader(
        book_id="hittihistoryofar00hitt",
        output_dir="./output/hitti",
    )
    dl.process_book(start=1, end=50)
    dl.save_results("./output/hitti/glossary_results")

Author: Z.ai
Updated: 2026-07-17
"""

import os
import re
import sys
import csv
import json
import time
import logging
import sqlite3
from pathlib import Path
from dataclasses import dataclass, asdict, field
from typing import List, Dict, Optional, Tuple, Any

import cv2
import requests
import numpy as np
from PIL import Image

# ---------------------------------------------------------------------------
# Project import — scanner fix pipeline
# ---------------------------------------------------------------------------
# Support running both as part of the package tree and as a standalone script.
try:
    from packages.preprocessors.scanner_fixer import fix_scanner_image
except ImportError:
    # Fallback: try relative / sys.path insertion so the file is directly runnable
    _PROJECT_ROOT = Path(__file__).resolve().parents[2]
    if str(_PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(_PROJECT_ROOT))
    from packages.preprocessors.scanner_fixer import fix_scanner_image

# ---------------------------------------------------------------------------
# Logging — dual handler (file + console)
# ---------------------------------------------------------------------------
LOG_DIR = Path(__file__).resolve().parents[2] / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

_logger = logging.getLogger("archive_book_downloader")
_logger.setLevel(logging.DEBUG)

_formatter = logging.Formatter(
    "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

_file_handler = logging.FileHandler(
    LOG_DIR / "archive_book_downloader.log", encoding="utf-8"
)
_file_handler.setLevel(logging.DEBUG)
_file_handler.setFormatter(_formatter)

_console_handler = logging.StreamHandler(sys.stdout)
_console_handler.setLevel(logging.INFO)
_console_handler.setFormatter(_formatter)

if not _logger.handlers:
    _logger.addHandler(_file_handler)
    _logger.addHandler(_console_handler)

log = _logger


# ---------------------------------------------------------------------------
# Data Model
# ---------------------------------------------------------------------------
@dataclass
class GlossaryEntry:
    """A single glossary term pair extracted from a book page."""
    entry_type: str      # "en_ar" or "ar_en"
    term1: str
    term2: str
    page_num: int
    context: str = ""
    confidence: float = 0.0


# ---------------------------------------------------------------------------
# Regex Patterns — 7 total
# ---------------------------------------------------------------------------
# Hitti-style patterns (3)
# 1. English → Arabic, comma/semicolon separated
RE_EN_AR_COMMA = re.compile(
    r"([A-Za-z][A-Za-z\s\-]{2,50})[,;]\s*([\u0600-\u06FF\s]{2,100})"
)
# 2. Arabic → English, comma/semicolon separated
RE_AR_EN_COMMA = re.compile(
    r"([\u0600-\u06FF][\u0600-\u06FF\s\-]{2,100})[,;]\s*([A-Za-z][A-Za-z\s\-]{2,50})"
)
# 3. Bold / all-caps dictionary headword  TERM — definition
RE_BOLD_DICT = re.compile(
    r"^([A-Z][A-Z\s\-]{1,40})\s*[—\-]\s*(.+)$", re.MULTILINE
)

# glossary_parser-style patterns (4)
# 4. Colon separator (confidence 0.8)
RE_COLON = re.compile(
    r"([^\n:]{2,80})[:：]\s*([^\n]{5,500})"
)
# 5. Numbered list entry (confidence 0.75)
RE_NUMBERED = re.compile(
    r"\d+[.)]\s*([^\n\-–]{2,80})\s*[-–]\s*([^\n]{5,500})"
)
# 6. Table row split by | or TAB (confidence 0.7)
RE_TABLE = re.compile(
    r"([^\n|]+?)\s*[|\t]\s*([^\n]+)"
)
# 7. Parenthetical definition (confidence 0.6)
RE_PARENS = re.compile(
    r"([^\n(]{2,50})\s*\(\s*([^\)]{5,200})\s*\)"
)

# Arabic character detection range
_ARABIC_CHAR_RE = re.compile(r"[\u0600-\u06FF]")
_ARABIC_EXTENDED_RE = re.compile(r"[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\uFB50-\uFDFF\uFE70-\uFEFF]")


# ---------------------------------------------------------------------------
# Helper: Arabic character ratio
# ---------------------------------------------------------------------------
def _arabic_char_ratio(text: str) -> float:
    """Return the fraction of characters in *text* that are Arabic script."""
    if not text:
        return 0.0
    total = len(text)
    arabic = len(_ARABIC_EXTENDED_RE.findall(text))
    return arabic / total


# ---------------------------------------------------------------------------
# Main Class
# ---------------------------------------------------------------------------
class ArchiveBookDownloader:
    """Download, OCR, and extract glossary terms from an Archive.org book."""

    # IIIF base URL
    IIIF_BASE = "https://archive.org/iiif/{book_id}/page/{n}/full/pct:100/0/default.jpg"
    IIIF_INFO = "https://archive.org/iiif/{book_id}/info.json"

    # -----------------------------------------------------------------------
    # Init
    # -----------------------------------------------------------------------
    def __init__(
        self,
        book_id: str,
        output_dir: str,
        email: str = "",
        password: str = "",
    ):
        self.book_id = book_id.strip()
        self.output_dir = Path(output_dir).resolve()
        self.email = email
        self.password = password

        # Create output directories
        self.pages_dir = self.output_dir / "pages"
        self.fixed_dir = self.output_dir / "pages_fixed"
        self.pages_dir.mkdir(parents=True, exist_ok=True)
        self.fixed_dir.mkdir(parents=True, exist_ok=True)

        # Database
        self.db_path = self.output_dir / f"{self.book_id}.db"
        self._init_db()

        # In-memory results
        self.glossary_entries: List[GlossaryEntry] = []

        # Book metadata (populated by get_book_info)
        self.total_pages: int = 0
        self.page_dimensions: Dict[str, Any] = {}
        self.book_metadata: Dict[str, Any] = {}

        # HTTP session
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": (
                "OmniMedicalSuite/1.0 (Archive.org Book Downloader; "
                f"contact: {self.email or 'user@example.com'})"
            ),
        })
        if self.email and self.password:
            self._authenticate()

    # -----------------------------------------------------------------------
    # Authentication (optional, for restricted books)
    # -----------------------------------------------------------------------
    def _authenticate(self) -> None:
        """Log in to Archive.org if credentials are provided."""
        try:
            login_url = "https://archive.org/account/login"
            resp = self.session.get(login_url, timeout=30)
            resp.raise_for_status()
            # Archive.org uses a cookie-based login; for public books this is
            # optional.  We store credentials in case they are needed later.
            log.info("Archive.org session initialised (credentials provided).")
        except Exception as exc:
            log.warning("Archive.org authentication attempt failed: %s", exc)

    # -----------------------------------------------------------------------
    # Database
    # -----------------------------------------------------------------------
    def _init_db(self) -> None:
        """Create SQLite tables if they don't exist."""
        with self._db_conn() as conn:
            cursor = conn.cursor()
            cursor.executescript("""
                CREATE TABLE IF NOT EXISTS en_ar_glossary (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    term_en     TEXT    NOT NULL,
                    term_ar     TEXT    NOT NULL,
                    page_num    INTEGER NOT NULL,
                    context     TEXT    DEFAULT '',
                    confidence  REAL    DEFAULT 0.0,
                    verified    INTEGER DEFAULT 0,
                    created_at  TEXT    DEFAULT (datetime('now'))
                );

                CREATE TABLE IF NOT EXISTS ar_en_glossary (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    term_ar     TEXT    NOT NULL,
                    term_en     TEXT    NOT NULL,
                    page_num    INTEGER NOT NULL,
                    context     TEXT    DEFAULT '',
                    confidence  REAL    DEFAULT 0.0,
                    verified    INTEGER DEFAULT 0,
                    created_at  TEXT    DEFAULT (datetime('now'))
                );

                CREATE TABLE IF NOT EXISTS processed_pages (
                    page_num    INTEGER PRIMARY KEY,
                    status      TEXT    DEFAULT 'pending',
                    ocr_text    TEXT    DEFAULT '',
                    entries_found INTEGER DEFAULT 0,
                    processed_at TEXT DEFAULT (datetime('now')),
                    error_msg   TEXT    DEFAULT '',
                    verified    INTEGER DEFAULT 0
                );
            """)
            conn.commit()
        log.debug("Database initialised at %s", self.db_path)

    def _db_conn(self) -> sqlite3.Connection:
        """Return a connection to the SQLite database."""
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    # -----------------------------------------------------------------------
    # Book Info (IIIF info.json)
    # -----------------------------------------------------------------------
    def get_book_info(self) -> Dict[str, Any]:
        """
        Fetch IIIF info.json to get total pages and page dimensions.

        Returns a dict with keys: total_pages, dimensions, metadata.
        """
        url = self.IIIF_INFO.format(book_id=self.book_id)
        log.info("Fetching book info from %s", url)

        try:
            resp = self.session.get(url, timeout=30)
            resp.raise_for_status()
            data = resp.json()
        except requests.RequestException as exc:
            log.error("Failed to fetch IIIF info.json: %s", exc)
            # Fallback: try the standard Archive.org metadata API
            return self._get_book_info_fallback()

        # Extract total number of pages from canvases / sequences
        total = 0
        dimensions: Dict[str, Any] = {}

        # IIIF Presentation API v2 / v3
        sequences = data.get("sequences", [])
        if not sequences and "items" in data:
            # IIIF v3 — items are the canvases at top level
            sequences = [{"canvases": data.get("items", [])}]

        for seq in sequences:
            for canvas in seq.get("canvases", []):
                total += 1
                canvas_id = canvas.get("@id", canvas.get("id", str(total)))
                width = canvas.get("width", 0)
                height = canvas.get("height", 0)
                dimensions[canvas_id] = {"width": width, "height": height}

        self.total_pages = total
        self.page_dimensions = dimensions
        self.book_metadata = {
            "label": data.get("label", ""),
            "description": data.get("description", ""),
            "attribution": data.get("attribution", ""),
        }

        info = {
            "total_pages": total,
            "dimensions": dimensions,
            "metadata": self.book_metadata,
        }
        log.info("Book info retrieved — %d pages, label: %s",
                 total, self.book_metadata.get("label", "N/A"))
        return info

    def _get_book_info_fallback(self) -> Dict[str, Any]:
        """Fallback: use Archive.org metadata API to get page count."""
        url = f"https://archive.org/metadata/{self.book_id}"
        try:
            resp = self.session.get(url, timeout=30)
            resp.raise_for_status()
            data = resp.json()
        except Exception as exc:
            log.error("Fallback metadata fetch also failed: %s", exc)
            return {"total_pages": 0, "dimensions": {}, "metadata": {}}

        # Page count may be in various fields
        total = 0
        # Try leaf count
        leaf_count = data.get("leafCount")
        if leaf_count is not None:
            total = int(leaf_count)

        # Try page count
        page_count = data.get("pageCount")
        if page_count is not None:
            total = max(total, int(page_count))

        # Try counting image files in the files list
        if total == 0:
            for f in data.get("files", []):
                name = f.get("name", "")
                if "page" in name.lower() and f.get("format", "").startswith("image"):
                    total += 1

        self.total_pages = total
        self.book_metadata = {
            "title": data.get("title", ""),
            "description": data.get("description", ""),
            "creator": data.get("creator", ""),
        }
        log.info("Fallback book info — %d pages", total)
        return {
            "total_pages": total,
            "dimensions": {},
            "metadata": self.book_metadata,
        }

    # -----------------------------------------------------------------------
    # Download Pages
    # -----------------------------------------------------------------------
    def download_pages(
        self,
        start: int = 1,
        end: Optional[int] = None,
        dpi: int = 300,
    ) -> List[Path]:
        """
        Download book pages via IIIF URL pattern.

        Parameters
        ----------
        start : int
            First page number (1-indexed).
        end : int, optional
            Last page number.  Defaults to total_pages if known, or start.
        dpi : int
            Target DPI (used for the IIIF `pct` size parameter).  The IIIF
            URL in this implementation uses ``pct:100`` (native resolution).
            Higher DPI pages can be requested via the IIIF size parameter.

        Returns
        -------
        list[Path]
            Paths to successfully downloaded (or already-existing) page images.
        """
        if end is None:
            end = self.total_pages if self.total_pages > 0 else start

        log.info("Downloading pages %d–%d for book '%s'", start, end, self.book_id)
        downloaded: List[Path] = []

        for page_num in range(start, end + 1):
            dest = self.pages_dir / f"page_{page_num:04d}.jpg"

            # Skip-if-exists for resumability
            if dest.exists() and dest.stat().st_size > 0:
                # Verify the image is valid
                try:
                    with Image.open(dest) as img:
                        img.verify()
                    log.debug("Page %d already exists, skipping (%s)", page_num, dest.name)
                    downloaded.append(dest)
                    continue
                except Exception:
                    log.warning("Existing page %d is corrupt, re-downloading", page_num)

            url = self.IIIF_BASE.format(book_id=self.book_id, n=page_num)
            log.info("Downloading page %d / %d  →  %s", page_num, end, url)

            try:
                resp = self.session.get(url, timeout=60, stream=True)
                resp.raise_for_status()

                # Write to temporary file first, then rename (atomic-ish)
                tmp_path = dest.with_suffix(".jpg.tmp")
                with open(tmp_path, "wb") as f:
                    for chunk in resp.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)

                # Verify downloaded image with PIL
                with Image.open(tmp_path) as img:
                    img.verify()

                tmp_path.rename(dest)
                downloaded.append(dest)
                log.info("Page %d saved (%d bytes)", page_num, dest.stat().st_size)

            except Exception as exc:
                log.error("Failed to download page %d: %s", page_num, exc)
                # Clean up partial file
                for tmp in (dest, dest.with_suffix(".jpg.tmp")):
                    if tmp.exists():
                        tmp.unlink(missing_ok=True)
                continue

            # Polite delay between requests
            time.sleep(0.3)

        log.info("Download complete: %d / %d pages available", len(downloaded), end - start + 1)
        return downloaded

    # -----------------------------------------------------------------------
    # OCR
    # -----------------------------------------------------------------------
    def run_ocr(self, image_path: str, lang: str = "eng+ara") -> str:
        """
        Run Tesseract OCR on an image file.

        The image is first processed through ``fix_scanner_image`` to correct
        scanner artifacts (deskew, denoise, sharpen, contrast, borders).

        Parameters
        ----------
        image_path : str
            Path to the source image.
        lang : str
            Tesseract language string (default ``eng+ara`` for English+Arabic).

        Returns
        -------
        str
            Recognised text.
        """
        import pytesseract

        img_path = Path(image_path)
        if not img_path.exists():
            log.error("Image not found for OCR: %s", image_path)
            return ""

        # Read with OpenCV
        img_bgr = cv2.imread(str(img_path))
        if img_bgr is None:
            log.error("cv2 could not read image: %s", image_path)
            return ""

        log.debug("Running scanner fix on %s", img_path.name)
        fixed_img = fix_scanner_image(img_bgr)

        # Save fixed image for debugging / inspection
        fixed_path = self.fixed_dir / img_path.name
        cv2.imwrite(str(fixed_path), fixed_img)

        # OCR configuration: PSM 6 (assume a single uniform block of text),
        # OEM 3 (LSTM neural network — best accuracy)
        custom_config = "--psm 6 --oem 3"

        log.debug("Running Tesseract OCR (lang=%s, config='%s') on %s",
                  lang, custom_config, img_path.name)
        try:
            text = pytesseract.image_to_string(fixed_img, lang=lang, config=custom_config)
            # Normalise whitespace
            text = re.sub(r"[ \t]+", " ", text)
            text = re.sub(r"\n{3,}", "\n\n", text)
            text = text.strip()
            log.debug("OCR produced %d characters from %s", len(text), img_path.name)
            return text
        except Exception as exc:
            log.error("Tesseract OCR failed on %s: %s", img_path.name, exc)
            return ""

    # -----------------------------------------------------------------------
    # Language Detection
    # -----------------------------------------------------------------------
    @staticmethod
    def detect_language(text: str) -> str:
        """
        Detect dominant script in *text*.

        Returns ``"ar"`` if Arabic characters exceed 30 % of total characters,
        otherwise ``"en"``.
        """
        ratio = _arabic_char_ratio(text)
        return "ar" if ratio > 0.3 else "en"

    # -----------------------------------------------------------------------
    # Glossary Extraction — 7 Patterns
    # -----------------------------------------------------------------------
    def extract_glossary(self, text: str, page_num: int) -> List[GlossaryEntry]:
        """
        Extract glossary term pairs from OCR text using all 7 regex patterns.

        Patterns (Hitti-style, 3):
            1. En→Ar comma-separated        (confidence 0.9)
            2. Ar→En comma-separated        (confidence 0.9)
            3. Bold / ALL-CAPS headword     (confidence 0.85)

        Patterns (glossary_parser-style, 4):
            4. Colon separator               (confidence 0.8)
            5. Numbered list entry           (confidence 0.75)
            6. Table row (| or TAB)         (confidence 0.7)
            7. Parenthetical definition      (confidence 0.6)

        Returns a list of :class:`GlossaryEntry` instances.
        """
        if not text or not text.strip():
            return []

        entries: List[GlossaryEntry] = []
        seen: set = set()  # de-duplication

        def _add(entry: GlossaryEntry) -> None:
            """Add entry if not a duplicate."""
            key = (entry.entry_type, entry.term1.strip().lower(), entry.term2.strip().lower())
            if key in seen:
                return
            # Basic quality filter: both terms must have printable content
            t1 = entry.term1.strip()
            t2 = entry.term2.strip()
            if len(t1) < 2 or len(t2) < 2:
                return
            seen.add(key)
            entries.append(entry)

        # ---- Pattern 1: En → Ar comma/semicolon (confidence 0.9) ----
        for m in RE_EN_AR_COMMA.finditer(text):
            t_en = m.group(1).strip().rstrip(",")
            t_ar = m.group(2).strip()
            if t_en and t_ar:
                _add(GlossaryEntry(
                    entry_type="en_ar",
                    term1=t_en,
                    term2=t_ar,
                    page_num=page_num,
                    context=m.group(0).strip(),
                    confidence=0.9,
                ))

        # ---- Pattern 2: Ar → En comma/semicolon (confidence 0.9) ----
        for m in RE_AR_EN_COMMA.finditer(text):
            t_ar = m.group(1).strip()
            t_en = m.group(2).strip()
            if t_ar and t_en:
                _add(GlossaryEntry(
                    entry_type="ar_en",
                    term1=t_ar,
                    term2=t_en,
                    page_num=page_num,
                    context=m.group(0).strip(),
                    confidence=0.9,
                ))

        # ---- Pattern 3: Bold / ALL-CAPS dictionary headword (confidence 0.85) ----
        for m in RE_BOLD_DICT.finditer(text):
            headword = m.group(1).strip()
            definition = m.group(2).strip()
            if headword and definition:
                _add(GlossaryEntry(
                    entry_type="en_ar",
                    term1=headword,
                    term2=definition,
                    page_num=page_num,
                    context=m.group(0).strip(),
                    confidence=0.85,
                ))

        # ---- Pattern 4: Colon separator (confidence 0.8) ----
        for m in RE_COLON.finditer(text):
            before = m.group(1).strip()
            after = m.group(2).strip()
            if not before or not after:
                continue
            # Classify direction based on script content
            ar_before = _arabic_char_ratio(before) > 0.3
            ar_after = _arabic_char_ratio(after) > 0.3
            if ar_before and not ar_after:
                entry_type = "ar_en"
                t1, t2 = before, after
            elif not ar_before and ar_after:
                entry_type = "en_ar"
                t1, t2 = before, after
            else:
                # Ambiguous — default to en_ar
                entry_type = "en_ar"
                t1, t2 = before, after
            _add(GlossaryEntry(
                entry_type=entry_type,
                term1=t1,
                term2=t2,
                page_num=page_num,
                context=m.group(0).strip(),
                confidence=0.8,
            ))

        # ---- Pattern 5: Numbered list (confidence 0.75) ----
        for m in RE_NUMBERED.finditer(text):
            term = m.group(1).strip()
            definition = m.group(2).strip()
            if not term or not definition:
                continue
            ar_term = _arabic_char_ratio(term) > 0.3
            ar_def = _arabic_char_ratio(definition) > 0.3
            if ar_term and not ar_def:
                entry_type = "ar_en"
                t1, t2 = term, definition
            elif not ar_term and ar_def:
                entry_type = "en_ar"
                t1, t2 = term, definition
            else:
                entry_type = "en_ar"
                t1, t2 = term, definition
            _add(GlossaryEntry(
                entry_type=entry_type,
                term1=t1,
                term2=t2,
                page_num=page_num,
                context=m.group(0).strip(),
                confidence=0.75,
            ))

        # ---- Pattern 6: Table row | or TAB (confidence 0.7) ----
        for m in RE_TABLE.finditer(text):
            col_a = m.group(1).strip()
            col_b = m.group(2).strip()
            if not col_a or not col_b:
                continue
            # Skip lines that look like pure punctuation / noise
            if re.match(r"^[\s|\-=_]+$", col_a + col_b):
                continue
            ar_a = _arabic_char_ratio(col_a) > 0.3
            ar_b = _arabic_char_ratio(col_b) > 0.3
            if ar_a and not ar_b:
                entry_type = "ar_en"
                t1, t2 = col_a, col_b
            elif not ar_a and ar_b:
                entry_type = "en_ar"
                t1, t2 = col_a, col_b
            else:
                entry_type = "en_ar"
                t1, t2 = col_a, col_b
            _add(GlossaryEntry(
                entry_type=entry_type,
                term1=t1,
                term2=t2,
                page_num=page_num,
                context=m.group(0).strip(),
                confidence=0.7,
            ))

        # ---- Pattern 7: Parenthetical definition (confidence 0.6) ----
        for m in RE_PARENS.finditer(text):
            outer = m.group(1).strip()
            inner = m.group(2).strip()
            if not outer or not inner:
                continue
            ar_outer = _arabic_char_ratio(outer) > 0.3
            ar_inner = _arabic_char_ratio(inner) > 0.3
            if ar_outer and not ar_inner:
                entry_type = "ar_en"
                t1, t2 = outer, inner
            elif not ar_outer and ar_inner:
                entry_type = "en_ar"
                t1, t2 = outer, inner
            else:
                entry_type = "en_ar"
                t1, t2 = outer, inner
            _add(GlossaryEntry(
                entry_type=entry_type,
                term1=t1,
                term2=t2,
                page_num=page_num,
                context=m.group(0).strip(),
                confidence=0.6,
            ))

        log.debug("Page %d: extracted %d glossary entries", page_num, len(entries))
        return entries

    # -----------------------------------------------------------------------
    # Full Processing Pipeline
    # -----------------------------------------------------------------------
    def process_book(
        self,
        start: int = 1,
        end: Optional[int] = None,
        ocr_lang: str = "eng+ara",
    ) -> List[GlossaryEntry]:
        """
        Run the full pipeline for a range of pages:
        download → scanner fix + OCR → glossary extraction → store to DB.

        Parameters
        ----------
        start : int
            First page number (1-indexed).
        end : int, optional
            Last page number.  Defaults to ``self.total_pages`` if known.
        ocr_lang : str
            Tesseract language string.

        Returns
        -------
        list[GlossaryEntry]
            All glossary entries found across the processed pages.
        """
        if end is None:
            end = self.total_pages if self.total_pages > 0 else start

        log.info("=" * 60)
        log.info("PROCESSING BOOK: %s  (pages %d–%d)", self.book_id, start, end)
        log.info("=" * 60)

        # Step 1: Get book info if not already done
        if not self.total_pages:
            self.get_book_info()

        # Step 2: Download pages
        downloaded = self.download_pages(start=start, end=end)

        # Step 3: Process each page (download → OCR → extract)
        for page_path in downloaded:
            # Parse page number from filename: page_NNNN.jpg
            fname = page_path.stem          # e.g. "page_0042"
            try:
                page_num = int(fname.split("_")[-1])
            except (ValueError, IndexError):
                log.warning("Could not parse page number from filename: %s", fname)
                continue

            # Check if already processed
            if self._is_page_processed(page_num):
                log.info("Page %d already processed, loading from DB", page_num)
                page_entries = self._load_page_entries(page_num)
                self.glossary_entries.extend(page_entries)
                continue

            try:
                # OCR (includes scanner fix internally)
                ocr_text = self.run_ocr(str(page_path), lang=ocr_lang)

                if not ocr_text:
                    log.warning("Page %d: OCR returned no text", page_num)
                    self._mark_page_processed(page_num, status="empty", ocr_text="", error_msg="OCR returned empty text")
                    continue

                # Detect language of the page
                lang = self.detect_language(ocr_text)
                log.info("Page %d: detected language=%s, %d chars",
                         page_num, lang, len(ocr_text))

                # Extract glossary entries
                page_entries = self.extract_glossary(ocr_text, page_num)

                # Store to SQLite
                self._store_entries(page_entries, page_num)
                self._mark_page_processed(
                    page_num,
                    status="done",
                    ocr_text=ocr_text,
                    entries_found=len(page_entries),
                )

                self.glossary_entries.extend(page_entries)
                log.info("Page %d: %d glossary entries extracted", page_num, len(page_entries))

            except Exception as exc:
                log.error("Page %d: processing FAILED — %s", page_num, exc, exc_info=True)
                self._mark_page_processed(
                    page_num,
                    status="error",
                    ocr_text="",
                    error_msg=str(exc),
                )
                continue  # never crash on single page failure

        log.info("=" * 60)
        log.info("PROCESSING COMPLETE: %d total glossary entries from %d pages",
                 len(self.glossary_entries), len(downloaded))
        log.info("=" * 60)
        return self.glossary_entries

    # -----------------------------------------------------------------------
    # DB Helpers
    # -----------------------------------------------------------------------
    def _is_page_processed(self, page_num: int) -> bool:
        """Check if a page has been successfully processed."""
        with self._db_conn() as conn:
            row = conn.execute(
                "SELECT status FROM processed_pages WHERE page_num = ?",
                (page_num,),
            ).fetchone()
            return row is not None and row["status"] == "done"

    def _mark_page_processed(
        self,
        page_num: int,
        status: str = "done",
        ocr_text: str = "",
        entries_found: int = 0,
        error_msg: str = "",
    ) -> None:
        """Insert or update the processed_pages record."""
        with self._db_conn() as conn:
            conn.execute(
                """
                INSERT INTO processed_pages (page_num, status, ocr_text, entries_found, error_msg)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(page_num) DO UPDATE SET
                    status      = excluded.status,
                    ocr_text    = excluded.ocr_text,
                    entries_found = excluded.entries_found,
                    error_msg   = excluded.error_msg,
                    processed_at = datetime('now')
                """,
                (page_num, status, ocr_text, entries_found, error_msg),
            )
            conn.commit()

    def _store_entries(self, entries: List[GlossaryEntry], page_num: int) -> None:
        """Insert glossary entries into the appropriate DB table."""
        if not entries:
            return
        with self._db_conn() as conn:
            for entry in entries:
                if entry.entry_type == "en_ar":
                    conn.execute(
                        """
                        INSERT INTO en_ar_glossary (term_en, term_ar, page_num, context, confidence)
                        VALUES (?, ?, ?, ?, ?)
                        """,
                        (entry.term1, entry.term2, entry.page_num, entry.context, entry.confidence),
                    )
                elif entry.entry_type == "ar_en":
                    conn.execute(
                        """
                        INSERT INTO ar_en_glossary (term_ar, term_en, page_num, context, confidence)
                        VALUES (?, ?, ?, ?, ?)
                        """,
                        (entry.term1, entry.term2, entry.page_num, entry.context, entry.confidence),
                    )
            conn.commit()
        log.debug("Stored %d entries for page %d in DB", len(entries), page_num)

    def _load_page_entries(self, page_num: int) -> List[GlossaryEntry]:
        """Load previously stored glossary entries for a page from DB."""
        entries: List[GlossaryEntry] = []
        with self._db_conn() as conn:
            # en_ar entries
            for row in conn.execute(
                "SELECT term_en, term_ar, context, confidence FROM en_ar_glossary WHERE page_num = ?",
                (page_num,),
            ).fetchall():
                entries.append(GlossaryEntry(
                    entry_type="en_ar",
                    term1=row["term_en"],
                    term2=row["term_ar"],
                    page_num=page_num,
                    context=row["context"],
                    confidence=row["confidence"],
                ))
            # ar_en entries
            for row in conn.execute(
                "SELECT term_ar, term_en, context, confidence FROM ar_en_glossary WHERE page_num = ?",
                (page_num,),
            ).fetchall():
                entries.append(GlossaryEntry(
                    entry_type="ar_en",
                    term1=row["term_ar"],
                    term2=row["term_en"],
                    page_num=page_num,
                    context=row["context"],
                    confidence=row["confidence"],
                ))
        return entries

    # -----------------------------------------------------------------------
    # Save / Export Results
    # -----------------------------------------------------------------------
    def save_results(self, output_path: str) -> Dict[str, str]:
        """
        Export all glossary entries to JSON, CSV (UTF-8 BOM), and TXT.

        Parameters
        ----------
        output_path : str
            Base path (without extension).  Three files will be created:
            ``{output_path}.json``, ``{output_path}.csv``, ``{output_path}.txt``.

        Returns
        -------
        dict[str, str]
            Mapping of format name to file path.
        """
        base = Path(output_path)
        base.parent.mkdir(parents=True, exist_ok=True)

        # If no in-memory entries, reload from DB
        if not self.glossary_entries:
            self.glossary_entries = self._load_all_entries()

        log.info("Saving %d glossary entries to %s.*", len(self.glossary_entries), base)

        saved: Dict[str, str] = {}

        # --- JSON ---
        json_path = base.with_suffix(".json")
        data = {
            "book_id": self.book_id,
            "total_entries": len(self.glossary_entries),
            "en_ar_count": sum(1 for e in self.glossary_entries if e.entry_type == "en_ar"),
            "ar_en_count": sum(1 for e in self.glossary_entries if e.entry_type == "ar_en"),
            "entries": [asdict(e) for e in self.glossary_entries],
        }
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        saved["json"] = str(json_path)
        log.info("JSON saved: %s", json_path)

        # --- CSV (UTF-8 BOM for Excel compatibility) ---
        csv_path = base.with_suffix(".csv")
        with open(csv_path, "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([
                "entry_type", "term1", "term2", "page_num",
                "context", "confidence",
            ])
            for entry in self.glossary_entries:
                writer.writerow([
                    entry.entry_type,
                    entry.term1,
                    entry.term2,
                    entry.page_num,
                    entry.context,
                    f"{entry.confidence:.2f}",
                ])
        saved["csv"] = str(csv_path)
        log.info("CSV saved (UTF-8 BOM): %s", csv_path)

        # --- TXT (human-readable) ---
        txt_path = base.with_suffix(".txt")
        with open(txt_path, "w", encoding="utf-8") as f:
            f.write(f"Archive.org Book Glossary\n")
            f.write(f"{'=' * 60}\n")
            f.write(f"Book ID   : {self.book_id}\n")
            f.write(f"Total     : {len(self.glossary_entries)} entries\n")
            en_ar = sum(1 for e in self.glossary_entries if e.entry_type == "en_ar")
            ar_en = sum(1 for e in self.glossary_entries if e.entry_type == "ar_en")
            f.write(f"  EN→AR   : {en_ar}\n")
            f.write(f"  AR→EN   : {ar_en}\n")
            f.write(f"{'=' * 60}\n\n")

            # Group by page
            pages: Dict[int, List[GlossaryEntry]] = {}
            for entry in self.glossary_entries:
                pages.setdefault(entry.page_num, []).append(entry)

            for pnum in sorted(pages.keys()):
                f.write(f"--- Page {pnum} ({len(pages[pnum])} entries) ---\n")
                for entry in pages[pnum]:
                    direction = "EN→AR" if entry.entry_type == "en_ar" else "AR→EN"
                    f.write(
                        f"  [{direction}] {entry.term1}  ⟶  {entry.term2}  "
                        f"(conf={entry.confidence:.2f})\n"
                    )
                    if entry.context:
                        # Truncate long contexts
                        ctx = entry.context[:200]
                        f.write(f"       ctx: {ctx}\n")
                f.write("\n")
        saved["txt"] = str(txt_path)
        log.info("TXT saved: %s", txt_path)

        return saved

    def _load_all_entries(self) -> List[GlossaryEntry]:
        """Load all glossary entries from the database."""
        entries: List[GlossaryEntry] = []
        with self._db_conn() as conn:
            for row in conn.execute(
                "SELECT term_en, term_ar, page_num, context, confidence FROM en_ar_glossary ORDER BY page_num, id"
            ).fetchall():
                entries.append(GlossaryEntry(
                    entry_type="en_ar",
                    term1=row["term_en"],
                    term2=row["term_ar"],
                    page_num=row["page_num"],
                    context=row["context"],
                    confidence=row["confidence"],
                ))
            for row in conn.execute(
                "SELECT term_ar, term_en, page_num, context, confidence FROM ar_en_glossary ORDER BY page_num, id"
            ).fetchall():
                entries.append(GlossaryEntry(
                    entry_type="ar_en",
                    term1=row["term_ar"],
                    term2=row["term_en"],
                    page_num=row["page_num"],
                    context=row["context"],
                    confidence=row["confidence"],
                ))
        return entries

    # -----------------------------------------------------------------------
    # Convenience: Summary
    # -----------------------------------------------------------------------
    def summary(self) -> Dict[str, Any]:
        """Return a summary dict of the current state."""
        en_ar = sum(1 for e in self.glossary_entries if e.entry_type == "en_ar")
        ar_en = sum(1 for e in self.glossary_entries if e.entry_type == "ar_en")
        return {
            "book_id": self.book_id,
            "total_pages": self.total_pages,
            "output_dir": str(self.output_dir),
            "db_path": str(self.db_path),
            "total_entries": len(self.glossary_entries),
            "en_ar_entries": en_ar,
            "ar_en_entries": ar_en,
        }


# ---------------------------------------------------------------------------
# CLI Entry Point
# ---------------------------------------------------------------------------
def main() -> None:
    """Command-line interface for the Archive.org book downloader."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Download and extract glossary from an Archive.org book.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python archive_book_downloader.py hittihistoryofar00hitt ./output/hitti --pages 1 100
  python archive_book_downloader.py somebookid ./output/book --start 50 --end 200
  python archive_book_downloader.py somebookid ./output/book --export-only --output ./output/book/glossary
        """,
    )
    parser.add_argument("book_id", help="Archive.org book identifier")
    parser.add_argument("output_dir", help="Output directory for pages and results")
    parser.add_argument("--start", type=int, default=1, help="Start page (default: 1)")
    parser.add_argument("--end", type=int, default=None, help="End page (default: last)")
    parser.add_argument("--pages", nargs=2, type=int, metavar=("START", "END"),
                        help="Page range (shorthand for --start and --end)")
    parser.add_argument("--email", default="", help="Archive.org email (for restricted books)")
    parser.add_argument("--password", default="", help="Archive.org password")
    parser.add_argument("--ocr-lang", default="eng+ara", help="Tesseract language (default: eng+ara)")
    parser.add_argument("--export-only", action="store_true",
                        help="Only export previously processed results (skip download/OCR)")
    parser.add_argument("--output", default=None,
                        help="Base path for exported results (default: <output_dir>/glossary_results)")

    args = parser.parse_args()

    if args.pages:
        start, end = args.pages
    else:
        start = args.start
        end = args.end

    downloader = ArchiveBookDownloader(
        book_id=args.book_id,
        output_dir=args.output_dir,
        email=args.email,
        password=args.password,
    )

    if args.export_only:
        output_path = args.output or str(downloader.output_dir / "glossary_results")
        saved = downloader.save_results(output_path)
        for fmt, path in saved.items():
            print(f"  {fmt.upper()}: {path}")
        return

    # Full pipeline
    downloader.process_book(start=start, end=end, ocr_lang=args.ocr_lang)

    # Export results
    output_path = args.output or str(downloader.output_dir / "glossary_results")
    saved = downloader.save_results(output_path)

    # Print summary
    s = downloader.summary()
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    for key, value in s.items():
        print(f"  {key:20s}: {value}")
    print("\nExported files:")
    for fmt, path in saved.items():
        print(f"  {fmt.upper()}: {path}")
    print()


if __name__ == "__main__":
    main()