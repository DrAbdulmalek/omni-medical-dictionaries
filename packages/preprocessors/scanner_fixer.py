#!/usr/bin/env python3
"""
scanner_fixer.py v2.1 — OmniFile_Processor / omni-medical-suite
===============================================================
Smart scanner image correction engine.

Features:
  - auto_rotate_strong: Tesseract OSD + Hough Lines + Projection Profile
  - Auto deskew, denoise, sharpen, contrast fix
  - Batch folder & multi-page PDF support (pdf2image)
  - Automatic temp-file cleanup (atexit + context manager)
  - Manjaro-ready (poppler, tesseract, opencv)

Author: Z.ai
Updated: 2026-07-17
"""

import os
import sys
import gc
import logging
import tempfile
import atexit
import shutil
import zipfile
import random
from pathlib import Path
from typing import List, Tuple, Optional, Dict, Any

import cv2
import numpy as np
from PIL import Image

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
LOG_DIR = Path(__file__).resolve().parents[2] / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / "scanner_fixer.log", encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger("scanner_fixer")

# ---------------------------------------------------------------------------
# Temp-file tracking & automatic cleanup
# ---------------------------------------------------------------------------
_temp_dirs: List[str] = []

def _register_tmp(path: str) -> None:
    _temp_dirs.append(path)

def _cleanup_all_tmp() -> None:
    for d in _temp_dirs:
        try:
            if os.path.isdir(d):
                shutil.rmtree(d, ignore_errors=True)
                logger.debug("Cleaned up temp dir: %s", d)
        except Exception as exc:
            logger.warning("Failed to clean %s: %s", d, exc)
    _temp_dirs.clear()

atexit.register(_cleanup_all_tmp)

def _make_tmp(base: str = "sf_") -> str:
    d = tempfile.mkdtemp(prefix=base)
    _register_tmp(d)
    return d

# ---------------------------------------------------------------------------
# Core Processing Functions
# ---------------------------------------------------------------------------

def _ensure_grayscale(img: np.ndarray) -> np.ndarray:
    """Convert to grayscale if needed."""
    if len(img.shape) == 2:
        return img
    return cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)


def _auto_rotate_osd(img: np.ndarray) -> Tuple[int, float]:
    """
    Use Tesseract OSD to detect orientation & rotation.
    Returns (angle_degrees, confidence).
    """
    try:
        import pytesseract
        osd_data = pytesseract.image_to_osd(img, config="--psm 0")
        angle = 0
        for line in osd_data.splitlines():
            if "Rotate in" in line:
                angle = int(line.split(":")[-1].strip())
        confidence = 5.0  # Tesseract OSD is usually reliable
        return angle, confidence
    except Exception as exc:
        logger.debug("OSD failed: %s", exc)
        return 0, 0.0


def _auto_rotate_hough(img: np.ndarray) -> Tuple[int, float]:
    """
    Detect skew angle using Hough Line Transform.
    Works well for scanned documents with text lines.
    Returns (angle_degrees, confidence).
    """
    try:
        gray = _ensure_grayscale(img)
        edges = cv2.Canny(gray, 50, 150, apertureSize=3)
        lines = cv2.HoughLines(edges, 1, np.pi / 180, threshold=100)
        if lines is None:
            return 0, 0.0

        angles = []
        for rho, theta in lines[:, 0]:
            angle = np.degrees(theta) - 90
            if abs(angle) < 45:  # ignore near-vertical lines
                angles.append(angle)

        if not angles:
            return 0, 0.0

        median_angle = float(np.median(angles))
        confidence = min(len(angles) / 50.0, 1.0) * 10.0  # 0-10
        return int(round(median_angle)), confidence
    except Exception as exc:
        logger.debug("Hough failed: %s", exc)
        return 0, 0.0


def _auto_rotate_projection(img: np.ndarray) -> Tuple[int, float]:
    """
    Detect skew angle using horizontal projection profile.
    Fast and works for mild rotations (< 15 deg).
    Returns (angle_degrees, confidence).
    """
    try:
        gray = _ensure_grayscale(img)
        thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)[1]

        # Skip if image is mostly uniform (no text content)
        content_ratio = np.count_nonzero(thresh) / thresh.size
        if content_ratio < 0.01 or content_ratio > 0.99:
            return 0, 0.0

        best_angle = 0
        best_score = 0
        h, w = thresh.shape

        for angle in range(-15, 16):
            M = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1)
            rotated = cv2.warpAffine(thresh, M, (w, h))
            proj = np.sum(rotated, axis=1)
            score = np.max(proj) - np.mean(proj)
            if score > best_score:
                best_score = score
                best_angle = angle

        confidence = (best_score / max(np.sum(thresh) / h, 1)) * 5.0
        confidence = min(confidence, 10.0)
        return best_angle, confidence
    except Exception as exc:
        logger.debug("Projection failed: %s", exc)
        return 0, 0.0


def auto_rotate_strong(img: np.ndarray) -> np.ndarray:
    """
    Multi-method rotation detection with weighted voting.
    Uses: Tesseract OSD (weight 3) + Hough (weight 2) + Projection (weight 1).
    """
    h, w = img.shape[:2]
    # Skip rotation for very small images
    if min(h, w) < 100:
        logger.debug("Image too small for rotation detection (%dx%d), skipping", w, h)
        return img

    results = [
        _auto_rotate_osd(img),       # (angle, confidence) — weight 3
        _auto_rotate_hough(img),      # weight 2
        _auto_rotate_projection(img), # weight 1
    ]
    weights = [3, 2, 1]

    total_weight = 0.0
    weighted_angle = 0.0

    for (angle, conf), w in zip(results, weights):
        if conf > 0:
            weighted_angle += angle * conf * w
            total_weight += conf * w
            logger.debug("Rotation method: angle=%d, conf=%.1f, weight=%d", angle, conf, w)

    if total_weight == 0:
        logger.info("No rotation method returned a result; keeping original orientation")
        return img

    final_angle = weighted_angle / total_weight
    final_angle = int(round(final_angle))

    if abs(final_angle) < 1:
        logger.info("Detected rotation %d° — negligible, skipping", final_angle)
        return img

    logger.info("Final rotation decision: %d° (weighted from %d methods)", final_angle,
                sum(1 for a, c in results if c > 0))

    center = (w // 2, h // 2)
    M = cv2.getRotationMatrix2D(center, final_angle, 1.0)
    rotated = cv2.warpAffine(img, M, (w, h), flags=cv2.INTER_CUBIC,
                             borderMode=cv2.BORDER_REPLICATE)
    return rotated


def deskew(img: np.ndarray) -> np.ndarray:
    """Deskew using minimum area rectangle of contours."""
    try:
        gray = _ensure_grayscale(img)
        thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)[1]
        coords = np.column_stack(np.where(thresh > 0))
        if len(coords) == 0:
            return img
        angle = cv2.minAreaRect(coords)[-1]
        if angle < -45:
            angle = -(90 + angle)
        else:
            angle = -angle
        if abs(angle) < 0.5:
            return img
        h, w = img.shape[:2]
        center = (w // 2, h // 2)
        M = cv2.getRotationMatrix2D(center, angle, 1.0)
        return cv2.warpAffine(img, M, (w, h), flags=cv2.INTER_CUBIC,
                              borderMode=cv2.BORDER_REPLICATE)
    except Exception as exc:
        logger.warning("Deskew failed: %s", exc)
        return img


def denoise(img: np.ndarray, strength: int = 10) -> np.ndarray:
    """Non-local means denoising."""
    try:
        if len(img.shape) == 2:
            return cv2.fastNlMeansDenoising(img, None, h=strength)
        return cv2.fastNlMeansDenoisingColored(img, None, h=strength, hColor=strength)
    except Exception as exc:
        logger.warning("Denoise failed: %s", exc)
        return img


def sharpen(img: np.ndarray) -> np.ndarray:
    """Unsharp mask sharpening."""
    try:
        kernel = np.array([[-1, -1, -1],
                           [-1,  9, -1],
                           [-1, -1, -1]])
        if len(img.shape) == 2:
            return cv2.filter2D(img, -1, kernel)
        return cv2.filter2D(img, -1, kernel)
    except Exception as exc:
        logger.warning("Sharpen failed: %s", exc)
        return img


def fix_contrast(img: np.ndarray, clip_limit: float = 2.0) -> np.ndarray:
    """CLAHE contrast enhancement."""
    try:
        if len(img.shape) == 2:
            clahe = cv2.createCLAHE(clipLimit=clip_limit, tileGridSize=(8, 8))
            return clahe.apply(img)
        # Color: apply on LAB L channel
        lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
        clahe = cv2.createCLAHE(clipLimit=clip_limit, tileGridSize=(8, 8))
        lab[:, :, 0] = clahe.apply(lab[:, :, 0])
        return cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)
    except Exception as exc:
        logger.warning("Contrast fix failed: %s", exc)
        return img


def remove_borders(img: np.ndarray, margin_px: int = 5) -> np.ndarray:
    """Detect and remove dark borders from scanned pages."""
    try:
        gray = _ensure_grayscale(img)
        _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
        h, w = thresh.shape

        # Skip very small images (would be cropped to nothing)
        if h < 40 or w < 40:
            return img

        # Skip if the threshold is entirely black or entirely white (no content)
        unique_vals = np.unique(thresh)
        if len(unique_vals) <= 1:
            logger.debug("No content detected for border removal (uniform image)")
            return img

        # Find the bounding box of non-border content
        x_coords = np.any(thresh[margin_px:h - margin_px, :], axis=0)
        y_coords = np.any(thresh[:, margin_px:w - margin_px], axis=1)

        if not x_coords.any() or not y_coords.any():
            logger.debug("No content detected for border removal")
            return img

        x_start, x_end = np.where(x_coords)[0][[0, -1]]
        y_start, y_end = np.where(y_coords)[0][[0, -1]]

        # Add small padding
        pad = 10
        x_start = max(0, x_start - pad)
        x_end = min(w, x_end + pad)
        y_start = max(0, y_start - pad)
        y_end = min(h, y_end + pad)

        # Ensure minimum output size (at least 20x20)
        if (x_end - x_start) < 20 or (y_end - y_start) < 20:
            logger.debug("Border removal would crop too aggressively, skipping")
            return img

        return img[y_start:y_end, x_start:x_end]
    except Exception as exc:
        logger.warning("Border removal failed: %s", exc)
        return img


# ---------------------------------------------------------------------------
# Pipeline: Full Fix
# ---------------------------------------------------------------------------

def fix_scanner_image(
    image: np.ndarray,
    do_rotate: bool = True,
    do_deskew: bool = True,
    do_denoise: bool = True,
    do_sharpen: bool = True,
    do_contrast: bool = True,
    do_border: bool = True,
    denoise_strength: int = 10,
) -> np.ndarray:
    """
    Full scanner correction pipeline.
    Returns the corrected image as numpy array (BGR or grayscale).
    """
    if image is None:
        raise ValueError("Image is None")

    logger.info("Starting scanner fix pipeline (input: %s)", image.shape)

    result = image.copy()

    try:
        if do_rotate:
            result = auto_rotate_strong(result)
        if do_deskew:
            result = deskew(result)
        if do_denoise:
            result = denoise(result, strength=denoise_strength)
        if do_contrast:
            result = fix_contrast(result)
        if do_sharpen:
            result = sharpen(result)
        if do_border:
            result = remove_borders(result)

        logger.info("Scanner fix pipeline completed (output: %s)", result.shape)
        return result
    except Exception as exc:
        logger.error("Scanner fix pipeline error: %s", exc)
        return image  # Return original on failure


def fix_image_file(
    input_path: str,
    output_path: Optional[str] = None,
    **kwargs,
) -> str:
    """
    Fix a single image file and save to output_path.
    If output_path is None, saves alongside input with '_fixed' suffix.
    Returns the output path.
    """
    input_path = str(input_path)
    if not os.path.isfile(input_path):
        raise FileNotFoundError(f"Input file not found: {input_path}")

    if output_path is None:
        p = Path(input_path)
        output_path = str(p.parent / f"{p.stem}_fixed{p.suffix}")

    img = cv2.imread(input_path)
    if img is None:
        raise ValueError(f"Cannot read image: {input_path}")

    fixed = fix_scanner_image(img, **kwargs)
    success = cv2.imwrite(output_path, fixed)
    if not success:
        raise IOError(f"Failed to write image: {output_path}")

    logger.info("Saved fixed image: %s", output_path)
    return output_path


# ---------------------------------------------------------------------------
# Batch Operations
# ---------------------------------------------------------------------------

def _load_pdf_pages(pdf_path: str, dpi: int = 200) -> List[np.ndarray]:
    """Convert PDF pages to OpenCV images using pdf2image."""
    try:
        from pdf2image import convert_from_path
    except ImportError:
        raise ImportError(
            "pdf2image is required for PDF support. "
            "On Manjaro: sudo pacman -S poppler && pip install pdf2image"
        )

    tmp_dir = _make_tmp("sf_pdf_")
    images = convert_from_path(pdf_path, dpi=dpi, output_folder=tmp_dir,
                               fmt="png", paths_only=True)
    result = []
    for img_path in images:
        cv_img = cv2.imread(img_path)
        if cv_img is not None:
            result.append(cv_img)
    logger.info("PDF '%s' → %d pages loaded", Path(pdf_path).name, len(result))
    return result


def batch_fix_folder(
    folder_path: str,
    output_folder: Optional[str] = None,
    extensions: Tuple[str, ...] = (".png", ".jpg", ".jpeg", ".tiff", ".tif", ".bmp", ".webp"),
    recursive: bool = True,
    **kwargs,
) -> List[str]:
    """
    Fix all images in a folder. Supports PDF files too.
    Returns a list of output file paths.
    """
    folder = Path(folder_path)
    if not folder.is_dir():
        raise NotADirectoryError(f"Not a directory: {folder_path}")

    if output_folder is None:
        output_folder = str(folder / "fixed")
    os.makedirs(output_folder, exist_ok=True)

    output_paths: List[str] = []
    pattern = "**/*" if recursive else "*"

    for fpath in sorted(folder.glob(pattern)):
        if fpath.is_file():
            suffix = fpath.suffix.lower()
            if suffix in extensions:
                try:
                    out = fix_image_file(str(fpath), output_folder=output_folder, **kwargs)
                    output_paths.append(out)
                except Exception as exc:
                    logger.error("Failed to fix '%s': %s", fpath.name, exc)
            elif suffix == ".pdf":
                try:
                    pdf_images = _load_pdf_pages(str(fpath))
                    pdf_out_dir = os.path.join(output_folder, fpath.stem)
                    os.makedirs(pdf_out_dir, exist_ok=True)
                    for i, cv_img in enumerate(pdf_images):
                        fixed = fix_scanner_image(cv_img, **kwargs)
                        out_name = f"{fpath.stem}_page_{i + 1:04d}.png"
                        out_path = os.path.join(pdf_out_dir, out_name)
                        cv2.imwrite(out_path, fixed)
                        output_paths.append(out_path)
                    logger.info("PDF '%s' → %d pages fixed", fpath.name, len(pdf_images))
                except Exception as exc:
                    logger.error("Failed to process PDF '%s': %s", fpath.name, exc)

    logger.info("Batch fix complete: %d/%d files processed", len(output_paths),
                len(list(folder.glob(pattern))))
    return output_paths


def batch_fix_to_zip(
    folder_path: str,
    zip_path: Optional[str] = None,
    **kwargs,
) -> str:
    """
    Fix all images in a folder and package results into a ZIP file.
    Returns the ZIP file path.
    """
    tmp_dir = _make_tmp("sf_zip_")
    fixed_paths = batch_fix_folder(folder_path, output_folder=tmp_dir, **kwargs)

    if not fixed_paths:
        raise ValueError("No images were processed — ZIP not created")

    if zip_path is None:
        zip_path = str(Path(folder_path) / "scanner_fixed_results.zip")

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for fp in fixed_paths:
            arcname = os.path.relpath(fp, tmp_dir)
            zf.write(fp, arcname)
            logger.debug("Added to ZIP: %s", arcname)

    size_mb = os.path.getsize(zip_path) / (1024 * 1024)
    logger.info("ZIP created: %s (%.2f MB, %d files)", zip_path, size_mb, len(fixed_paths))
    return zip_path


def get_random_preview(
    folder_path: str,
    output_folder: Optional[str] = None,
    n: int = 4,
    **kwargs,
) -> List[Tuple[np.ndarray, np.ndarray]]:
    """
    Fix random sample of images from a folder.
    Returns list of (original, fixed) tuples.
    """
    folder = Path(folder_path)
    extensions = {".png", ".jpg", ".jpeg", ".tiff", ".tif", ".bmp", ".webp"}
    image_files = [f for f in folder.rglob("*") if f.is_file() and f.suffix.lower() in extensions]

    if not image_files:
        return []

    sample = random.sample(image_files, min(n, len(image_files)))
    results = []

    for fpath in sample:
        img = cv2.imread(str(fpath))
        if img is None:
            continue
        fixed = fix_scanner_image(img, **kwargs)
        results.append((img, fixed))

    logger.info("Random preview: %d/%d images", len(results), len(sample))
    return results


# ---------------------------------------------------------------------------
# PIL ↔ CV2 helpers (for Gradio compatibility)
# ---------------------------------------------------------------------------

def pil_to_cv2(pil_img: Image.Image) -> np.ndarray:
    """Convert PIL Image to OpenCV BGR numpy array."""
    cv_img = np.array(pil_img)
    if len(cv_img.shape) == 2:
        return cv_img
    return cv2.cvtColor(cv_img, cv2.COLOR_RGB2BGR)


def cv2_to_pil(cv_img: np.ndarray) -> Image.Image:
    """Convert OpenCV BGR numpy array to PIL Image."""
    if len(cv_img.shape) == 2:
        return Image.fromarray(cv_img)
    return Image.fromarray(cv2.cvtColor(cv_img, cv2.COLOR_BGR2RGB))


# ---------------------------------------------------------------------------
# Version info
# ---------------------------------------------------------------------------
__version__ = "2.1"
__all__ = [
    "fix_scanner_image",
    "fix_image_file",
    "batch_fix_folder",
    "batch_fix_to_zip",
    "get_random_preview",
    "auto_rotate_strong",
    "pil_to_cv2",
    "cv2_to_pil",
    "denoise",
    "sharpen",
    "fix_contrast",
    "deskew",
    "remove_borders",
]