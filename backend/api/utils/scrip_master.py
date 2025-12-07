"""Download the Angel One scrip master and persist it as prettified JSON."""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List

import requests

SCRIP_MASTER_URL = (
    "https://margincalculator.angelbroking.com/OpenAPI_File/files/"
    "OpenAPIScripMaster.json"
)
EXCLUDED_KEYWORDS = ("SENSEX", "NIFTY", "BANKNIFTY")


def download_scrip_master(
    output_path: Path,
    expiry_summary_path: Path,
) -> None:
    """Download Angel One scrip master and save filtered instruments."""
    response = requests.get(SCRIP_MASTER_URL, timeout=60)
    response.raise_for_status()
    data = response.json()
    excluded_terms = tuple(keyword.upper() for keyword in EXCLUDED_KEYWORDS)
    filtered = [
        item
        for item in data
        if (item.get("name", "") or "").upper() in excluded_terms
    ]

    def parse_expiry(raw: str) -> datetime | None:
        cleaned = (raw or "").strip().upper()
        for fmt in ("%d%b%Y", "%d%b%y"):
            try:
                return datetime.strptime(cleaned, fmt)
            except ValueError:
                continue
        return None

    now = datetime.now()
    cutoff = now + timedelta(days=92)
    filtered_with_expiry = []
    for item in filtered:
        expiry_value = parse_expiry(item.get("expiry", ""))
        if not expiry_value:
            continue
        if now <= expiry_value <= cutoff:
            filtered_with_expiry.append((item, expiry_value))

    filtered_with_expiry.sort(key=lambda pair: pair[1])
    filtered = [item for item, _ in filtered_with_expiry]

    if output_path.exists():
        output_path.unlink()

    with output_path.open("w", encoding="utf-8") as handle:
        json.dump(filtered, handle, ensure_ascii=False, indent=2)

    collect_expiries(output_path, expiry_summary_path)


def collect_expiries(
    instruments_path: Path,
    expiry_summary_path: Path,
) -> Dict[str, List[str]]:
    """Extract and organize contract expiries from instruments data."""
    if not instruments_path.exists():
        raise FileNotFoundError(
            f"Scrip master JSON not found at {instruments_path}"
        )

    with instruments_path.open("r", encoding="utf-8") as handle:
        records = json.load(handle)

    expiries_map: dict[str, set[str]] = defaultdict(set)
    keyword_set = {keyword.upper() for keyword in EXCLUDED_KEYWORDS}

    def normalise(text: str) -> str:
        return (text or "").strip().upper()

    for item in records:
        name = normalise(item.get("name", ""))
        if name not in keyword_set:
            continue

        expiry_value = normalise(item.get("expiry", ""))
        if not expiry_value:
            continue

        expiries_map[name].add(expiry_value)

    def sort_expiries(values: set[str]) -> list[str]:
        def parse(raw: str) -> datetime:
            for fmt in ("%d%b%Y", "%d%b%y"):
                try:
                    return datetime.strptime(raw, fmt)
                except ValueError:
                    continue
            return datetime.max

        return [
            expiry
            for expiry, _ in sorted(
                ((value, parse(value)) for value in values),
                key=lambda pair: pair[1],
            )
        ]

    summary = {
        name: sort_expiries(expiry_values)
        for name, expiry_values in expiries_map.items()
    }

    with expiry_summary_path.open("w", encoding="utf-8") as handle:
        json.dump(summary, handle, ensure_ascii=False, indent=2)

    return summary
