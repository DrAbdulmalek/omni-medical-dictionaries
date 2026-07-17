"""
Lightweight multi-engine OCR engine for the Omni Medical Suite.

Provides a unified interface over Tesseract, EasyOCR, and PaddleOCR with
graceful degradation and lazy loading.  Engines are tried in order and the
first successful result is returned.
"""

from __future__ import annotations

import importlib
import logging
import os
import re
from typing import Any, Dict, List, Optional

import cv2

logger = logging.getLogger(__name__)


class OCREngine:
    """Multi-engine OCR with automatic fallback.

    Parameters
    ----------
    default_lang : str
        Language string passed to the underlying engines.  Defaults to
        ``"eng+ara"`` which enables English and Arabic.
    confidence_threshold : float
        Minimum average confidence (0-1) for a result to be considered
        acceptable.  If an engine returns below this threshold the next
        engine is tried.
    """

    def __init__(
        self,
        default_lang: str = "eng+ara",
        confidence_threshold: float = 0.5,
    ) -> None:
        self.default_lang = default_lang
        self.confidence_threshold = confidence_threshold

        # Lazy-loaded engine singletons
        self._easyocr_reader: Optional[Any] = None
        self._paddleocr_engine: Optional[Any] = None

        # Cache of availability flags (populated once)
        self._availability_cache: Dict[str, bool] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def recognize(
        self,
        image_path: str,
        lang: Optional[str] = None,
        engine: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Run OCR on a single image.

        Parameters
        ----------
        image_path : str
            Path to the image file.
        lang : str or None
            Override language for this call.  Falls back to
            ``self.default_lang``.
        engine : str or None
            Force a specific engine (``"tesseract"``, ``"easyocr"``,
            ``"paddleocr"``).  When *None* the engines are tried in the
            standard fallback order.

        Returns
        -------
        dict
            ``{"text": str, "engine": str, "confidence": float, "words": list}``
        """
        if not os.path.isfile(image_path):
            logger.error("Image file not found: %s", image_path)
            return self._empty_result(engine or "none")

        lang = lang or self.default_lang
        engines_to_try = self._resolve_engine_order(engine)

        for eng_name in engines_to_try:
            try:
                logger.info("Trying OCR engine: %s on %s", eng_name, image_path)
                result = self._dispatch(eng_name, image_path, lang)
                if result and result["confidence"] >= self.confidence_threshold:
                    logger.info(
                        "Engine %s succeeded with confidence %.2f",
                        eng_name,
                        result["confidence"],
                    )
                    return result
                elif result:
                    logger.warning(
                        "Engine %s returned low confidence %.2f (threshold %.2f)",
                        eng_name,
                        result["confidence"],
                        self.confidence_threshold,
                    )
                else:
                    logger.warning("Engine %s returned no result", eng_name)
            except Exception:
                logger.exception("Engine %s failed on %s", eng_name, image_path)

        logger.error("All OCR engines failed for %s", image_path)
        return self._empty_result(engine or "none")

    def recognize_batch(
        self,
        image_paths: List[str],
        lang: Optional[str] = None,
        engine: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Run OCR on a list of images.

        Parameters
        ----------
        image_paths : list[str]
            Paths to image files.
        lang, engine
            Same semantics as :meth:`recognize`.

        Returns
        -------
        list[dict]
            One result dict per input image, in the same order.
        """
        results: List[Dict[str, Any]] = []
        for idx, path in enumerate(image_paths):
            logger.info("Processing batch item %d/%d: %s", idx + 1, len(image_paths), path)
            results.append(self.recognize(path, lang=lang, engine=engine))
        return results

    def list_available_engines(self) -> List[str]:
        """Return a list of engine names that are currently importable."""
        available: List[str] = []
        engine_modules = {
            "tesseract": "pytesseract",
            "easyocr": "easyocr",
            "paddleocr": "paddleocr",
        }
        for eng_name, module_name in engine_modules.items():
            if self._is_available(module_name):
                available.append(eng_name)
                logger.debug("Engine %s is available (module %s)", eng_name, module_name)
            else:
                logger.debug("Engine %s is NOT available (module %s)", eng_name, module_name)
        return available

    # ------------------------------------------------------------------
    # Engine implementations
    # ------------------------------------------------------------------

    def _run_tesseract(self, image_path: str, lang: str) -> Dict[str, Any]:
        """Run Tesseract OCR (pytesseract with --psm 6 --oem 3)."""
        import pytesseract

        img = cv2.imread(image_path)
        if img is None:
            raise ValueError(f"cv2 could not read image: {image_path}")

        config = "--psm 6 --oem 3"
        data = pytesseract.image_to_data(img, lang=lang, config=config, output_type=pytesseract.Output.DICT)

        words: List[Dict[str, Any]] = []
        total_conf = 0.0
        word_count = 0

        for i in range(len(data["text"])):
            text = data["text"][i].strip()
            if not text:
                continue
            conf = float(data["conf"][i])
            if conf < 0:
                conf = 0.0
            words.append({
                "text": text,
                "confidence": conf / 100.0,
                "bbox": {
                    "x": data["left"][i],
                    "y": data["top"][i],
                    "w": data["width"][i],
                    "h": data["height"][i],
                },
            })
            total_conf += conf
            word_count += 1

        full_text = pytesseract.image_to_string(img, lang=lang, config=config).strip()
        avg_conf = (total_conf / word_count / 100.0) if word_count > 0 else 0.0

        return {
            "text": full_text,
            "engine": "tesseract",
            "confidence": avg_conf,
            "words": words,
        }

    def _run_easyocr(self, image_path: str, lang: str) -> Dict[str, Any]:
        """Run EasyOCR with lazy-loaded reader."""
        if self._easyocr_reader is None:
            logger.info("Lazy-loading EasyOCR reader …")
            import easyocr  # type: ignore[import-untyped]

            # Map tesseract-style lang codes to easyocr
            easy_langs = self._tesseract_to_easyocr_langs(lang)
            self._easyocr_reader = easyocr.Reader(easy_langs, gpu=False)
            logger.info("EasyOCR reader loaded with languages: %s", easy_langs)

        results = self._easyocr_reader.readtext(image_path)

        words: List[Dict[str, Any]] = []
        total_conf = 0.0

        for bbox, text, conf in results:
            words.append({
                "text": text,
                "confidence": float(conf),
                "bbox": {
                    "x": int(bbox[0][0]),
                    "y": int(bbox[0][1]),
                    "w": int(bbox[1][0] - bbox[0][0]),
                    "h": int(bbox[2][1] - bbox[0][1]),
                },
            })
            total_conf += conf

        full_text = " ".join(w["text"] for w in words)
        avg_conf = total_conf / len(results) if results else 0.0

        return {
            "text": full_text,
            "engine": "easyocr",
            "confidence": avg_conf,
            "words": words,
        }

    def _run_paddleocr(self, image_path: str, lang: str) -> Dict[str, Any]:
        """Run PaddleOCR with lazy-loaded engine."""
        if self._paddleocr_engine is None:
            logger.info("Lazy-loading PaddleOCR engine …")
            from paddleocr import PaddleOCR  # type: ignore[import-untyped]

            paddle_lang = "ar" if "ara" in lang else "en"
            self._paddleocr_engine = PaddleOCR(
                use_angle_cls=True,
                lang=paddle_lang,
                show_log=False,
            )
            logger.info("PaddleOCR engine loaded with lang=%s", paddle_lang)

        result = self._paddleocr_engine.ocr(image_path, cls=True)

        words: List[Dict[str, Any]] = []
        total_conf = 0.0

        # PaddleOCR returns nested list: [[ [bbox, (text, conf)], ... ]]
        if result and result[0]:
            for line in result[0]:
                bbox, (text, conf) = line[0], line[1]
                words.append({
                    "text": text,
                    "confidence": float(conf),
                    "bbox": {
                        "x": int(bbox[0][0]),
                        "y": int(bbox[0][1]),
                        "w": int(bbox[2][0] - bbox[0][0]),
                        "h": int(bbox[2][1] - bbox[0][1]),
                    },
                })
                total_conf += conf

        full_text = " ".join(w["text"] for w in words)
        avg_conf = total_conf / len(words) if words else 0.0

        return {
            "text": full_text,
            "engine": "paddleocr",
            "confidence": avg_conf,
            "words": words,
        }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _is_available(self, module_name: str) -> bool:
        """Check whether a Python module can be imported.

        Results are cached after the first check so that repeated calls are
        cheap.
        """
        if module_name in self._availability_cache:
            return self._availability_cache[module_name]
        try:
            importlib.import_module(module_name)
            self._availability_cache[module_name] = True
        except ImportError:
            self._availability_cache[module_name] = False
        return self._availability_cache[module_name]

    def _dispatch(
        self, engine_name: str, image_path: str, lang: str
    ) -> Optional[Dict[str, Any]]:
        """Route to the correct engine implementation."""
        if engine_name == "tesseract":
            return self._run_tesseract(image_path, lang)
        elif engine_name == "easyocr":
            return self._run_easyocr(image_path, lang)
        elif engine_name == "paddleocr":
            return self._run_paddleocr(image_path, lang)
        else:
            raise ValueError(f"Unknown engine: {engine_name}")

    def _resolve_engine_order(self, engine: Optional[str]) -> List[str]:
        """Return the ordered list of engines to try.

        If *engine* is specified and available, only that engine is tried.
        Otherwise all available engines are returned in fallback order.
        """
        if engine is not None:
            if self._is_available(self._engine_to_module(engine)):
                return [engine]
            logger.warning(
                "Requested engine %s is not available, falling back to all engines",
                engine,
            )
            # Fall through to default order

        fallback_order = ["tesseract", "easyocr", "paddleocr"]
        return [e for e in fallback_order if self._is_available(self._engine_to_module(e))]

    @staticmethod
    def _engine_to_module(engine_name: str) -> str:
        mapping = {
            "tesseract": "pytesseract",
            "easyocr": "easyocr",
            "paddleocr": "paddleocr",
        }
        return mapping.get(engine_name, engine_name)

    @staticmethod
    def _tesseract_to_easyocr_langs(lang: str) -> List[str]:
        """Convert a tesseract language string to easyocr language codes.

        Examples
        --------
        "eng+ara" → ["en", "ar"]
        "eng"     → ["en"]
        """
        mapping = {
            "eng": "en",
            "ara": "ar",
            "fra": "fr",
            "deu": "de",
            "spa": "es",
        }
        codes: List[str] = []
        for part in lang.split("+"):
            code = mapping.get(part.strip())
            if code and code not in codes:
                codes.append(code)
        return codes or ["en"]

    @staticmethod
    def _empty_result(engine: str) -> Dict[str, Any]:
        return {
            "text": "",
            "engine": engine,
            "confidence": 0.0,
            "words": [],
        }