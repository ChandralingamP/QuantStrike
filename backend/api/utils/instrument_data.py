from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from django.conf import settings

from .scrip_master import download_scrip_master

INSTRUMENTS_JSON_PATH = settings.BASE_DIR / "data" / "instruments.json"
INSTRUMENT_EXPIRIES_PATH = settings.BASE_DIR / "data" / "instruments_expiries.json"


def refresh_external_instrument_files() -> Dict[str, List[str]]:
    """Download latest instrument data and refresh expiry mappings."""
    ensure_parent_directories()
    download_scrip_master(INSTRUMENTS_JSON_PATH, INSTRUMENT_EXPIRIES_PATH)
    return load_expiry_map()


def load_expiry_map() -> Dict[str, List[str]]:
    if not INSTRUMENT_EXPIRIES_PATH.exists():
        return {}
    with INSTRUMENT_EXPIRIES_PATH.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    # ensure deterministic ordering
    return {
        key.upper(): [value for value in values]
        for key, values in payload.items()
    }


def parse_expiry_code(expiry_code: str) -> Optional[date]:
    cleaned = (expiry_code or "").strip().upper()
    if not cleaned:
        return None
    for fmt in ("%d%b%Y", "%d%b%y"):
        try:
            return datetime.strptime(cleaned, fmt).date()
        except ValueError:
            continue
    return None


def next_valid_expiry(expiry_codes: Iterable[str], reference: date) -> Optional[str]:
    parsed = []
    for code in expiry_codes:
        expiry_date = parse_expiry_code(code)
        if not expiry_date:
            continue
        parsed.append((expiry_date, code))
    if not parsed:
        return None
    parsed.sort(key=lambda pair: pair[0])
    for expiry_date, code in parsed:
        if expiry_date >= reference:
            return code
    # fallback to latest available even if in past
    return parsed[-1][1]


def ensure_parent_directories() -> None:
    """Ensure data directory and placeholder JSON files exist."""
    INSTRUMENTS_JSON_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not INSTRUMENTS_JSON_PATH.exists():
        INSTRUMENTS_JSON_PATH.write_text("[]", encoding="utf-8")
    if not INSTRUMENT_EXPIRIES_PATH.exists():
        INSTRUMENT_EXPIRIES_PATH.write_text("{}", encoding="utf-8")
