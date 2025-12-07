from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date
from typing import Iterable

from django.utils import timezone

from ..constants import INSTRUMENT_PRESETS
from ..models import Instrument
from ..utils.instrument_data import (
    ensure_parent_directories,
    load_expiry_map,
    next_valid_expiry,
    parse_expiry_code,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ExpirySelection:
    code: str
    value: date


def _determine_next_expiry(options: Iterable[str]) -> ExpirySelection | None:
    next_code = next_valid_expiry(options, timezone.now().date())
    if not next_code:
        return None
    next_date = parse_expiry_code(next_code)
    if not next_date:
        return None
    return ExpirySelection(code=next_code, value=next_date)


def initialize_user_instruments(user) -> None:
    """Ensure a user has instrument rows with default presets and expiries."""
    try:
        ensure_parent_directories()
        expiry_map = load_expiry_map()
    except Exception as exc:  # pragma: no cover - defensive guard
        logger.warning("Unable to load expiry metadata for instruments: %s", exc)
        expiry_map = {}

    for instrument_code, defaults in INSTRUMENT_PRESETS.items():
        options = expiry_map.get(instrument_code, [])
        selection = _determine_next_expiry(options) if options else None

        payload = {
            "transaction": defaults["transaction"],
            "no_of_lots": defaults["no_of_lots"],
            "pl_exit_lots": defaults["pl_exit_lots"],
            "premium_price": defaults["premium_price"],
            "pl_points": defaults["pl_points"],
            "sl_points": defaults["sl_points"],
            "trailing_points": defaults["trailing_points"],
            "active": defaults["active"],
            "strike_selection": defaults.get("strike_selection", Instrument.StrikeSelection.STATIC),
            "strike_step": defaults.get("strike_step", 50),
            "ce_strike_offset": defaults.get("ce_strike_offset", 0),
            "pe_strike_offset": defaults.get("pe_strike_offset", 0),
            "contract_expiry_code": selection.code if selection else "",
            "contract_expiry": selection.value if selection else None,
        }

        for field in (
            "trading_symbol",
            "symbol_token",
            "exchange",
            "lot_size",
        ):
            if field in defaults:
                payload[field] = defaults[field]

        Instrument.objects.update_or_create(
            user=user,
            instrument=instrument_code,
            defaults=payload,
        )