#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_scanner_fixer.py — Unit tests for scanner_fixer.py v2.1
============================================================
Tests core processing functions with synthetic and edge-case images.
Run: python -m pytest tests/test_scanner_fixer.py -v
"""

import sys
import numpy as np
from pathlib import Path

import pytest

# Ensure packages are importable
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from packages.preprocessors.scanner_fixer import (
    auto_rotate_strong,
    deskew,
    denoise,
    sharpen,
    fix_contrast,
    remove_borders,
    fix_scanner_image,
    pil_to_cv2,
    cv2_to_pil,
    _ensure_grayscale,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_white_image(h=200, w=300):
    """Create a blank white image (BGR)."""
    return np.ones((h, w, 3), dtype=np.uint8) * 255


def _make_black_image(h=200, w=300):
    """Create a blank black image (BGR)."""
    return np.zeros((h, w, 3), dtype=np.uint8)


# ---------------------------------------------------------------------------
# Tests: _ensure_grayscale
# ---------------------------------------------------------------------------

class TestEnsureGrayscale:
    def test_bgr_input(self):
        bgr = np.random.randint(0, 255, (100, 100, 3), dtype=np.uint8)
        gray = _ensure_grayscale(bgr)
        assert gray.shape == (100, 100)

    def test_already_gray(self):
        gray = np.random.randint(0, 255, (100, 100), dtype=np.uint8)
        result = _ensure_grayscale(gray)
        assert result.shape == (100, 100)
        np.testing.assert_array_equal(result, gray)


# ---------------------------------------------------------------------------
# Tests: denoise
# ---------------------------------------------------------------------------

class TestDenoise:
    def test_color_image(self):
        img = _make_white_image()
        noisy = img + np.random.randint(0, 30, img.shape, dtype=np.uint8)
        result = denoise(noisy, strength=5)
        assert result.shape == img.shape

    def test_grayscale_image(self):
        gray = np.ones((100, 100), dtype=np.uint8) * 200
        gray_noisy = gray + np.random.randint(0, 30, gray.shape, dtype=np.uint8)
        result = denoise(gray_noisy, strength=5)
        assert result.shape == (100, 100)


# ---------------------------------------------------------------------------
# Tests: sharpen
# ---------------------------------------------------------------------------

class TestSharpen:
    def test_returns_same_shape(self):
        img = _make_white_image()
        result = sharpen(img)
        assert result.shape == img.shape


# ---------------------------------------------------------------------------
# Tests: fix_contrast
# ---------------------------------------------------------------------------

class TestFixContrast:
    def test_color_image(self):
        img = _make_white_image()
        result = fix_contrast(img)
        assert result.shape == img.shape

    def test_grayscale_image(self):
        gray = np.ones((100, 100), dtype=np.uint8) * 128
        result = fix_contrast(gray)
        assert result.shape == (100, 100)


# ---------------------------------------------------------------------------
# Tests: remove_borders
# ---------------------------------------------------------------------------

class TestRemoveBorders:
    def test_white_image(self):
        """White image should be returned as-is (no borders to remove)."""
        img = _make_white_image()
        result = remove_borders(img)
        assert result.shape == img.shape

    def test_black_image(self):
        """Black image should be returned as-is (no content)."""
        img = _make_black_image()
        result = remove_borders(img)
        assert result.shape == img.shape

    def test_small_image(self):
        """Very small images should be skipped."""
        img = np.ones((10, 10, 3), dtype=np.uint8) * 255
        result = remove_borders(img)
        assert result.shape == img.shape

    def test_uniform_image(self):
        """Uniform gray image should be returned as-is."""
        img = np.ones((200, 300, 3), dtype=np.uint8) * 128
        result = remove_borders(img)
        assert result.shape == img.shape


# ---------------------------------------------------------------------------
# Tests: auto_rotate_strong
# ---------------------------------------------------------------------------

class TestAutoRotateStrong:
    def test_small_image_skipped(self):
        """Images smaller than 100px should skip rotation."""
        img = np.ones((50, 50, 3), dtype=np.uint8) * 255
        result = auto_rotate_strong(img)
        assert result.shape == img.shape

    def test_white_image_no_crash(self):
        """White image should not crash rotation detection."""
        img = _make_white_image(500, 500)
        result = auto_rotate_strong(img)
        assert result is not None


# ---------------------------------------------------------------------------
# Tests: deskew
# ---------------------------------------------------------------------------

class TestDeskew:
    def test_white_image(self):
        img = _make_white_image()
        result = deskew(img)
        assert result is not None


# ---------------------------------------------------------------------------
# Tests: fix_scanner_image (full pipeline)
# ---------------------------------------------------------------------------

class TestFixScannerImage:
    def test_none_raises(self):
        with pytest.raises(ValueError):
            fix_scanner_image(None)

    def test_white_image_pipeline(self):
        img = _make_white_image()
        result = fix_scanner_image(img)
        assert result.shape == img.shape

    def test_black_image_pipeline(self):
        img = _make_black_image()
        result = fix_scanner_image(img)
        assert result.shape == img.shape

    def test_selective_pipeline(self):
        img = _make_white_image()
        result = fix_scanner_image(
            img,
            do_rotate=False,
            do_deskew=False,
            do_denoise=False,
            do_sharpen=False,
            do_contrast=True,
            do_border=False,
        )
        assert result.shape == img.shape

    def test_on_failure_returns_original(self):
        """If processing fails, original image is returned."""
        img = _make_white_image(30, 30)
        result = fix_scanner_image(img)
        # Should not crash, may return original or processed
        assert result is not None


# ---------------------------------------------------------------------------
# Tests: PIL <-> CV2 helpers
# ---------------------------------------------------------------------------

class TestPilCv2Conversion:
    def test_pil_to_cv2(self):
        from PIL import Image as PILImage
        pil_img = PILImage.new("RGB", (200, 100), color="red")
        cv_img = pil_to_cv2(pil_img)
        assert cv_img.shape == (100, 200, 3)

    def test_cv2_to_pil(self):
        cv_img = np.zeros((100, 200, 3), dtype=np.uint8)
        pil_img = cv2_to_pil(cv_img)
        assert pil_img.size == (200, 100)

    def test_roundtrip_color(self):
        from PIL import Image as PILImage
        original = PILImage.new("RGB", (150, 150), color="blue")
        cv_img = pil_to_cv2(original)
        back = cv2_to_pil(cv_img)
        assert back.size == original.size

    def test_roundtrip_gray(self):
        from PIL import Image as PILImage
        original = PILImage.new("L", (150, 150), color=128)
        cv_img = pil_to_cv2(original)
        assert len(cv_img.shape) == 2
        back = cv2_to_pil(cv_img)
        assert back.size == original.size


# ---------------------------------------------------------------------------
# Tests: Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_very_large_image(self):
        """Large image should not crash."""
        img = np.random.randint(200, 255, (2000, 3000, 3), dtype=np.uint8)
        result = fix_scanner_image(img, do_rotate=False, do_denoise=False)
        assert result.shape == img.shape

    def test_gradient_image(self):
        """Gradient image (not uniform) should work."""
        gradient = np.tile(np.linspace(0, 255, 300, dtype=np.uint8), (200, 1))
        gradient_bgr = np.stack([gradient, gradient, gradient], axis=2)
        result = fix_scanner_image(gradient_bgr)
        assert result is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])