from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Optional

from django.conf import settings


@dataclass(frozen=True)
class ContractMetadata:
    symbol: str
    token: str
    exchange: Optional[str] = None
    lot_size: Optional[int] = None


class ContractLookupError(RuntimeError):
    """Raised when instrument metadata cannot be loaded."""


def lookup_contract(symbol: str) -> Optional[ContractMetadata]:
    """Return metadata for the given trading symbol if available."""

    symbol = symbol.upper()
    cache = _load_metadata_cache()
    payload = cache.get(symbol)
    if not payload:
        return None
    return ContractMetadata(
        symbol=symbol,
        token=str(payload.get("symbol_token", "")),
        exchange=payload.get("exchange"),
        lot_size=payload.get("lot_size"),
    )


@lru_cache(maxsize=1)
def _load_metadata_cache() -> dict[str, dict[str, object]]:
    path_value = getattr(settings, "ANGEL_INSTRUMENT_METADATA_PATH", "")
    if not path_value:
        return {}
    path = Path(path_value).expanduser().resolve()
    if not path.exists():
        raise ContractLookupError(f"Instrument metadata file not found: {path}")
    content = path.read_text(encoding="utf-8")
    data = json.loads(content)
    if isinstance(data, dict):
        return {key.upper(): _coerce_payload(value) for key, value in data.items() if isinstance(value, dict)}
    if isinstance(data, list):
        mapping: dict[str, dict[str, object]] = {}
        for entry in data:
            if not isinstance(entry, dict):
                continue
            symbol = str(entry.get("symbol") or entry.get("tradingsymbol") or "").upper()
            if not symbol:
                continue
            mapping[symbol] = _coerce_payload(
                {
                    "symbol_token": entry.get("token") or entry.get("symboltoken"),
                    "exchange": entry.get("exch_seg") or entry.get("exchange"),
                    "lot_size": entry.get("lotsize") or entry.get("lot_size"),
                }
            )
        return mapping
    raise ContractLookupError("Unsupported metadata structure; expected dict or list.")


def _coerce_payload(payload: dict[str, object | None]) -> dict[str, object]:
    normalized: dict[str, object] = {}
    for key, value in payload.items():
        if value in (None, ""):
            continue
        if key == "lot_size":
            try:
                normalized[key] = int(float(value))
            except (TypeError, ValueError):
                continue
        else:
            normalized[key] = value
    return normalized
