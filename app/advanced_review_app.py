#!/usr/bin/env python3
"""
advanced_review_app.py — OmniFile_Processor / omni-medical-suite
===============================================================
Gradio application with full "Scanner Fixer" tab.

Tabs:
  1. Single Image — Before/After preview (gr.State) + manual save only
  2. Batch Mode — PDF + Folder + random preview + Save All as ZIP

Author: Z.ai
Updated: 2026-07-17
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
# BUILD THE APP
# ===========================================================================

def build_app() -> gr.Blocks:
    """Construct and return the Gradio application."""

    with gr.Blocks(
        title="OmniFile Processor — Scanner Fixer",
        theme=gr.themes.Soft(primary_hue="blue", secondary_hue="green"),
        css="""
            .before-after-row { display: flex; gap: 16px; justify-content: center; }
            .before-after-row > div { flex: 1; text-align: center; }
            .tab-title { font-size: 1.2em; font-weight: bold; margin-bottom: 8px; }
        """,
    ) as app:

        gr.Markdown(
            "# OmniFile Processor — Scanner Fixer v2.1\n"
            "Smart image correction for scanned documents. "
            "Auto-rotate, deskew, denoise, sharpen, contrast fix, border removal.\n"
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
        # FOOTER
        # ===================================================================
        gr.Markdown(
            "---\n"
            "OmniFile Processor | Scanner Fixer v2.1 | "
            "Engine: Tesseract OSD + Hough + Projection Profile | "
            "Manjaro-ready"
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