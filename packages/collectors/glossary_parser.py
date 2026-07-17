"""
Glossary parser for the Omni Medical Suite.

Extracts term-definition pairs from OCR output using seven complementary
regex-based patterns, with automatic language detection and confidence
scoring.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Arabic Unicode range (includes Arabic letters, Arabic Presentation Forms,
# and the additional Arabic range).
_ARABIC_CHAR_RE = re.compile(
    r"[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\uFB50-\uFDFF\uFE70-\uFEFF]"
)


class GlossaryParser:
    """Extract term-definition pairs from raw text.

    Parameters
    ----------
    min_confidence : float
        Minimum confidence (0–1) for an entry to be included in the final
        output.
    """

    def __init__(self, min_confidence: float = 0.5) -> None:
        self.min_confidence = min_confidence

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def parse(
        self,
        text: str,
        page_num: int = 0,
        source: str = "",
    ) -> List[Dict[str, Any]]:
        """Parse *text* and return a deduplicated list of glossary entries.

        Returns
        -------
        list[dict]
            Each dict has keys: ``term``, ``definition``, ``language``,
            ``confidence``, ``pattern_name``, ``page_num``, ``source``.
        """
        if not text or not text.strip():
            return []

        language = self.detect_language(text)
        logger.info(
            "Parsing glossary on page %d (lang=%s, source=%s, len=%d)",
            page_num,
            language,
            source,
            len(text),
        )

        # Collect candidates from every pattern.
        all_candidates: List[Dict[str, Any]] = []

        pattern_methods = [
            ("en_ar_comma", self._pattern_en_ar_comma),
            ("ar_en_comma", self._pattern_ar_en_comma),
            ("bold_dict", self._pattern_bold_dict),
            ("colon", self._pattern_colon),
            ("numbered", self._pattern_numbered),
            ("table", self._pattern_table),
            ("parentheses", self._pattern_parentheses),
        ]

        for pattern_name, method in pattern_methods:
            try:
                raw_entries = method(text)
                for entry in raw_entries:
                    all_candidates.append({
                        "term": entry["term"].strip(),
                        "definition": entry["definition"].strip(),
                        "confidence": entry["confidence"],
                        "pattern_name": pattern_name,
                    })
            except Exception:
                logger.exception("Pattern %s raised an exception", pattern_name)

        # Deduplicate: keep the entry with the highest confidence per term.
        best: Dict[str, Dict[str, Any]] = {}
        for cand in all_candidates:
            key = cand["term"].lower()
            if key not in best or cand["confidence"] > best[key]["confidence"]:
                best[key] = cand

        # Build final output, filtering by min_confidence.
        results: List[Dict[str, Any]] = []
        for key in best:
            entry = best[key]
            if entry["confidence"] < self.min_confidence:
                continue
            results.append({
                "term": entry["term"],
                "definition": entry["definition"],
                "language": language,
                "confidence": entry["confidence"],
                "pattern_name": entry["pattern_name"],
                "page_num": page_num,
                "source": source,
            })

        logger.info(
            "Glossary parse complete: %d raw candidates → %d final entries",
            len(all_candidates),
            len(results),
        )
        return results

    # ------------------------------------------------------------------
    # Language detection
    # ------------------------------------------------------------------

    @staticmethod
    def detect_language(text: str) -> str:
        """Detect dominant language of *text*.

        Returns ``"ar"`` when the ratio of Arabic characters to total
        non-whitespace characters exceeds 0.3; otherwise ``"en"``.
        """
        if not text:
            return "en"
        arabic_chars = len(_ARABIC_CHAR_RE.findall(text))
        non_ws_chars = len(re.sub(r"\s", "", text))
        if non_ws_chars == 0:
            return "en"
        ratio = arabic_chars / non_ws_chars
        lang = "ar" if ratio > 0.3 else "en"
        logger.debug("Language detection: ratio=%.2f → %s", ratio, lang)
        return lang

    # ------------------------------------------------------------------
    # Extraction patterns
    # ------------------------------------------------------------------

    def _pattern_en_ar_comma(self, text: str) -> List[Dict[str, str]]:
        """English term followed by Arabic definition, comma-separated.

        Matches lines like::

            Blood pressure, الضغط الدموي
            Heart rate, معدل ضربات القلب
        """
        entries: List[Dict[str, str]] = []
        # A line that starts with Latin characters followed by a comma and
        # then Arabic characters.
        pattern = re.compile(
            r"^([A-Za-z][A-Za-z\s\-/().]{1,120}?)\s*[,،]\s*"
            r"([\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\uFB50-\uFDFF\uFE70-\uFEFF"
            r"\s\d\-/().،,]+?)$",
            re.MULTILINE,
        )
        for m in pattern.finditer(text):
            term = m.group(1).strip()
            definition = m.group(2).strip()
            if term and definition and len(term) > 1:
                entries.append({
                    "term": term,
                    "definition": definition,
                    "confidence": 0.9,
                })
                logger.debug("en_ar_comma matched: %s → %s", term, definition)
        return entries

    def _pattern_ar_en_comma(self, text: str) -> List[Dict[str, str]]:
        """Arabic term followed by English definition, comma-separated.

        Matches lines like::

            الضغط الدموي, Blood pressure
        """
        entries: List[Dict[str, str]] = []
        pattern = re.compile(
            r"^([\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\uFB50-\uFDFF\uFE70-\uFEFF"
            r"\s\d\-/().،,]+?)\s*[,،]\s*"
            r"([A-Za-z][A-Za-z\s\-/().]{1,120}?)$",
            re.MULTILINE,
        )
        for m in pattern.finditer(text):
            term = m.group(1).strip()
            definition = m.group(2).strip()
            if term and definition and len(term) > 1:
                entries.append({
                    "term": term,
                    "definition": definition,
                    "confidence": 0.9,
                })
                logger.debug("ar_en_comma matched: %s → %s", term, definition)
        return entries

    def _pattern_bold_dict(self, text: str) -> List[Dict[str, str]]:
        """Bold-marked term followed by definition.

        Matches lines like::

            **Blood pressure** – the force of blood against artery walls
            __Hypertension__: abnormally high blood pressure
            **الضغط** - قوة الدم
        """
        entries: List[Dict[str, str]] = []
        # Markdown bold (** or __) + optional separator + definition
        pattern = re.compile(
            r"(?:^|\n)"
            r"[\s]*"
            r"(\*{2}|_{2})(.+?)\1"  # **term** or __term__
            r"\s*[-–—:：]\s*"  # separator
            r"(.+?)"
            r"(?:\n|$)",
        )
        for m in pattern.finditer(text):
            term = m.group(2).strip()
            definition = m.group(3).strip()
            if term and definition:
                entries.append({
                    "term": term,
                    "definition": definition,
                    "confidence": 0.85,
                })
                logger.debug("bold_dict matched: %s → %s", term, definition)
        return entries

    def _pattern_colon(self, text: str) -> List[Dict[str, str]]:
        """Term-colon-definition pattern.

        Matches lines like::

            Blood pressure: the force exerted by blood on vessel walls
            Systole: the phase of the heartbeat when the heart muscle contracts
        """
        entries: List[Dict[str, str]] = []
        pattern = re.compile(
            r"^([^\n:]{2,80}?)\s*[:：]\s*([^\n]+?)$",
            re.MULTILINE,
        )
        for m in pattern.finditer(text):
            term = m.group(1).strip()
            definition = m.group(2).strip()
            # Skip lines that look like timestamps, headings, or page markers.
            if not term or not definition:
                continue
            if re.match(r"^\d{1,2}:\d{2}", definition):
                continue
            if len(term) > 80:
                continue
            entries.append({
                "term": term,
                "definition": definition,
                "confidence": 0.8,
            })
            logger.debug("colon matched: %s → %s", term, definition)
        return entries

    def _pattern_numbered(self, text: str) -> List[Dict[str, str]]:
        """Numbered list entries.

        Matches lines like::

            1. Blood pressure – the force of blood against artery walls
            2) Heart rate: number of heartbeats per minute
            3- Systole : contraction phase of the cardiac cycle
        """
        entries: List[Dict[str, str]] = []
        pattern = re.compile(
            r"^\s*\d{1,3}\s*[.)\-]\s*"
            r"([^\n\-–—:：]{2,80}?)"  # term (up to separator)
            r"\s*[-–—:：]\s*"
            r"([^\n]+?)$",
            re.MULTILINE,
        )
        for m in pattern.finditer(text):
            term = m.group(1).strip()
            definition = m.group(2).strip()
            if term and definition and len(term) > 1:
                entries.append({
                    "term": term,
                    "definition": definition,
                    "confidence": 0.75,
                })
                logger.debug("numbered matched: %s → %s", term, definition)
        return entries

    def _pattern_table(self, text: str) -> List[Dict[str, str]]:
        """Simple table format (tab or pipe-delimited).

        Matches lines like::

            Blood pressure\tالضغط الدموي\tthe force of blood
            Heart rate	معدل ضربات القلب	beats per minute
            Systole | الانقباض | contraction phase
        """
        entries: List[Dict[str, str]] = []

        # Tab-delimited or pipe-delimited rows with at least 2 columns.
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue

            # Determine delimiter.
            if "\t" in line:
                parts = [p.strip() for p in line.split("\t")]
            elif "|" in line:
                parts = [p.strip() for p in line.split("|") if p.strip()]
            else:
                continue

            if len(parts) < 2:
                continue

            # Heuristic: treat the first short-ish field as term and the rest
            # as definition.
            term = parts[0]
            definition = " | ".join(parts[1:])

            if term and definition and len(term) > 1 and len(term) <= 120:
                entries.append({
                    "term": term,
                    "definition": definition,
                    "confidence": 0.7,
                })
                logger.debug("table matched: %s → %s", term, definition)

        return entries

    def _pattern_parentheses(self, text: str) -> List[Dict[str, str]]:
        """Parenthetical definition pattern.

        Matches lines like::

            Blood pressure (the force of blood against artery walls)
            Hypertension (abnormally elevated blood pressure)
        """
        entries: List[Dict[str, str]] = []
        pattern = re.compile(
            r"([^\s(][^\n(]{1,80}?)"  # term – must not start with whitespace
            r"\s*\(\s*"
            r"([^\)]{3,500}?)"  # definition inside parentheses
            r"\s*\)",
        )
        for m in pattern.finditer(text):
            term = m.group(1).strip()
            definition = m.group(2).strip()
            # Filter out noise: parenthetical references, years, etc.
            if not term or not definition:
                continue
            if re.match(r"^(?:et al\.?|see|cf\.?|e\.g\.?|i\.e\.?)$", definition, re.I):
                continue
            if re.match(r"^\d{4}$", definition):
                continue
            entries.append({
                "term": term,
                "definition": definition,
                "confidence": 0.6,
            })
            logger.debug("parentheses matched: %s → %s", term, definition)
        return entries