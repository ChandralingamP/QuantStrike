from __future__ import annotations

import importlib.util
import json
from datetime import date, datetime
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from django.conf import settings

DATA_MODULE_PATH = settings.BASE_DIR.parent / "My API" / "Data.py"
INSTRUMENTS_JSON_PATH = settings.BASE_DIR.parent / "My API" / "instruments.json"
INSTRUMENT_EXPIRIES_PATH = settings.BASE_DIR.parent / "My API" / "instruments_expiries.json"


def load_data_module():
    if not DATA_MODULE_PATH.exists():
        raise FileNotFoundError(f"Angel data helper not found at {DATA_MODULE_PATH}")
    spec = importlib.util.spec_from_file_location("quantstrike_instrument_data", DATA_MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def refresh_external_instrument_files() -> Dict[str, List[str]]:
    module = load_data_module()
    # download_scrip_master also writes the expiry summary.
    module.download_scrip_master()
    # collect_expiries returns the summary dictionary.
    return module.collect_expiries()


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
    INSTRUMENTS_JSON_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not INSTRUMENTS_JSON_PATH.exists():
        INSTRUMENTS_JSON_PATH.write_text("[]", encoding="utf-8")
    if not INSTRUMENT_EXPIRIES_PATH.exists():
        INSTRUMENT_EXPIRIES_PATH.write_text("{}", encoding="utf-8")
