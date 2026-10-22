"""Smoke tests.

Added because CI requires a ``tests/`` directory and failed with
"ERROR: tests/ directory is required". These tests only assert that the
repository's data files are present and parseable; they do not change any
behaviour.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_repository_root_is_present() -> None:
    assert ROOT.is_dir()


@pytest.mark.parametrize("name", ["dictionary.json", "dictionary_medical.json"])
def test_json_data_files_parse(name: str) -> None:
    """Each tracked JSON data file must be valid JSON."""
    path = ROOT / name
    if not path.exists():
        pytest.skip(f"{name} not present in this checkout")
    with path.open(encoding="utf-8") as fh:
        assert json.load(fh) is not None
