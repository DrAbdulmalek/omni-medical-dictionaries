#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Archive.org Book Extractor v2.0
===============================
Supports: IIIF API | Selenium fallback | Manual mode
Author: DrAbdulmalek / Z.ai
"""

import argparse
import os
import sys
import time
import json
import re
import sqlite3
import logging
import shutil
from pathlib import Path
from datetime import datetime
from typing import List, Optional
from dataclasses import dataclass, asdict

import requests
from PIL import Image
import cv2
import numpy as np

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)-8s | %(message)s',
    handlers=[
        logging.FileHandler('logs/extractor.log', encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)


@dataclass
class GlossaryEntry:
    entry_type: str
    term1: str
    term2: str
    page_num: int
    context: str = ""
    confidence: float = 0.0
    
    def to_dict(self):
        return asdict(self)


class ArchiveBookExtractor:
    MODES = ["iiif", "selenium", "manual"]
    
    def __init__(self, email, password, output_dir, mode="iiif", delay=2.5):
        self.email = email
        self.password = password
        self.output_dir = Path(output_dir)
        self.mode = mode if mode in self.MODES else "iiif"
        self.delay = delay
        self.session = requests.Session()
        self.session.headers.update({'User-Agent': 'Mozilla/5.0'})
        self.book_id = None
        self.total_pages = 0
        self.driver = None
        
        self.output_dir.mkdir(parents=True, exist_ok=True)
        (self.output_dir / "pages").mkdir(exist_ok=True)
        (self.output_dir / "ocr").mkdir(exist_ok=True)
        (self.output_dir / "glossary").mkdir(exist_ok=True)
        (self.output_dir / "temp").mkdir(exist_ok=True)
        
        self.db_path = self.output_dir / "hitti_glossary.db"
        self._init_database()
        logger.info(f"Extractor v2.0 initialized | Mode: {self.mode}")
    
    def _init_database(self):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS en_ar_glossary (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                english_term TEXT NOT NULL,
                arabic_term TEXT,
                transliteration TEXT,
                page_num INTEGER,
                context TEXT,
                category TEXT,
                confidence REAL DEFAULT 0.0,
                verified INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS ar_en_glossary (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                arabic_term TEXT NOT NULL,
                english_term TEXT,
                page_num INTEGER,
                context TEXT,
                category TEXT,
                confidence REAL DEFAULT 0.0,
                verified INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS processed_pages (
                page_num INTEGER PRIMARY KEY,
                image_path TEXT,
                ocr_text TEXT,
                extraction_mode TEXT,
                processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_en ON en_ar_glossary(english_term)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_ar ON ar_en_glossary(arabic_term)')
        conn.commit()
        conn.close()
        logger.info("Database ready")
    
    def login(self):
        logger.info("Logging in to Archive.org...")
        try:
            login_page = self.session.get('https://archive.org/account/login', timeout=30)
            csrf_match = re.search(r'name="csrf-token" content="([^"]+)"', login_page.text)
            if not csrf_match:
                logger.error("Could not find CSRF token")
                return False
            csrf_token = csrf_match.group(1)
            login_data = {
                "username": self.email,
                "password": self.password,
                "csrf_token": csrf_token,
                "submit_by_js": "true",
                "remember": "true"
            }
            response = self.session.post('https://archive.org/account/login', data=login_data, headers={'Referer': 'https://archive.org/account/login'}, timeout=30)
            if response.status_code == 200:
                logger.info("Login successful")
                return True
            else:
                logger.error(f"Login failed: {response.status_code}")
                return False
        except Exception as e:
            logger.error(f"Login error: {e}")
            return False
    
    def borrow_book(self, book_url):
        self.book_id = book_url.split('/details/')[-1].split('/')[0]
        logger.info(f"Borrowing book: {self.book_id}")
        try:
            book_page = self.session.get(book_url, timeout=30)
            borrow_match = re.search(r'href="(/services/loans/loan\?action=borrow_book[^"]+)"', book_page.text)
            if borrow_match:
                borrow_url = 'https://archive.org' + borrow_match.group(1)
                response = self.session.get(borrow_url, timeout=30)
                if response.status_code == 200:
                    logger.info("Book borrowed successfully")
                    return True
            logger.warning("Could not confirm borrow status, continuing...")
            return True
        except Exception as e:
            logger.error(f"Borrow error: {e}")
            return False
    
    def get_page_url_iiif(self, page_num):
        return f"https://archive.org/iiif/{self.book_id}/page/{page_num}/full/pct:100/0/default.jpg"
    
    def download_page_iiif(self, page_num):
        image_path = self.output_dir / "pages" / f"page_{page_num:04d}.jpg"
        if image_path.exists():
            return str(image_path)
        url = self.get_page_url_iiif(page_num)
        try:
            logger.info(f"[IIIF] Downloading page {page_num}...")
            response = self.session.get(url, timeout=30)
            if response.status_code == 200 and len(response.content) > 1000:
                with open(image_path, "wb") as fimg:
                    fimg.write(response.content)
                try:
                    img = Image.open(image_path)
                    img.verify()
                    size_kb = len(response.content) // 1024
                    logger.info(f"[IIIF] Page {page_num} OK ({size_kb}KB)")
                    return str(image_path)
                except Exception:
                    image_path.unlink(missing_ok=True)
                    return None
            else:
                logger.warning(f"[IIIF] Page {page_num}: HTTP {response.status_code}")
                return None
        except Exception as e:
            logger.error(f"[IIIF] Page {page_num} error: {e}")
            return None
    
    def download_page_selenium(self, page_num):
        try:
            from selenium import webdriver
            from selenium.webdriver.chrome.options import Options
            if not self.driver:
                chrome_options = Options()
                chrome_options.add_argument("--headless")
                chrome_options.add_argument("--no-sandbox")
                self.driver = webdriver.Chrome(options=chrome_options)
            image_path = self.output_dir / "pages" / f"page_{page_num:04d}.jpg"
            if image_path.exists():
                return str(image_path)
            viewer_url = f"https://archive.org/details/{self.book_id}/page/{page_num}/mode/1up"
            self.driver.get(viewer_url)
            time.sleep(3)
            img_elem = self.driver.find_element("css selector", "img.BRpageimage")
            if img_elem:
                img_url = img_elem.get_attribute("src")
                if img_url:
                    response = self.session.get(img_url, timeout=30)
                    if response.status_code == 200:
                        with open(image_path, "wb") as fimg:
                            fimg.write(response.content)
                        logger.info(f"[Selenium] Page {page_num} downloaded")
                        return str(image_path)
            return None
        except ImportError:
            logger.warning("selenium not installed")
            return None
        except Exception as e:
            logger.error(f"[Selenium] Page {page_num} error: {e}")
            return None
    
    def download_page(self, page_num):
        if self.mode == "iiif":
            result = self.download_page_iiif(page_num)
            if result:
                return result
            logger.warning(f"IIIF failed for page {page_num}, trying Selenium...")
            return self.download_page_selenium(page_num)
        elif self.mode == "selenium":
            return self.download_page_selenium(page_num)
        elif self.mode == "manual":
            manual_path = self.output_dir / "temp" / f"page_{page_num:04d}.jpg"
            if manual_path.exists():
                dest = self.output_dir / "pages" / f"page_{page_num:04d}.jpg"
                shutil.copy(manual_path, dest)
                return str(dest)
            logger.warning(f"[Manual] Page {page_num} not found in temp/")
            return None
        return None
    
    def run_ocr(self, image_path, page_num):
        try:
            import pytesseract
            img = cv2.imread(image_path)
            if img is None:
                return ""
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            denoised = cv2.fastNlMeansDenoising(gray, None, 10, 7, 21)
            binary = cv2.adaptiveThreshold(denoised, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2)
            text = pytesseract.image_to_string(binary, lang='eng+ara', config='--psm 6 --oem 3')
            ocr_path = self.output_dir / "ocr" / f"page_{page_num:04d}.txt"
            with open(ocr_path, "w", encoding="utf-8") as focr:
                focr.write(text)
            logger.info(f"OCR page {page_num}: {len(text)} chars")
            return text
        except ImportError:
            logger.error("pytesseract not installed")
            return ""
        except Exception as e:
            logger.error(f"OCR error page {page_num}: {e}")
            return ""
    
    def extract_glossary_entries(self, text, page_num):
        entries = []
        # Pattern 1: English -> Arabic
        pattern1 = re.compile(r'([A-Za-z][A-Za-z\s\-/]{2,50})[,;:]\s*([\u0600-\u06FF\s]{2,100})', re.MULTILINE)
        for match in pattern1.finditer(text):
            en_term = re.sub(r"\s+", " ", match.group(1).strip())
            ar_term = re.sub(r"\s+", " ", match.group(2).strip())
            if len(en_term) > 2 and len(ar_term) > 2:
                ctx = text[max(0, match.start()-50):match.end()+50]
                entries.append(GlossaryEntry("en_ar", en_term, ar_term, page_num, ctx, 0.7))
        # Pattern 2: Arabic -> English
        pattern2 = re.compile(r'([\u0600-\u06FF][\u0600-\u06FF\s]{2,50})[,;:]\s*([A-Za-z][A-Za-z\s\-/]{2,50})', re.MULTILINE)
        for match in pattern2.finditer(text):
            ar_term = re.sub(r"\s+", " ", match.group(1).strip())
            en_term = re.sub(r"\s+", " ", match.group(2).strip())
            if len(ar_term) > 2 and len(en_term) > 2:
                ctx = text[max(0, match.start()-50):match.end()+50]
                entries.append(GlossaryEntry("ar_en", ar_term, en_term, page_num, ctx, 0.7))
        # Pattern 3: Dictionary bold format
        pattern3 = re.compile(r'^([A-Z][A-Z\s\-/]{1,40})\s*[—\-]\s*(.+)$', re.MULTILINE)
        for match in pattern3.finditer(text):
            en_term = match.group(1).strip()
            definition = match.group(2).strip()
            ar_match = re.search(r'([\u0600-\u06FF]{2,100})', definition)
            if ar_match:
                entries.append(GlossaryEntry("en_ar", en_term, ar_match.group(1).strip(), page_num, definition, 0.6))
        # Pattern 4: Numbered entries
        pattern4 = re.compile(r'^\s*\d+\.\s*([A-Za-z][A-Za-z\s\-/]{2,50})\s*[—\-]\s*([\u0600-\u06FF\s]{2,100})', re.MULTILINE)
        for match in pattern4.finditer(text):
            en_term = re.sub(r"\s+", " ", match.group(1).strip())
            ar_term = re.sub(r"\s+", " ", match.group(2).strip())
            entries.append(GlossaryEntry("en_ar", en_term, ar_term, page_num, text[max(0, match.start()-50):match.end()+50], 0.65))
        return entries
    
    def save_to_database(self, entries):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        for entry in entries:
            if entry.entry_type == "en_ar":
                cursor.execute("INSERT OR IGNORE INTO en_ar_glossary (english_term, arabic_term, page_num, context, confidence) VALUES (?, ?, ?, ?, ?)", (entry.term1, entry.term2, entry.page_num, entry.context[:500], entry.confidence))
            else:
                cursor.execute("INSERT OR IGNORE INTO ar_en_glossary (arabic_term, english_term, page_num, context, confidence) VALUES (?, ?, ?, ?, ?)", (entry.term1, entry.term2, entry.page_num, entry.context[:500], entry.confidence))
        conn.commit()
        conn.close()
    
    def export_glossary(self, fmt="all"):
        conn = sqlite3.connect(self.db_path)
        if fmt in ("all", "json"):
            cursor = conn.execute("SELECT * FROM en_ar_glossary ORDER BY english_term")
            en_ar = [dict(zip([c[0] for c in cursor.description], row)) for row in cursor.fetchall()]
            cursor = conn.execute("SELECT * FROM ar_en_glossary ORDER BY arabic_term")
            ar_en = [dict(zip([c[0] for c in cursor.description], row)) for row in cursor.fetchall()]
            json_path = self.output_dir / "glossary" / "hitti_glossary.json"
            with open(json_path, "w", encoding="utf-8") as fjson:
                meta = {"book": "Hitti Medical Dictionary", "extracted_at": datetime.now().isoformat(), "total_en_ar": len(en_ar), "total_ar_en": len(ar_en), "version": "2.0"}
                json.dump({"en_ar": en_ar, "ar_en": ar_en, "metadata": meta}, fjson, ensure_ascii=False, indent=2)
            logger.info(f"JSON exported: {json_path}")
        if fmt in ("all", "csv"):
            import csv
            csv_path = self.output_dir / "glossary" / "hitti_en_ar.csv"
            with open(csv_path, "w", encoding="utf-8-sig", newline="") as fcsv:
                writer = csv.writer(fcsv)
                writer.writerow(["English", "Arabic", "Page", "Context", "Confidence"])
                cursor = conn.execute("SELECT english_term, arabic_term, page_num, context, confidence FROM en_ar_glossary ORDER BY english_term")
                writer.writerows(cursor.fetchall())
            csv_path = self.output_dir / "glossary" / "hitti_ar_en.csv"
            with open(csv_path, "w", encoding="utf-8-sig", newline="") as fcsv:
                writer = csv.writer(fcsv)
                writer.writerow(["Arabic", "English", "Page", "Context", "Confidence"])
                cursor = conn.execute("SELECT arabic_term, english_term, page_num, context, confidence FROM ar_en_glossary ORDER BY arabic_term")
                writer.writerows(cursor.fetchall())
            logger.info("CSV exported")
        if fmt in ("all", "txt"):
            txt_path = self.output_dir / "glossary" / "hitti_glossary.txt"
            with open(txt_path, "w", encoding="utf-8") as ftxt:
                ftxt.write("=" * 70 + "\n")
                ftxt.write("HITTI NEW MEDICAL DICTIONARY\n")
                ftxt.write("English-Arabic / Arabic-English Glossary\n")
                ftxt.write("Extracted by Archive.org Book Extractor v2.0\n")
                ftxt.write("=" * 70 + "\n\n")
                ftxt.write("[ENGLISH -> ARABIC]\n")
                ftxt.write("-" * 50 + "\n")
                cursor = conn.execute("SELECT english_term, arabic_term, page_num, confidence FROM en_ar_glossary ORDER BY english_term")
                for row in cursor.fetchall():
                    conf = f"[{row[3]:.1f}]" if row[3] else ""
                    ftxt.write(f"{row[0]:<30} | {row[1]:<30} | p.{row[2]:<4} {conf}\n")
                ftxt.write("\n\n[ARABIC -> ENGLISH]\n")
                ftxt.write("-" * 50 + "\n")
                cursor = conn.execute("SELECT arabic_term, english_term, page_num, confidence FROM ar_en_glossary ORDER BY arabic_term")
                for row in cursor.fetchall():
                    conf = f"[{row[3]:.1f}]" if row[3] else ""
                    ftxt.write(f"{row[0]:<30} | {row[1]:<30} | p.{row[2]:<4} {conf}\n")
            logger.info(f"TXT exported: {txt_path}")
        if fmt in ("all", "sql"):
            sql_path = self.output_dir / "glossary" / "hitti_glossary.sql"
            with open(sql_path, "w", encoding="utf-8") as fsql:
                fsql.write("-- Hitti Medical Dictionary - Glossary Export\n")
                fsql.write(f"-- Generated: {datetime.now().isoformat()}\n\n")
                cursor = conn.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name IN ('en_ar_glossary', 'ar_en_glossary')")
                for row in cursor.fetchall():
                    fsql.write(f"{row[0]};\n\n")
                cursor = conn.execute("SELECT * FROM en_ar_glossary")
                for row in cursor.fetchall():
                    fsql.write(f"INSERT INTO en_ar_glossary VALUES {row};\n")
                fsql.write("\n")
                cursor = conn.execute("SELECT * FROM ar_en_glossary")
                for row in cursor.fetchall():
                    fsql.write(f"INSERT INTO ar_en_glossary VALUES {row};\n")
            logger.info(f"SQL exported: {sql_path}")
        conn.close()
    
    def create_pdf(self):
        try:
            from img2pdf import convert
            pages_dir = self.output_dir / "pages"
            images = sorted(pages_dir.glob("page_*.jpg"))
            if not images:
                logger.warning("No pages found to create PDF")
                return
            pdf_path = self.output_dir / f"{self.book_id}.pdf"
            with open(pdf_path, "wb") as fpdf:
                fpdf.write(convert([str(img) for img in images]))
            logger.info(f"PDF created: {pdf_path}")
        except ImportError:
            logger.warning("img2pdf not installed")
    
    def cleanup_temp(self):
        temp_dir = self.output_dir / "temp"
        if temp_dir.exists():
            shutil.rmtree(temp_dir)
            logger.info("Temporary files cleaned up")
    
    def run(self, book_url, start_page=1, end_page=None, skip_download=False, skip_ocr=False):
        logger.info("=" * 70)
        logger.info("Archive.org Book Extractor v2.0 - Starting")
        logger.info(f"Book URL: {book_url}")
        logger.info(f"Mode: {self.mode}")
        logger.info("=" * 70)
        if not self.login():
            logger.error("Cannot proceed without login")
            return False
        self.borrow_book(book_url)
        if end_page is None:
            end_page = start_page + 49
        self.total_pages = end_page - start_page + 1
        logger.info(f"Processing pages {start_page} to {end_page}")
        if not skip_download:
            for page_num in range(start_page, end_page + 1):
                image_path = self.download_page(page_num)
                if image_path and not skip_ocr:
                    text = self.run_ocr(image_path, page_num)
                    if text:
                        entries = self.extract_glossary_entries(text, page_num)
                        if entries:
                            self.save_to_database(entries)
                            logger.info(f"Found {len(entries)} entries on page {page_num}")
                time.sleep(self.delay)
        logger.info("Exporting results...")
        self.export_glossary("all")
        self.create_pdf()
        self.cleanup_temp()
        conn = sqlite3.connect(self.db_path)
        en_ar_count = conn.execute("SELECT COUNT(*) FROM en_ar_glossary").fetchone()[0]
        ar_en_count = conn.execute("SELECT COUNT(*) FROM ar_en_glossary").fetchone()[0]
        conn.close()
        logger.info("=" * 70)
        logger.info("EXTRACTION COMPLETE")
        logger.info(f"English->Arabic entries: {en_ar_count}")
        logger.info(f"Arabic->English entries: {ar_en_count}")
        logger.info(f"Output directory: {self.output_dir}")
        logger.info("=" * 70)
        return True


def main():
    parser = argparse.ArgumentParser(description="Archive.org Book Extractor v2.0")
    parser.add_argument("--url", required=True, help="Book URL on Archive.org")
    parser.add_argument("--email", help="Archive.org email")
    parser.add_argument("--password", help="Archive.org password")
    parser.add_argument("--mode", choices=["iiif", "selenium", "manual"], default="iiif", help="Extraction mode")
    parser.add_argument("--pages", type=int, default=100, help="Number of pages")
    parser.add_argument("--start-page", type=int, default=1, help="Start page")
    parser.add_argument("--end-page", type=int, help="End page")
    parser.add_argument("--output", default="./archive_output", help="Output directory")
    parser.add_argument("--delay", type=float, default=2.5, help="Delay between downloads")
    parser.add_argument("--skip-download", action="store_true", help="Skip download")
    parser.add_argument("--skip-ocr", action="store_true", help="Skip OCR")
    args = parser.parse_args()
    if args.end_page is None:
        args.end_page = args.start_page + args.pages - 1
    extractor = ArchiveBookExtractor(
        email=args.email or os.environ.get("ARCHIVE_EMAIL", ""),
        password=args.password or os.environ.get("ARCHIVE_PASSWORD", ""),
        output_dir=args.output,
        mode=args.mode,
        delay=args.delay
    )
    extractor.run(
        book_url=args.url,
        start_page=args.start_page,
        end_page=args.end_page,
        skip_download=args.skip_download,
        skip_ocr=args.skip_ocr
    )


if __name__ == '__main__':
    main()