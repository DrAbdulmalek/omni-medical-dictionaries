#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Hitti Glossary Builder - Gradio Web Interface
===============================================
Web UI for Archive.org extraction + OCR + Glossary management
Author: DrAbdulmalek / Z.ai
"""

import os
import sys
import json
import sqlite3
import shutil
import zipfile
from pathlib import Path
from datetime import datetime

import gradio as gr
from PIL import Image
import cv2
import numpy as np

sys.path.insert(0, "../scripts")
from archive_book_extractor import ArchiveBookExtractor, GlossaryEntry

DB_PATH = Path("./glossary_output/hitti_glossary.db")
DB_PATH.parent.mkdir(parents=True, exist_ok=True)


def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS en_ar_glossary (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            english_term TEXT NOT NULL,
            arabic_term TEXT,
            page_num INTEGER,
            context TEXT,
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
            confidence REAL DEFAULT 0.0,
            verified INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()


def extract_from_archive(url, email, password, start_page, end_page, mode, delay):
    try:
        output_dir = "./glossary_output"
        extractor = ArchiveBookExtractor(
            email=email, password=password,
            output_dir=output_dir, mode=mode, delay=delay
        )
        success = extractor.run(
            book_url=url,
            start_page=int(start_page),
            end_page=int(end_page) if end_page else None
        )
        if success:
            return "Extraction complete! Check the Glossary tabs."
        return "Extraction failed. Check logs."
    except Exception as e:
        return f"Error: {str(e)}"


def process_uploaded_images(files):
    try:
        import pytesseract
        output_dir = Path("./glossary_output")
        output_dir.mkdir(exist_ok=True)
        (output_dir / "pages").mkdir(exist_ok=True)
        (output_dir / "ocr").mkdir(exist_ok=True)
        total_entries = 0
        for i, file_path in enumerate(files):
            page_num = i + 1
            img = cv2.imread(file_path)
            if img is None:
                continue
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
            text = pytesseract.image_to_string(binary, lang='eng+ara', config='--psm 6 --oem 3')
            ocr_path = output_dir / "ocr" / f"page_{page_num:04d}.txt"
            with open(ocr_path, "w", encoding="utf-8") as f:
                f.write(text)
            extractor = ArchiveBookExtractor("", "", str(output_dir))
            entries = extractor.extract_glossary_entries(text, page_num)
            if entries:
                extractor.save_to_database(entries)
                total_entries += len(entries)
        extractor.export_glossary("all")
        return f"Processed {len(files)} images. Found {total_entries} glossary entries."
    except Exception as e:
        return f"Error: {str(e)}"


def search_glossary(query, direction):
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        if direction == "en->ar":
            cursor.execute(
                "SELECT english_term, arabic_term, page_num, confidence FROM en_ar_glossary WHERE english_term LIKE ? ORDER BY english_term",
                (f"%{query}%",)
            )
        else:
            cursor.execute(
                "SELECT arabic_term, english_term, page_num, confidence FROM ar_en_glossary WHERE arabic_term LIKE ? ORDER BY arabic_term",
                (f"%{query}%",)
            )
        results = cursor.fetchall()
        conn.close()
        if not results:
            return "No results found."
        output = []
        for row in results[:50]:
            conf = f"[{row[3]:.1f}]" if row[3] else ""
            output.append(f"{row[0]} -> {row[1]} | Page {row[2]} {conf}")
        return "\n".join(output)
    except Exception as e:
        return f"Error: {str(e)}"


def get_stats():
    try:
        conn = sqlite3.connect(DB_PATH)
        en_ar = conn.execute("SELECT COUNT(*) FROM en_ar_glossary").fetchone()[0]
        ar_en = conn.execute("SELECT COUNT(*) FROM ar_en_glossary").fetchone()[0]
        conn.close()
        return f"English->Arabic: {en_ar} entries\nArabic->English: {ar_en} entries\nTotal: {en_ar + ar_en} entries"
    except Exception as e:
        return f"Error: {str(e)}"


def export_glossary_zip():
    try:
        output_dir = Path("./glossary_output")
        zip_path = output_dir / "hitti_glossary_export.zip"
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for f in (output_dir / "glossary").glob("*"):
                zf.write(f, f.name)
            if (output_dir / "hitti_glossary.db").exists():
                zf.write(output_dir / "hitti_glossary.db", "hitti_glossary.db")
        return str(zip_path)
    except Exception as e:
        return f"Error: {str(e)}"


def verify_entry(entry_id, direction, corrected_term):
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        table = "en_ar_glossary" if direction == "en->ar" else "ar_en_glossary"
        cursor.execute(f"UPDATE {table} SET verified = 1 WHERE id = ?", (entry_id,))
        if corrected_term:
            if direction == "en->ar":
                cursor.execute("UPDATE en_ar_glossary SET arabic_term = ? WHERE id = ?", (corrected_term, entry_id))
            else:
                cursor.execute("UPDATE ar_en_glossary SET english_term = ? WHERE id = ?", (corrected_term, entry_id))
        conn.commit()
        conn.close()
        return "Entry verified and updated."
    except Exception as e:
        return f"Error: {str(e)}"


def create_interface():
    init_db()
    with gr.Blocks(title="Hitti Glossary Builder", theme=gr.themes.Soft()) as demo:
        gr.Markdown("# 📚 Hitti Glossary Builder")
        gr.Markdown("Extract, OCR, and build medical glossaries from Archive.org books")
        
        with gr.Tabs():
            
            with gr.TabItem("🔌 Archive.org Extractor"):
                gr.Markdown("### Extract directly from Archive.org")
                with gr.Row():
                    url = gr.Textbox(label="Book URL", value="https://archive.org/details/hittisnewmedical0000hitt")
                    mode = gr.Dropdown(["iiif", "selenium", "manual"], value="iiif", label="Mode")
                with gr.Row():
                    email = gr.Textbox(label="Email")
                    password = gr.Textbox(label="Password", type="password")
                with gr.Row():
                    start_page = gr.Number(label="Start Page", value=1)
                    end_page = gr.Number(label="End Page", value=50)
                    delay = gr.Number(label="Delay (sec)", value=2.5)
                extract_btn = gr.Button("Start Extraction", variant="primary")
                extract_status = gr.Textbox(label="Status", lines=5)
                extract_btn.click(
                    extract_from_archive,
                    [url, email, password, start_page, end_page, mode, delay],
                    extract_status
                )
            
            with gr.TabItem("📁 Upload Images"):
                gr.Markdown("### Upload scanned pages manually")
                upload_files = gr.File(label="Upload Images", file_count="multiple", file_types=["image"])
                process_btn = gr.Button("Process Images", variant="primary")
                upload_status = gr.Textbox(label="Status", lines=5)
                process_btn.click(process_uploaded_images, upload_files, upload_status)
            
            with gr.TabItem("🔍 Search Glossary"):
                gr.Markdown("### Search extracted glossary")
                with gr.Row():
                    query = gr.Textbox(label="Search Term")
                    direction = gr.Dropdown(["en->ar", "ar->en"], value="en->ar", label="Direction")
                search_btn = gr.Button("Search", variant="primary")
                search_results = gr.Textbox(label="Results", lines=15)
                search_btn.click(search_glossary, [query, direction], search_results)
            
            with gr.TabItem("📊 Statistics"):
                stats_btn = gr.Button("Refresh Stats", variant="primary")
                stats_output = gr.Textbox(label="Statistics", lines=5)
                stats_btn.click(get_stats, [], stats_output)
                
                gr.Markdown("### Export")
                export_btn = gr.Button("Export as ZIP", variant="secondary")
                export_file = gr.File(label="Download ZIP")
                export_btn.click(export_glossary_zip, [], export_file)
            
            with gr.TabItem("✅ Verify Entries"):
                gr.Markdown("### Verify and correct glossary entries")
                with gr.Row():
                    entry_id = gr.Number(label="Entry ID")
                    verify_dir = gr.Dropdown(["en->ar", "ar->en"], value="en->ar", label="Direction")
                corrected = gr.Textbox(label="Corrected Term (optional)")
                verify_btn = gr.Button("Verify Entry", variant="primary")
                verify_status = gr.Textbox(label="Status")
                verify_btn.click(verify_entry, [entry_id, verify_dir, corrected], verify_status)
    
    return demo


if __name__ == "__main__":
    demo = create_interface()
    demo.launch(server_name="0.0.0.0", server_port=7860, share=True)