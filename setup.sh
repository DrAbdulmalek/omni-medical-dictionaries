#!/usr/bin/env bash
# ============================================================
# setup.sh — OmniFile Processor / Scanner Fixer v2.1
# تشغيل على Manjaro / Arch Linux
# ============================================================
set -e

# --- ألوان ---
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

info()  { echo -e "${BLUE}[INFO]${NC} $*"; }
ok()    { echo -e "${GREEN}[OK]${NC} $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $*"; }
err()   { echo -e "${RED}[ERROR]${NC} $*"; }

# --- المجلد الرئيسي ---
PROJECT_DIR="$HOME/omni-medical-suite"

echo ""
echo "============================================"
echo "  OmniFile Processor — Scanner Fixer v2.1"
echo "  Setup Script for Manjaro"
echo "============================================"
echo ""

# --- الخطوة 1: حزم النظام ---
info "الخطوة 1/5: تثبيت حزم النظام (poppler, tesseract, opencv)..."
echo ""

if command -v pacman &>/dev/null; then
    # التحقق مما إذا كانت الحزم مثبتة مسبقاً
    MISSING_PKGS=()
    for pkg in python python-pip python-opencv tesseract poppler tesseract-data-ara tesseract-data-eng; do
        if ! pacman -Qi "$pkg" &>/dev/null; then
            MISSING_PKGS+=("$pkg")
        fi
    done

    if [ ${#MISSING_PKGS[@]} -gt 0 ]; then
        info "الحزم المطلوبة: ${MISSING_PKGS[*]}"
        sudo pacman -S --noconfirm "${MISSING_PKGS[@]}"
        ok "تم تثبيت حزم النظام"
    else
        ok "حزم النظام مثبتة مسبقاً — تم التخطي"
    fi
elif command -v apt &>/dev/null; then
    warn "تم اكتشاف Ubuntu/Debian (ليس Manjaro) — سأستخدم apt"
    sudo apt update
    sudo apt install -y python3 python3-pip python3-opencv tesseract-ocr tesseract-ocr-ara tesseract-ocr-eng poppler-utils libgl1 libglib2.0-0
    ok "تم تثبيت حزم النظام"
else
    err "نظام غير مدعوم. ثبّت يدوياً: python, opencv, tesseract, poppler"
    exit 1
fi

echo ""

# --- الخطوة 2: إنشاء هيكل المجلدات ---
info "الخطوة 2/5: إنشاء هيكل المشروع..."

mkdir -p "$PROJECT_DIR"/{packages/preprocessors,app,training,logs,downloads}
ok "تم إنشاء المجلدات"

echo ""

# --- الخطوة 3: إنشاء ملفات Python ---
info "الخطوة 3/5: إنشاء ملفات المشروع..."

# ===== packages/__init__.py =====
cat > "$PROJECT_DIR/packages/__init__.py" << 'PYEOF'
# packages/__init__.py
PYEOF
ok "  packages/__init__.py"

# ===== packages/preprocessors/__init__.py =====
cat > "$PROJECT_DIR/packages/preprocessors/__init__.py" << 'PYEOF'
from .scanner_fixer import (
    fix_scanner_image,
    fix_image_file,
    batch_fix_folder,
    batch_fix_to_zip,
    get_random_preview,
    auto_rotate_strong,
    pil_to_cv2,
    cv2_to_pil,
    __version__,
)
PYEOF
ok "  packages/preprocessors/__init__.py"

# ===== packages/preprocessors/scanner_fixer.py =====
cat > "$PROJECT_DIR/packages/preprocessors/scanner_fixer.py" << 'PYEOF'
#!/usr/bin/env python3
"""
scanner_fixer.py v2.1 — OmniFile_Processor / omni-medical-suite
===============================================================
Smart scanner image correction engine.
"""

import os, sys, gc, logging, tempfile, atexit, shutil, zipfile, random
from pathlib import Path
from typing import List, Tuple, Optional, Dict, Any

import cv2
import numpy as np
from PIL import Image

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

_temp_dirs: List[str] = []

def _register_tmp(path: str) -> None:
    _temp_dirs.append(path)

def _cleanup_all_tmp() -> None:
    for d in _temp_dirs:
        try:
            if os.path.isdir(d):
                shutil.rmtree(d, ignore_errors=True)
        except Exception:
            pass
    _temp_dirs.clear()

atexit.register(_cleanup_all_tmp)

def _make_tmp(base: str = "sf_") -> str:
    d = tempfile.mkdtemp(prefix=base)
    _register_tmp(d)
    return d

def _ensure_grayscale(img: np.ndarray) -> np.ndarray:
    if len(img.shape) == 2:
        return img
    return cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

def _auto_rotate_osd(img: np.ndarray) -> Tuple[int, float]:
    try:
        import pytesseract
        osd_data = pytesseract.image_to_osd(img, config="--psm 0")
        angle = 0
        for line in osd_data.splitlines():
            if "Rotate in" in line:
                angle = int(line.split(":")[-1].strip())
        return angle, 5.0
    except Exception as exc:
        logger.debug("OSD failed: %s", exc)
        return 0, 0.0

def _auto_rotate_hough(img: np.ndarray) -> Tuple[int, float]:
    try:
        gray = _ensure_grayscale(img)
        edges = cv2.Canny(gray, 50, 150, apertureSize=3)
        lines = cv2.HoughLines(edges, 1, np.pi / 180, threshold=100)
        if lines is None:
            return 0, 0.0
        angles = []
        for rho, theta in lines[:, 0]:
            angle = np.degrees(theta) - 90
            if abs(angle) < 45:
                angles.append(angle)
        if not angles:
            return 0, 0.0
        median_angle = float(np.median(angles))
        confidence = min(len(angles) / 50.0, 1.0) * 10.0
        return int(round(median_angle)), confidence
    except Exception as exc:
        logger.debug("Hough failed: %s", exc)
        return 0, 0.0

def _auto_rotate_projection(img: np.ndarray) -> Tuple[int, float]:
    try:
        gray = _ensure_grayscale(img)
        thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)[1]
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
    h, w = img.shape[:2]
    if min(h, w) < 100:
        return img
    results = [_auto_rotate_osd(img), _auto_rotate_hough(img), _auto_rotate_projection(img)]
    weights = [3, 2, 1]
    total_weight = 0.0
    weighted_angle = 0.0
    for (angle, conf), wt in zip(results, weights):
        if conf > 0:
            weighted_angle += angle * conf * wt
            total_weight += conf * wt
    if total_weight == 0:
        return img
    final_angle = int(round(weighted_angle / total_weight))
    if abs(final_angle) < 1:
        return img
    logger.info("Rotation: %d deg", final_angle)
    center = (w // 2, h // 2)
    M = cv2.getRotationMatrix2D(center, final_angle, 1.0)
    return cv2.warpAffine(img, M, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)

def deskew(img: np.ndarray) -> np.ndarray:
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
        return cv2.warpAffine(img, M, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)
    except Exception:
        return img

def denoise(img: np.ndarray, strength: int = 10) -> np.ndarray:
    try:
        if len(img.shape) == 2:
            return cv2.fastNlMeansDenoising(img, None, h=strength)
        return cv2.fastNlMeansDenoisingColored(img, None, h=strength, hColor=strength)
    except Exception:
        return img

def sharpen(img: np.ndarray) -> np.ndarray:
    try:
        kernel = np.array([[-1, -1, -1], [-1, 9, -1], [-1, -1, -1]])
        return cv2.filter2D(img, -1, kernel)
    except Exception:
        return img

def fix_contrast(img: np.ndarray, clip_limit: float = 2.0) -> np.ndarray:
    try:
        if len(img.shape) == 2:
            clahe = cv2.createCLAHE(clipLimit=clip_limit, tileGridSize=(8, 8))
            return clahe.apply(img)
        lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
        clahe = cv2.createCLAHE(clipLimit=clip_limit, tileGridSize=(8, 8))
        lab[:, :, 0] = clahe.apply(lab[:, :, 0])
        return cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)
    except Exception:
        return img

def remove_borders(img: np.ndarray, margin_px: int = 5) -> np.ndarray:
    try:
        gray = _ensure_grayscale(img)
        _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
        h, w = thresh.shape
        if h < 40 or w < 40:
            return img
        unique_vals = np.unique(thresh)
        if len(unique_vals) <= 1:
            return img
        x_coords = np.any(thresh[margin_px:h - margin_px, :], axis=0)
        y_coords = np.any(thresh[:, margin_px:w - margin_px], axis=1)
        if not x_coords.any() or not y_coords.any():
            return img
        x_start, x_end = np.where(x_coords)[0][[0, -1]]
        y_start, y_end = np.where(y_coords)[0][[0, -1]]
        pad = 10
        x_start = max(0, x_start - pad)
        x_end = min(w, x_end + pad)
        y_start = max(0, y_start - pad)
        y_end = min(h, y_end + pad)
        if (x_end - x_start) < 20 or (y_end - y_start) < 20:
            return img
        return img[y_start:y_end, x_start:x_end]
    except Exception:
        return img

def fix_scanner_image(image: np.ndarray, do_rotate=True, do_deskew=True,
                      do_denoise=True, do_sharpen=True, do_contrast=True,
                      do_border=True, denoise_strength=10) -> np.ndarray:
    if image is None:
        raise ValueError("Image is None")
    logger.info("Pipeline start: %s", image.shape)
    result = image.copy()
    try:
        if do_rotate:   result = auto_rotate_strong(result)
        if do_deskew:   result = deskew(result)
        if do_denoise:  result = denoise(result, strength=denoise_strength)
        if do_contrast: result = fix_contrast(result)
        if do_sharpen:  result = sharpen(result)
        if do_border:   result = remove_borders(result)
        logger.info("Pipeline done: %s", result.shape)
        return result
    except Exception as exc:
        logger.error("Pipeline error: %s", exc)
        return image

def fix_image_file(input_path: str, output_path: Optional[str] = None, **kwargs) -> str:
    input_path = str(input_path)
    if not os.path.isfile(input_path):
        raise FileNotFoundError(f"Not found: {input_path}")
    if output_path is None:
        p = Path(input_path)
        output_path = str(p.parent / f"{p.stem}_fixed{p.suffix}")
    img = cv2.imread(input_path)
    if img is None:
        raise ValueError(f"Cannot read: {input_path}")
    fixed = fix_scanner_image(img, **kwargs)
    cv2.imwrite(output_path, fixed)
    logger.info("Saved: %s", output_path)
    return output_path

def _load_pdf_pages(pdf_path: str, dpi: int = 200) -> List[np.ndarray]:
    try:
        from pdf2image import convert_from_path
    except ImportError:
        raise ImportError("pdf2image required. On Manjaro: sudo pacman -S poppler && pip install pdf2image")
    tmp_dir = _make_tmp("sf_pdf_")
    images = convert_from_path(pdf_path, dpi=dpi, output_folder=tmp_dir, fmt="png", paths_only=True)
    result = []
    for img_path in images:
        cv_img = cv2.imread(img_path)
        if cv_img is not None:
            result.append(cv_img)
    logger.info("PDF %s -> %d pages", Path(pdf_path).name, len(result))
    return result

def batch_fix_folder(folder_path: str, output_folder: Optional[str] = None,
                     extensions=(".png", ".jpg", ".jpeg", ".tiff", ".tif", ".bmp", ".webp"),
                     recursive: bool = True, **kwargs) -> List[str]:
    folder = Path(folder_path)
    if not folder.is_dir():
        raise NotADirectoryError(f"Not a directory: {folder_path}")
    if output_folder is None:
        output_folder = str(folder / "fixed")
    os.makedirs(output_folder, exist_ok=True)
    output_paths = []
    pattern = "**/*" if recursive else "*"
    for fpath in sorted(folder.glob(pattern)):
        if fpath.is_file():
            suffix = fpath.suffix.lower()
            if suffix in extensions:
                try:
                    out = fix_image_file(str(fpath), output_folder=output_folder, **kwargs)
                    output_paths.append(out)
                except Exception as exc:
                    logger.error("Failed %s: %s", fpath.name, exc)
            elif suffix == ".pdf":
                try:
                    pdf_images = _load_pdf_pages(str(fpath))
                    pdf_out = os.path.join(output_folder, fpath.stem)
                    os.makedirs(pdf_out, exist_ok=True)
                    for i, cv_img in enumerate(pdf_images):
                        fixed = fix_scanner_image(cv_img, **kwargs)
                        out_name = f"{fpath.stem}_page_{i+1:04d}.png"
                        out_path = os.path.join(pdf_out, out_name)
                        cv2.imwrite(out_path, fixed)
                        output_paths.append(out_path)
                except Exception as exc:
                    logger.error("PDF failed %s: %s", fpath.name, exc)
    logger.info("Batch: %d files", len(output_paths))
    return output_paths

def batch_fix_to_zip(folder_path: str, zip_path: Optional[str] = None, **kwargs) -> str:
    tmp_dir = _make_tmp("sf_zip_")
    fixed_paths = batch_fix_folder(folder_path, output_folder=tmp_dir, **kwargs)
    if not fixed_paths:
        raise ValueError("No images processed")
    if zip_path is None:
        zip_path = str(Path(folder_path) / "scanner_fixed_results.zip")
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for fp in fixed_paths:
            zf.write(fp, os.path.relpath(fp, tmp_dir))
    size_mb = os.path.getsize(zip_path) / (1024 * 1024)
    logger.info("ZIP: %s (%.2f MB)", zip_path, size_mb)
    return zip_path

def get_random_preview(folder_path: str, output_folder: Optional[str] = None,
                       n: int = 4, **kwargs) -> List[Tuple[np.ndarray, np.ndarray]]:
    folder = Path(folder_path)
    exts = {".png", ".jpg", ".jpeg", ".tiff", ".tif", ".bmp", ".webp"}
    files = [f for f in folder.rglob("*") if f.is_file() and f.suffix.lower() in exts]
    if not files:
        return []
    sample = random.sample(files, min(n, len(files)))
    results = []
    for fpath in sample:
        img = cv2.imread(str(fpath))
        if img is not None:
            fixed = fix_scanner_image(img, **kwargs)
            results.append((img, fixed))
    return results

def pil_to_cv2(pil_img) -> np.ndarray:
    cv_img = np.array(pil_img)
    if len(cv_img.shape) == 2:
        return cv_img
    return cv2.cvtColor(cv_img, cv2.COLOR_RGB2BGR)

def cv2_to_pil(cv_img: np.ndarray):
    if len(cv_img.shape) == 2:
        return Image.fromarray(cv_img)
    return Image.fromarray(cv2.cvtColor(cv_img, cv2.COLOR_BGR2RGB))

__version__ = "2.1"
__all__ = [
    "fix_scanner_image", "fix_image_file", "batch_fix_folder",
    "batch_fix_to_zip", "get_random_preview", "auto_rotate_strong",
    "pil_to_cv2", "cv2_to_pil", "denoise", "sharpen",
    "fix_contrast", "deskew", "remove_borders",
]
PYEOF
ok "  packages/preprocessors/scanner_fixer.py"

# ===== app/advanced_review_app.py =====
cat > "$PROJECT_DIR/app/advanced_review_app.py" << 'PYEOF'
#!/usr/bin/env python3
"""
advanced_review_app.py — OmniFile Processor — Scanner Fixer v2.1
Gradio: Single Image (Before/After) + Batch (Folder/PDF/ZIP)
"""

import os, sys, time, logging, zipfile
from pathlib import Path
from typing import Optional, Tuple, List

import gradio as gr
import numpy as np
from PIL import Image

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from packages.preprocessors.scanner_fixer import (
    fix_scanner_image, pil_to_cv2, cv2_to_pil,
    batch_fix_folder, _load_pdf_pages, _make_tmp, __version__,
)

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

STATE_ORIG = "original_cv2"
STATE_FIXED = "fixed_cv2"
STATE_OUT = "output_path"

# ========== SINGLE IMAGE ==========

def single_upload(image, state):
    if image is None:
        return None, None, state or {}, "Upload an image first."
    state = state or {}
    state[STATE_ORIG] = pil_to_cv2(image)
    state[STATE_FIXED] = None
    state[STATE_OUT] = None
    return image, None, state, f"Loaded: {image.size[0]}x{image.size[1]} px"

def single_process(state, do_rotate, do_deskew, do_denoise, do_sharpen, do_contrast, do_border, denoise_str):
    if not state or STATE_ORIG not in state:
        return None, None, state or {}, "No image loaded."
    orig = state[STATE_ORIG]
    try:
        fixed = fix_scanner_image(orig, do_rotate=do_rotate, do_deskew=do_deskew,
            do_denoise=do_denoise, do_sharpen=do_sharpen, do_contrast=do_contrast,
            do_border=do_border, denoise_strength=int(denoise_str))
        state[STATE_FIXED] = fixed
        h, w = fixed.shape[:2]
        return cv2_to_pil(orig), cv2_to_pil(fixed), state, f"Processed: {w}x{h} px"
    except Exception as exc:
        logger.error("single_process: %s", exc)
        return cv2_to_pil(orig), None, state, f"Error: {exc}"

def single_save(image, state, filename):
    if not state or STATE_FIXED not in state or state[STATE_FIXED] is None:
        return state or {}, "Nothing to save. Process first."
    dl = PROJECT_ROOT / "downloads"
    dl.mkdir(parents=True, exist_ok=True)
    if not filename:
        filename = f"scanner_fixed_{int(time.time())}.png"
    if not filename.lower().endswith((".png",".jpg",".jpeg",".tiff",".tif",".bmp")):
        filename += ".png"
    out = dl / filename
    import cv2
    ok = cv2.imwrite(str(out), state[STATE_FIXED])
    if ok:
        state[STATE_OUT] = str(out)
        kb = out.stat().st_size / 1024
        return state, f"Saved: {out.name} ({kb:.1f} KB)"
    return state, f"Failed to save."

def single_reset(state):
    return None, None, None, {}, "Reset."

# ========== BATCH ==========

def batch_folder(folder, do_rotate, do_deskew, do_denoise, do_sharpen, do_contrast, do_border, denoise_str, recursive, state):
    if not folder or not os.path.isdir(folder):
        return "Invalid path.", [], state or {}
    state = state or {}
    try:
        kw = dict(do_rotate=do_rotate, do_deskew=do_deskew, do_denoise=do_denoise,
                  do_sharpen=do_sharpen, do_contrast=do_contrast, do_border=do_border,
                  denoise_strength=int(denoise_str))
        paths = batch_fix_folder(folder, recursive=recursive, **kw)
        state["batch_paths"] = paths
        state["batch_src"] = folder
        return (f"Fixed {len(paths)} images." if paths else "No images found."), paths, state
    except Exception as exc:
        return f"Error: {exc}", [], state

def batch_pdf(pdf_file, do_rotate, do_deskew, do_denoise, do_sharpen, do_contrast, do_border, denoise_str, state):
    if pdf_file is None:
        return "Upload PDF first.", [], state or {}
    state = state or {}
    try:
        tmp = _make_tmp("sf_up_")
        pdf_path = os.path.join(tmp, pdf_file.name)
        with open(pdf_path, "wb") as f:
            f.write(pdf_file.read())
        kw = dict(do_rotate=do_rotate, do_deskew=do_deskew, do_denoise=do_denoise,
                  do_sharpen=do_sharpen, do_contrast=do_contrast, do_border=do_border,
                  denoise_strength=int(denoise_str))
        pages = _load_pdf_pages(pdf_path)
        if not pages:
            return "No pages.", [], state
        import cv2
        out_dir = PROJECT_ROOT / "downloads" / Path(pdf_file.name).stem
        out_dir.mkdir(parents=True, exist_ok=True)
        paths = []
        for i, pg in enumerate(pages):
            fixed = fix_scanner_image(pg, **kw)
            p = str(out_dir / f"page_{i+1:04d}.png")
            cv2.imwrite(p, fixed)
            paths.append(p)
        state["batch_paths"] = paths
        return f"PDF: {len(paths)} pages -> downloads/{Path(pdf_file.name).stem}/", paths, state
    except Exception as exc:
        return f"Error: {exc}", [], state

def batch_preview(folder, n, do_rotate, do_deskew, do_denoise, do_sharpen, do_contrast, do_border, denoise_str):
    if not folder or not os.path.isdir(folder):
        return [], "Invalid path."
    try:
        from packages.preprocessors.scanner_fixer import get_random_preview
        kw = dict(do_rotate=do_rotate, do_deskew=do_deskew, do_denoise=do_denoise,
                  do_sharpen=do_sharpen, do_contrast=do_contrast, do_border=do_border,
                  denoise_strength=int(denoise_str))
        pairs = get_random_preview(folder, n=int(n), **kw)
        if not pairs:
            return [], "No images."
        items = []
        for o, f in pairs:
            items.append(cv2_to_pil(o))
            items.append(cv2_to_pil(f))
        return items, f"Preview: {len(pairs)} pairs (odd=Before, even=After)"
    except Exception as exc:
        return [], f"Error: {exc}"

def batch_zip(state):
    if not state or "batch_paths" not in state or not state["batch_paths"]:
        return None, "No results. Process first."
    try:
        dl = PROJECT_ROOT / "downloads"
        dl.mkdir(parents=True, exist_ok=True)
        zname = f"scanner_fixed_{int(time.time())}.zip"
        zpath = dl / zname
        with zipfile.ZipFile(str(zpath), "w", zipfile.ZIP_DEFLATED) as zf:
            for fp in state["batch_paths"]:
                if os.path.isfile(fp):
                    zf.write(fp, os.path.basename(fp))
        mb = zpath.stat().st_size / (1024*1024)
        return str(zpath), f"ZIP: {zname} ({mb:.2f} MB, {len(state['batch_paths'])} files)"
    except Exception as exc:
        return None, f"Error: {exc}"

# ========== BUILD APP ==========

def build_app():
    with gr.Blocks(title="Scanner Fixer v2.1") as app:
        gr.Markdown("# OmniFile Processor - Scanner Fixer v2.1\nSmart correction: rotate, deskew, denoise, sharpen, contrast, borders.\n**Manual save only.**")

        with gr.Tab("Single Image"):
            st = gr.State(value={})
            with gr.Row():
                inp = gr.Image(label="Upload", type="pil", height=350, sources=["upload","clipboard"])
                with gr.Column():
                    fn = gr.Textbox(label="Filename", value="scanner_fixed.png")
            with gr.Row():
                bef = gr.Image(label="Before", type="pil", height=300, interactive=False)
                aft = gr.Image(label="After", type="pil", height=300, interactive=False)
            with gr.Accordion("Settings", open=True):
                with gr.Row():
                    cr=gr.Checkbox(label="Rotate",value=True); ck=gr.Checkbox(label="Deskew",value=True)
                    dn=gr.Checkbox(label="Denoise",value=True); sh=gr.Checkbox(label="Sharpen",value=True)
                    ct=gr.Checkbox(label="Contrast",value=True); bd=gr.Checkbox(label="Borders",value=True)
                ds = gr.Slider(label="Denoise Strength", min=1, max=30, value=10, step=1)
            with gr.Row():
                gr.Button("Process", variant="primary", size="lg").click(single_process,
                    [st,cr,ck,dn,sh,ct,bd,ds],[bef,aft,st,sts:=gr.Textbox(label="Status",interactive=False)])
                gr.Button("Save", variant="secondary", size="lg").click(single_save,[aft,st,fn],[st,sts])
                gr.Button("Reset", variant="stop").click(single_reset,[st],[bef,aft,inp,st,sts])
            inp.change(single_upload, [inp, st], [bef, aft, st, sts])

        with gr.Tab("Batch"):
            bst = gr.State(value={})
            with gr.Tabs():
                with gr.Tab("Folder"):
                    fi = gr.Textbox(label="Folder Path", placeholder="/path/to/images")
                    with gr.Row():
                        rec = gr.Checkbox(label="Recursive", value=True)
                        gr.Button("Process Folder", variant="primary").click(batch_folder,
                            [fi,cr,ck,dn,sh,ct,bd,ds,rec,bst],[bstat:=gr.Textbox(label="Status",interactive=False),bgal:=gr.Gallery(label="Results",columns=4,height=250),bst])
                with gr.Tab("PDF"):
                    pi = gr.File(label="PDF", file_types=[".pdf"])
                    gr.Button("Process PDF", variant="primary").click(batch_pdf,
                        [pi,cr,ck,dn,sh,ct,bd,ds,bst],[bstat,bgal,bst])
            with gr.Accordion("Random Preview", open=False):
                with gr.Row():
                    pf = gr.Textbox(label="Preview Folder", scale=3)
                    pn = gr.Slider(label="Count", min=2, max=10, value=4, step=2, scale=1)
                    gr.Button("Preview").click(batch_preview,[pf,pn,cr,ck,dn,sh,ct,bd,ds],
                        [pgal:=gr.Gallery(label="Pairs (odd=Before,even=After)",columns=4,height=300),pstat:=gr.Textbox(label="Preview Status",interactive=False)])
            with gr.Row():
                gr.Button("Save All as ZIP", variant="primary", size="lg").click(batch_zip,[bst],[zf:=gr.File(label="ZIP"),bstat])
        gr.Markdown("---\nScanner Fixer v2.1 | Tesseract OSD + Hough + Projection | Manjaro-ready")
    return app

def main():
    logger.info("Starting Scanner Fixer v%s", __version__)
    app = build_app()
    app.launch(server_name="0.0.0.0", server_port=7860, share=False, show_error=True)

if __name__ == "__main__":
    main()
PYEOF
ok "  app/advanced_review_app.py"

# ===== requirements-scanner.txt =====
cat > "$PROJECT_DIR/requirements-scanner.txt" << 'PYEOF'
gradio>=4.0.0
numpy>=1.24.0
Pillow>=10.0.0
opencv-python-headless>=4.8.0
pytesseract>=0.3.10
pdf2image>=1.16.0
PYEOF
ok "  requirements-scanner.txt"

echo ""

# --- الخطوة 4: تثبيت حزم Python ---
info "الخطوة 4/5: إنشاء بيئة افتراضية وتثبيت الحزم..."

if [ ! -d "$PROJECT_DIR/venv" ]; then
    python -m venv "$PROJECT_DIR/venv"
    ok "تم إنشاء البيئة الافتراضية"
else
    ok "البيئة الافتراضية موجودة مسبقاً"
fi

source "$PROJECT_DIR/venv/bin/activate"
pip install --upgrade pip -q
pip install -r "$PROJECT_DIR/requirements-scanner.txt" -q
ok "تم تثبيت حزم Python"

echo ""

# --- الخطوة 5: اختبار ---
info "الخطوة 5/5: اختبار سريع..."

python -c "
import sys; sys.path.insert(0, '$PROJECT_DIR')
from packages.preprocessors.scanner_fixer import fix_scanner_image, __version__
print(f'scanner_fixer v{__version__} - OK')
" 2>/dev/null

if [ $? -eq 0 ]; then
    ok "الاختبار نجح"
else
    warn "اختبار الاستيراد فشل — قد تحتاج لتثبيت حزم إضافية يدوياً"
fi

echo ""
echo "============================================"
echo -e "  ${GREEN}تم الإعداد بنجاح!${NC}"
echo "============================================"
echo ""
echo "  للتشغيل:"
echo ""
echo -e "    ${YELLOW}cd $PROJECT_DIR${NC}"
echo -e "    ${YELLOW}source venv/bin/activate${NC}"
echo -e "    ${YELLOW}python app/advanced_review_app.py${NC}"
echo ""
echo "  ثم افتح: http://localhost:7860"
echo ""
echo "  لإيقاف: Ctrl+C"
echo "============================================"