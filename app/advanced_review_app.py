#!/usr/bin/env python3
"""
advanced_review_app.py — Omni Medical Suite
=============================================
Gradio application with Scanner Fixer + Archive Extractor + Glossary Builder.

Tabs:
  1. Single Image — Before/After preview (gr.State) + manual save only
  2. Batch Mode — PDF + Folder + random preview + Save All as ZIP
  3. Archive Extractor — Download from Archive.org + OCR + glossary extraction
  4. Glossary Search — Search & export extracted medical terms

Author: DrAbdulmalek / Z.ai
Updated: 2026-07-18
"""

import os
import sys
import time
import logging
import tempfile
import shutil
import zipfile
from pathlib import Path
from typing import Optional, Tuple, List

import gradio as gr
import numpy as np
from PIL import Image

# ---------------------------------------------------------------------------
# Add project root to path so we can import packages
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from packages.preprocessors.scanner_fixer import (
    fix_scanner_image,
    pil_to_cv2,
    cv2_to_pil,
    batch_fix_folder,
    batch_fix_to_zip,
    get_random_preview,
    _load_pdf_pages,
    _make_tmp,
    __version__,
)

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
LOG_DIR = PROJECT_ROOT / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / "app.log", encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger("advanced_review_app")

# ---------------------------------------------------------------------------
# State keys for gr.State
# ---------------------------------------------------------------------------
STATE_KEY_ORIGINAL = "original_cv2"
STATE_KEY_FIXED = "fixed_cv2"
STATE_KEY_OUTPUT_PATH = "output_path"

# ===========================================================================
# SINGLE IMAGE TAB CALLBACKS
# ===========================================================================

def single_upload(image: Optional[Image.Image], state: dict) -> Tuple:
    """
    When user uploads an image: show it as Before, store in state.
    No processing yet — user clicks 'Process' explicitly.
    """
    if image is None:
        return None, None, state, "Upload an image first."
    state = state or {}
    cv_img = pil_to_cv2(image)
    state[STATE_KEY_ORIGINAL] = cv_img
    state[STATE_KEY_FIXED] = None
    state[STATE_KEY_OUTPUT_PATH] = None
    return image, None, state, f"Image loaded: {image.size[0]}x{image.size[1]} px"


def single_process(state: dict, do_rotate, do_deskew, do_denoise,
                   do_sharpen, do_contrast, do_border, denoise_strength) -> Tuple:
    """
    Process the stored original image. Show Before + After.
    Results stored in state only — NOT saved to disk.
    """
    if not state or STATE_KEY_ORIGINAL not in state:
        return None, None, state, "No image loaded. Upload an image first."

    original_cv2 = state[STATE_KEY_ORIGINAL]
    try:
        fixed_cv2 = fix_scanner_image(
            original_cv2,
            do_rotate=do_rotate,
            do_deskew=do_deskew,
            do_denoise=do_denoise,
            do_sharpen=do_sharpen,
            do_contrast=do_contrast,
            do_border=do_border,
            denoise_strength=int(denoise_strength),
        )
        state[STATE_KEY_FIXED] = fixed_cv2
        original_pil = cv2_to_pil(original_cv2)
        fixed_pil = cv2_to_pil(fixed_cv2)
        h, w = fixed_cv2.shape[:2]
        return original_pil, fixed_pil, state, f"Processed: {w}x{h} px — Ready to save."
    except Exception as exc:
        logger.error("single_process error: %s", exc)
        orig_pil = cv2_to_pil(original_cv2)
        return orig_pil, None, state, f"Error during processing: {exc}"


def single_save(image: Optional[Image.Image], state: dict, filename: str) -> Tuple:
    """
    Manual save only — user clicks 'Save' explicitly.
    Saves the FIXED image to the downloads/ directory.
    """
    if not state or STATE_KEY_FIXED not in state:
        return state, "Nothing to save. Process an image first."

    fixed_cv2 = state[STATE_KEY_FIXED]
    if fixed_cv2 is None:
        return state, "Nothing to save. Process an image first."

    downloads_dir = PROJECT_ROOT / "downloads"
    downloads_dir.mkdir(parents=True, exist_ok=True)

    if not filename:
        filename = f"scanner_fixed_{int(time.time())}.png"

    if not filename.lower().endswith((".png", ".jpg", ".jpeg", ".tiff", ".tif", ".bmp")):
        filename += ".png"

    out_path = downloads_dir / filename
    success = cv2.imwrite(str(out_path), fixed_cv2)
    if success:
        state[STATE_KEY_OUTPUT_PATH] = str(out_path)
        size_kb = out_path.stat().st_size / 1024
        logger.info("User saved: %s (%.1f KB)", out_path, size_kb)
        return state, f"Saved: {out_path.name} ({size_kb:.1f} KB)"
    return state, f"Failed to save: {out_path}"


def single_reset(state: dict) -> Tuple:
    """Clear all state and reset UI."""
    return None, None, None, {}, "Reset complete."


# ===========================================================================
# BATCH TAB CALLBACKS
# ===========================================================================

def batch_process_folder(
    folder_path: str,
    do_rotate, do_deskew, do_denoise,
    do_sharpen, do_contrast, do_border,
    denoise_strength, recursive,
    state: dict,
) -> Tuple:
    """
    Process all images in a folder.
    Returns: count message, updates state with output paths.
    """
    if not folder_path or not os.path.isdir(folder_path):
        return "Invalid folder path.", [], state

    state = state or {}
    try:
        kwargs = dict(
            do_rotate=do_rotate,
            do_deskew=do_deskew,
            do_denoise=do_denoise,
            do_sharpen=do_sharpen,
            do_contrast=do_contrast,
            do_border=do_border,
            denoise_strength=int(denoise_strength),
        )
        output_paths = batch_fix_folder(
            folder_path,
            recursive=recursive,
            **kwargs,
        )
        state["batch_output_paths"] = output_paths
        state["batch_source"] = folder_path

        if not output_paths:
            return "No image files found in folder.", [], state

        return f"Fixed {len(output_paths)} images.", output_paths, state

    except Exception as exc:
        logger.error("batch_process_folder error: %s", exc)
        return f"Error: {exc}", [], state


def batch_process_pdf(
    pdf_file,
    do_rotate, do_deskew, do_denoise,
    do_sharpen, do_contrast, do_border,
    denoise_strength,
    state: dict,
) -> Tuple:
    """
    Process a multi-page PDF file.
    """
    if pdf_file is None:
        return "Upload a PDF file first.", [], state

    state = state or {}
    try:
        # Save uploaded PDF to temp
        tmp_dir = _make_tmp("sf_upload_")
        pdf_path = os.path.join(tmp_dir, pdf_file.name)
        with open(pdf_path, "wb") as f:
            f.write(pdf_file.read())

        kwargs = dict(
            do_rotate=do_rotate,
            do_deskew=do_deskew,
            do_denoise=do_denoise,
            do_sharpen=do_sharpen,
            do_contrast=do_contrast,
            do_border=do_border,
            denoise_strength=int(denoise_strength),
        )

        # Load pages
        pages = _load_pdf_pages(pdf_path)
        if not pages:
            return "PDF has no pages or could not be read.", [], state

        # Process each page
        output_dir = PROJECT_ROOT / "downloads" / Path(pdf_file.name).stem
        output_dir.mkdir(parents=True, exist_ok=True)

        output_paths = []
        for i, page_cv2 in enumerate(pages):
            fixed = fix_scanner_image(page_cv2, **kwargs)
            out_name = f"page_{i + 1:04d}.png"
            out_path = str(output_dir / out_name)
            cv2.imwrite(out_path, fixed)
            output_paths.append(out_path)

        state["batch_output_paths"] = output_paths
        state["batch_source"] = pdf_path

        return f"PDF processed: {len(output_paths)} pages saved to downloads/{Path(pdf_file.name).stem}/", output_paths, state

    except Exception as exc:
        logger.error("batch_process_pdf error: %s", exc)
        return f"Error: {exc}", [], state


def batch_random_preview(
    folder_path: str,
    n_preview: int,
    do_rotate, do_deskew, do_denoise,
    do_sharpen, do_contrast, do_border,
    denoise_strength,
) -> Tuple:
    """
    Show random before/after pairs from a folder.
    Returns a flat list: [before1, after1, before2, after2, ...]
    """
    if not folder_path or not os.path.isdir(folder_path):
        return [], "Invalid folder path."

    try:
        kwargs = dict(
            do_rotate=do_rotate,
            do_deskew=do_deskew,
            do_denoise=do_denoise,
            do_sharpen=do_sharpen,
            do_contrast=do_contrast,
            do_border=do_border,
            denoise_strength=int(denoise_strength),
        )
        pairs = get_random_preview(folder_path, n=int(n_preview), **kwargs)
        if not pairs:
            return [], "No image files found in folder."

        gallery_items = []
        for orig, fixed in pairs:
            gallery_items.append(cv2_to_pil(orig))
            gallery_items.append(cv2_to_pil(fixed))

        return gallery_items, f"Random preview: {len(pairs)} image pairs (odd=Before, even=After)"
    except Exception as exc:
        logger.error("batch_random_preview error: %s", exc)
        return [], f"Error: {exc}"


def batch_save_zip(state: dict) -> Tuple:
    """
    Save all batch results as a single ZIP file.
    Manual only — user must click explicitly.
    """
    if not state or "batch_output_paths" not in state:
        return None, "No batch results to save. Process files first."

    output_paths = state["batch_output_paths"]
    if not output_paths:
        return None, "No files were processed."

    try:
        downloads_dir = PROJECT_ROOT / "downloads"
        downloads_dir.mkdir(parents=True, exist_ok=True)

        zip_name = f"scanner_fixed_{int(time.time())}.zip"
        zip_path = downloads_dir / zip_name

        with zipfile.ZipFile(str(zip_path), "w", zipfile.ZIP_DEFLATED) as zf:
            for fp in output_paths:
                if os.path.isfile(fp):
                    arcname = os.path.basename(fp)
                    zf.write(fp, arcname)

        size_mb = zip_path.stat().st_size / (1024 * 1024)
        logger.info("ZIP saved: %s (%.2f MB, %d files)", zip_path, size_mb, len(output_paths))
        return str(zip_path), f"ZIP saved: {zip_name} ({size_mb:.2f} MB, {len(output_paths)} files)"
    except Exception as exc:
        logger.error("batch_save_zip error: %s", exc)
        return None, f"Error creating ZIP: {exc}"


# ===========================================================================
# ARCHIVE EXTRACTOR CALLBACKS
# ===========================================================================

GLOSSARY_DIR = PROJECT_ROOT / "glossary_output"
GLOSSARY_DB = GLOSSARY_DIR / "hitti_glossary.db"


def _init_glossary_db():
    """Ensure the glossary database exists."""
    import sqlite3
    GLOSSARY_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(GLOSSARY_DB)
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS en_ar_glossary (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        english_term TEXT NOT NULL, arabic_term TEXT,
        page_num INTEGER, context TEXT,
        confidence REAL DEFAULT 0.0, verified INTEGER DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS ar_en_glossary (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        arabic_term TEXT NOT NULL, english_term TEXT,
        page_num INTEGER, context TEXT,
        confidence REAL DEFAULT 0.0, verified INTEGER DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")
    conn.commit()
    conn.close()


def archive_extract(url, email, password, start_page, end_page, mode, delay):
    """Run Archive.org book extraction."""
    try:
        _init_glossary_db()
        scripts_path = PROJECT_ROOT / "scripts"
        sys.path.insert(0, str(scripts_path))
        from archive_book_extractor import ArchiveBookExtractor

        output_dir = str(GLOSSARY_DIR)
        extractor = ArchiveBookExtractor(
            email=email, password=password,
            output_dir=output_dir, mode=mode,
            delay=float(delay),
        )
        success = extractor.run(
            book_url=url,
            start_page=int(start_page),
            end_page=int(end_page) if end_page else None,
        )
        if success:
            return f"Extraction complete. Use the 'Glossary Search' tab to browse results."
        return "Extraction failed. Check logs/extractor.log for details."
    except ImportError as exc:
        return f"Missing dependency: {exc}. Install with: pip install requests selenium webdriver-manager"
    except Exception as exc:
        logger.error("archive_extract error: %s", exc)
        return f"Error: {exc}"


def glossary_search(query, direction):
    """Search the glossary database."""
    import sqlite3
    try:
        _init_glossary_db()
        conn = sqlite3.connect(GLOSSARY_DB)
        cursor = conn.cursor()
        if direction == "en->ar":
            cursor.execute(
                "SELECT english_term, arabic_term, page_num, confidence "
                "FROM en_ar_glossary WHERE english_term LIKE ? ORDER BY english_term LIMIT 100",
                (f"%{query}%",),
            )
        else:
            cursor.execute(
                "SELECT arabic_term, english_term, page_num, confidence "
                "FROM ar_en_glossary WHERE arabic_term LIKE ? ORDER BY arabic_term LIMIT 100",
                (f"%{query}%",),
            )
        rows = cursor.fetchall()
        conn.close()
        if not rows:
            return "No results found. Try extracting a book first."
        lines = []
        for term1, term2, page, conf in rows:
            conf_str = f"[{conf:.1f}]" if conf else ""
            lines.append(f"{term1:<30} -> {term2:<30} | p.{page} {conf_str}")
        return "\n".join(lines)
    except Exception as exc:
        return f"Error: {exc}"


def glossary_stats():
    """Get glossary statistics."""
    import sqlite3
    try:
        _init_glossary_db()
        conn = sqlite3.connect(GLOSSARY_DB)
        en_ar = conn.execute("SELECT COUNT(*) FROM en_ar_glossary").fetchone()[0]
        ar_en = conn.execute("SELECT COUNT(*) FROM ar_en_glossary").fetchone()[0]
        conn.close()
        return (
            f"English -> Arabic: {en_ar} entries\n"
            f"Arabic -> English: {ar_en} entries\n"
            f"Total: {en_ar + ar_en} entries\n"
            f"Database: {GLOSSARY_DB}"
        )
    except Exception as exc:
        return f"Error: {exc}"


def glossary_export_zip():
    """Export all glossary data as a ZIP file."""
    import sqlite3, zipfile
    try:
        zip_path = GLOSSARY_DIR / "hitti_glossary_export.zip"
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for f in (GLOSSARY_DIR / "glossary").glob("*"):
                if f.is_file():
                    zf.write(f, f.name)
            if GLOSSARY_DB.exists():
                zf.write(GLOSSARY_DB, "hitti_glossary.db")
        return str(zip_path)
    except Exception as exc:
        logger.error("glossary_export_zip error: %s", exc)
        return f"Error: {exc}"


# ===========================================================================
# BUILD THE APP
# ===========================================================================

def build_app() -> gr.Blocks:
    """Construct and return the Gradio application."""

    with gr.Blocks(
        title="Omni Medical Suite — Scanner Fixer + Glossary Builder",
        theme=gr.themes.Soft(primary_hue="blue", secondary_hue="green"),
        css="""
            .before-after-row { display: flex; gap: 16px; justify-content: center; }
            .before-after-row > div { flex: 1; text-align: center; }
            .tab-title { font-size: 1.2em; font-weight: bold; margin-bottom: 8px; }
        """,
    ) as app:

        gr.Markdown(
            "# Omni Medical Suite\n"
            "Smart scanner image correction + Archive.org glossary builder\n"
            "**Manual save only** — your files are not saved until you click Save."
        )

        # ===================================================================
        # TAB 1: SINGLE IMAGE
        # ===================================================================
        with gr.Tab("Single Image"):

            gr.Markdown("### Upload an image, adjust settings, click **Process**, then **Save** manually.")
            state_single = gr.State(value={})

            with gr.Row():
                with gr.Column():
                    input_image = gr.Image(
                        label="Upload Image",
                        type="pil",
                        height=350,
                        sources=["upload", "clipboard"],
                    )
                    file_name = gr.Textbox(
                        label="Output Filename",
                        placeholder="scanner_fixed.png",
                        value="scanner_fixed.png",
                    )

                with gr.Column():
                    with gr.Row():
                        before_image = gr.Image(label="Before", type="pil", height=300, interactive=False)
                        after_image = gr.Image(label="After", type="pil", height=300, interactive=False)

            # Settings accordion
            with gr.Accordion("Settings", open=True):
                with gr.Row():
                    do_rotate = gr.Checkbox(label="Auto-Rotate", value=True)
                    do_deskew = gr.Checkbox(label="Deskew", value=True)
                    do_denoise = gr.Checkbox(label="Denoise", value=True)
                    do_sharpen = gr.Checkbox(label="Sharpen", value=True)
                    do_contrast = gr.Checkbox(label="Fix Contrast", value=True)
                    do_border = gr.Checkbox(label="Remove Borders", value=True)
                denoise_strength = gr.Slider(
                    label="Denoise Strength", minimum=1, maximum=30, value=10, step=1
                )

            with gr.Row():
                btn_process = gr.Button("Process", variant="primary", size="lg")
                btn_save = gr.Button("Save Image", variant="secondary", size="lg")
                btn_reset = gr.Button("Reset", variant="stop", size="sm")

            status_single = gr.Textbox(
                label="Status", interactive=False, show_label=True,
                max_lines=3,
            )

            # --- Events ---
            input_image.change(
                fn=single_upload,
                inputs=[input_image, state_single],
                outputs=[before_image, after_image, state_single, status_single],
            )

            btn_process.click(
                fn=single_process,
                inputs=[
                    state_single, do_rotate, do_deskew, do_denoise,
                    do_sharpen, do_contrast, do_border, denoise_strength,
                ],
                outputs=[before_image, after_image, state_single, status_single],
            )

            btn_save.click(
                fn=single_save,
                inputs=[after_image, state_single, file_name],
                outputs=[state_single, status_single],
            )

            btn_reset.click(
                fn=single_reset,
                inputs=[state_single],
                outputs=[before_image, after_image, input_image, state_single, status_single],
            )

        # ===================================================================
        # TAB 2: BATCH MODE
        # ===================================================================
        with gr.Tab("Batch Mode"):
            state_batch = gr.State(value={})

            gr.Markdown(
                "### Process a folder of images or a multi-page PDF.\n"
                "Use **Random Preview** to check quality, then **Save All as ZIP**."
            )

            # Sub-tabs for Folder vs PDF
            with gr.Tabs():
                with gr.Tab("Folder"):
                    folder_input = gr.Textbox(
                        label="Folder Path",
                        placeholder="/path/to/your/scanned/images",
                    )
                    with gr.Row():
                        recursive_cb = gr.Checkbox(label="Recursive (subfolders)", value=True)
                        btn_process_folder = gr.Button("Process Folder", variant="primary")

                with gr.Tab("PDF"):
                    pdf_input = gr.File(
                        label="Upload PDF",
                        file_types=[".pdf"],
                    )
                    btn_process_pdf = gr.Button("Process PDF", variant="primary")

            # Shared settings
            with gr.Accordion("Batch Settings", open=True):
                with gr.Row():
                    b_rotate = gr.Checkbox(label="Auto-Rotate", value=True)
                    b_deskew = gr.Checkbox(label="Deskew", value=True)
                    b_denoise = gr.Checkbox(label="Denoise", value=True)
                    b_sharpen = gr.Checkbox(label="Sharpen", value=True)
                    b_contrast = gr.Checkbox(label="Fix Contrast", value=True)
                    b_border = gr.Checkbox(label="Remove Borders", value=True)
                b_denoise_str = gr.Slider(
                    label="Denoise Strength", minimum=1, maximum=30, value=10, step=1
                )

            # Random Preview section
            with gr.Accordion("Random Preview (Before / After)", open=False):
                with gr.Row():
                    preview_folder = gr.Textbox(
                        label="Preview Folder Path",
                        placeholder="Same folder or different",
                        scale=3,
                    )
                    n_preview = gr.Slider(
                        label="Count", minimum=2, maximum=10, value=4, step=2,
                        scale=1,
                    )
                    btn_preview = gr.Button("Generate Preview", variant="secondary")

                preview_gallery = gr.Gallery(
                    label="Random Pairs (odd index = Before, even = After)",
                    columns=4,
                    rows=2,
                    height=300,
                    object_fit="contain",
                )
                preview_status = gr.Textbox(label="Preview Status", interactive=False)

            # Results & ZIP
            batch_status = gr.Textbox(label="Batch Status", interactive=False, max_lines=3)
            batch_gallery = gr.Gallery(
                label="Fixed Images (first 20)",
                columns=4,
                height=250,
                object_fit="contain",
            )
            with gr.Row():
                btn_zip = gr.Button("Save All as ZIP", variant="primary", size="lg")
                zip_file = gr.File(label="Download ZIP", interactive=False)

            # --- Events ---
            btn_process_folder.click(
                fn=batch_process_folder,
                inputs=[
                    folder_input,
                    b_rotate, b_deskew, b_denoise,
                    b_sharpen, b_contrast, b_border,
                    b_denoise_str, recursive_cb,
                    state_batch,
                ],
                outputs=[batch_status, batch_gallery, state_batch],
            )

            btn_process_pdf.click(
                fn=batch_process_pdf,
                inputs=[
                    pdf_input,
                    b_rotate, b_deskew, b_denoise,
                    b_sharpen, b_contrast, b_border,
                    b_denoise_str,
                    state_batch,
                ],
                outputs=[batch_status, batch_gallery, state_batch],
            )

            btn_preview.click(
                fn=batch_random_preview,
                inputs=[
                    preview_folder, n_preview,
                    b_rotate, b_deskew, b_denoise,
                    b_sharpen, b_contrast, b_border,
                    b_denoise_str,
                ],
                outputs=[preview_gallery, preview_status],
            )

            btn_zip.click(
                fn=batch_save_zip,
                inputs=[state_batch],
                outputs=[zip_file, batch_status],
            )

        # ===================================================================
        # TAB 3: ARCHIVE EXTRACTOR
        # ===================================================================
        with gr.Tab("Archive Extractor"):
            gr.Markdown(
                "### Extract pages from Archive.org books\n"
                "Uses IIIF API to download pages, then runs OCR + glossary extraction.\n"
                "Book must be borrowable on Archive.org."
            )
            with gr.Row():
                archive_url = gr.Textbox(
                    label="Book URL",
                    value="https://archive.org/details/hittisnewmedical0000hitt",
                    scale=3,
                )
                archive_mode = gr.Dropdown(
                    ["iiif", "selenium", "manual"],
                    value="iiif",
                    label="Mode",
                    scale=1,
                )
            with gr.Row():
                archive_email = gr.Textbox(label="Email", type="password", scale=1)
                archive_password = gr.Textbox(label="Password", type="password", scale=1)
            with gr.Row():
                archive_start = gr.Number(label="Start Page", value=1, scale=1)
                archive_end = gr.Number(label="End Page", value=50, scale=1)
                archive_delay = gr.Number(label="Delay (sec)", value=2.5, scale=1)
            with gr.Row():
                btn_extract = gr.Button("Start Extraction", variant="primary")
            archive_status = gr.Textbox(label="Extraction Status", lines=8, interactive=False)

            btn_extract.click(
                fn=archive_extract,
                inputs=[archive_url, archive_email, archive_password,
                        archive_start, archive_end, archive_mode, archive_delay],
                outputs=[archive_status],
            )

        # ===================================================================
        # TAB 4: GLOSSARY SEARCH
        # ===================================================================
        with gr.Tab("Glossary Search"):
            gr.Markdown(
                "### Search extracted medical glossary\n"
                "Searches the local SQLite database of extracted terms."
            )
            with gr.Row():
                gloss_query = gr.Textbox(
                    label="Search Term",
                    placeholder="e.g. abdominal or بطني",
                    scale=2,
                )
                gloss_dir = gr.Dropdown(
                    ["en->ar", "ar->en"],
                    value="en->ar",
                    label="Direction",
                    scale=1,
                )
                btn_search = gr.Button("Search", variant="primary")
            gloss_results = gr.Textbox(label="Results", lines=15, interactive=False)

            with gr.Row():
                btn_stats = gr.Button("Show Statistics")
            gloss_stats = gr.Textbox(label="Statistics", interactive=False)

            with gr.Row():
                btn_export_zip = gr.Button("Export All as ZIP", variant="secondary")
                gloss_zip = gr.File(label="Download ZIP")

            btn_search.click(
                fn=glossary_search,
                inputs=[gloss_query, gloss_dir],
                outputs=[gloss_results],
            )
            btn_stats.click(fn=glossary_stats, outputs=[gloss_stats])
            btn_export_zip.click(fn=glossary_export_zip, outputs=[gloss_zip])

        # ===================================================================
        # FOOTER
        # ===================================================================
        gr.Markdown(
            "---\n"
            "Omni Medical Suite | Scanner Fixer v2.1 + Glossary Builder | "
            "Engine: Tesseract OSD + Hough + Projection Profile | "
            "Manjaro-ready | "
            "[Tampermonkey Script](scripts/archive-downloader.user.js) for fast downloads"
        )

    return app


# ===========================================================================
# MAIN
# ===========================================================================

def main():
    """Launch the application."""
    logger.info("Starting OmniFile Processor — Scanner Fixer v%s", __version__)
    logger.info("Project root: %s", PROJECT_ROOT)
    logger.info("Downloads dir: %s", PROJECT_ROOT / "downloads")

    app = build_app()
    app.launch(
        server_name="0.0.0.0",
        server_port=7860,
        share=False,
        show_error=True,
    )


if __name__ == "__main__":
    main()