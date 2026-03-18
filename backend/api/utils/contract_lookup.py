"""Contract metadata lookup using locally cached Angel scrip master data."""
from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import Decimal
from functools import lru_cache
from typing import Optional

from django.conf import settings

from .instrument_data import parse_expiry_code


@dataclass(frozen=True)
class ContractMetadata:
    """Legacy contract metadata structure - kept for backward compatibility."""
    symbol: str
    token: str
    exchange: Optional[str] = None
    lot_size: Optional[int] = None


class ContractLookupError(RuntimeError):
    """Raised when instrument metadata cannot be loaded."""


@lru_cache(maxsize=1)
def _load_contract_rows() -> list[dict]:
    path = settings.BASE_DIR / "data" / "instruments.json"
    if not path.exists():
        raise ContractLookupError(f"Instrument metadata file not found: {path}")
    try:
        with path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except Exception as exc:  # pragma: no cover - defensive guard
        raise ContractLookupError(f"Unable to load contract metadata: {exc}") from exc
    if not isinstance(payload, list):
        raise ContractLookupError("Instrument metadata is malformed.")
    return payload


def _normalise_strike(raw: object) -> Optional[int]:
    try:
        value = Decimal(str(raw or "0"))
    except Exception:
        return None
    if value <= 0:
        return None
    if value > Decimal("100000"):
        value = value / Decimal("100")
    return int(value)


def _option_type_from_symbol(symbol: str) -> str:
    upper = (symbol or "").upper()
    if upper.endswith("PE"):
        return "PE"
    if upper.endswith("CE"):
        return "CE"
    return ""


def _expiry_matches(raw_expiry: str, expiry_code: str) -> bool:
    left = parse_expiry_code(raw_expiry or "")
    right = parse_expiry_code(expiry_code or "")
    if left and right:
        return left == right
    return (raw_expiry or "").strip().upper() == (expiry_code or "").strip().upper()


def lookup_contract(symbol: str) -> Optional[ContractMetadata]:
    """Return exact symbol metadata from the local scrip master cache."""
    target = (symbol or "").strip().upper()
    if not target:
        return None
    for row in _load_contract_rows():
        row_symbol = str(row.get("symbol") or "").strip().upper()
        if row_symbol != target:
            continue
        return ContractMetadata(
            symbol=str(row.get("symbol") or ""),
            token=str(row.get("token") or ""),
            exchange=str(row.get("exch_seg") or "") or None,
            lot_size=int(str(row.get("lotsize") or "0") or 0) or None,
        )
    return None


def find_contract(
    *,
    underlying: str,
    expiry_code: str,
    strike: int,
    option_type: str,
) -> Optional[ContractMetadata]:
    """Find a contract by underlying, expiry, strike and option type."""
    target_name = (underlying or "").strip().upper()
    target_option_type = (option_type or "").strip().upper()
    for row in _load_contract_rows():
        if str(row.get("name") or "").strip().upper() != target_name:
            continue
        if not _expiry_matches(str(row.get("expiry") or ""), expiry_code):
            continue
        if _option_type_from_symbol(str(row.get("symbol") or "")) != target_option_type:
            continue
        row_strike = _normalise_strike(row.get("strike"))
        if row_strike != int(strike):
            continue
        return ContractMetadata(
            symbol=str(row.get("symbol") or ""),
            token=str(row.get("token") or ""),
            exchange=str(row.get("exch_seg") or "") or None,
            lot_size=int(str(row.get("lotsize") or "0") or 0) or None,
        )
    return None
