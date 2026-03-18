from __future__ import annotations

from typing import Dict, List

from django.core.management.base import BaseCommand
from django.utils import timezone

from api.models import Instrument
from api.utils.contract_lookup import find_contract
from api.utils.instrument_data import (
    ensure_parent_directories,
    load_expiry_map,
    next_valid_expiry,
    parse_expiry_code,
    refresh_external_instrument_files,
)


def _extract_symbol_details(symbol: str) -> tuple[int | None, str]:
    cleaned = (symbol or "").strip().upper()
    if not cleaned:
        return None, ""
    option_type = "PE" if cleaned.endswith("PE") else "CE" if cleaned.endswith("CE") else ""
    base = cleaned[:-2] if option_type else cleaned
    digits = "".join(ch for ch in base if ch.isdigit())
    strike = int(digits[-5:]) if len(digits) >= 5 else None
    return strike, option_type


def _sync_contract_metadata(instrument: Instrument) -> list[str]:
    if not instrument.contract_expiry_code:
        return []

    update_fields: list[str] = []

    def update_from_symbol(symbol_field: str, token_field: str) -> None:
        nonlocal update_fields
        current_symbol = getattr(instrument, symbol_field, "") or ""
        if not current_symbol:
            return
        strike, option_type = _extract_symbol_details(current_symbol)
        if strike is None or not option_type:
            return
        metadata = find_contract(
            underlying=instrument.instrument,
            expiry_code=instrument.contract_expiry_code,
            strike=strike,
            option_type=option_type,
        )
        if not metadata:
            return
        if getattr(instrument, symbol_field) != metadata.symbol:
            setattr(instrument, symbol_field, metadata.symbol)
            update_fields.append(symbol_field)
        if getattr(instrument, token_field) != metadata.token:
            setattr(instrument, token_field, metadata.token)
            update_fields.append(token_field)
        if metadata.exchange and instrument.exchange != metadata.exchange:
            instrument.exchange = metadata.exchange
            update_fields.append("exchange")
        if metadata.lot_size and instrument.lot_size != metadata.lot_size:
            instrument.lot_size = metadata.lot_size
            update_fields.append("lot_size")

    update_from_symbol("trading_symbol", "symbol_token")
    update_from_symbol("alternate_trading_symbol", "alternate_symbol_token")
    return update_fields


class Command(BaseCommand):
    help = (
        "Refresh the external instrument datasets and roll forward the stored "
        "contract expiries for NIFTY, BANKNIFTY, and SENSEX."
    )

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--skip-refresh",
            action="store_true",
            help="Skip calling the external download scripts and reuse existing JSON files.",
        )

    def handle(self, *args, **options):
        ensure_parent_directories()

        if options.get("skip_refresh"):
            expiry_map = load_expiry_map()
            self.stdout.write("Using cached instruments_expiries.json")
        else:
            expiry_map = refresh_external_instrument_files()
            self.stdout.write("Fetched latest instrument metadata from Angel One")

        if not expiry_map:
            self.stdout.write(self.style.WARNING("No expiry data available. Aborting roll-forward."))
            return

        today = timezone.now().date()
        updated = 0
        missing: Dict[str, List[str]] = {}

        for instrument in Instrument.objects.all():
            instrument_code = instrument.instrument.upper()
            options = expiry_map.get(instrument_code, [])
            if not options:
                missing[instrument_code] = []
                continue

            next_code = next_valid_expiry(options, today)
            next_date = parse_expiry_code(next_code)
            if not next_code or not next_date:
                missing[instrument_code] = options
                continue

            current_date = instrument.contract_expiry
            current_code = instrument.contract_expiry_code

            expiry_changed = not (
                current_code == next_code
                and current_date is not None
                and current_date >= today
            )

            update_fields = []
            if expiry_changed:
                instrument.contract_expiry_code = next_code
                instrument.contract_expiry = next_date
                update_fields.extend(["contract_expiry", "contract_expiry_code"])

                # Clear cached daily selections and levels when expiry rolls.
                instrument.daily_selection_date = None
                instrument.daily_ce_symbol = ""
                instrument.daily_ce_token = ""
                instrument.daily_pe_symbol = ""
                instrument.daily_pe_token = ""
                instrument.daily_underlying_price = None
                instrument.daily_ce_prev_high = None
                instrument.daily_ce_prev_low = None
                instrument.daily_pe_prev_high = None
                instrument.daily_pe_prev_low = None
                instrument.daily_levels_date = None
                update_fields.extend([
                    "daily_selection_date",
                    "daily_ce_symbol",
                    "daily_ce_token",
                    "daily_pe_symbol",
                    "daily_pe_token",
                    "daily_underlying_price",
                    "daily_ce_prev_high",
                    "daily_ce_prev_low",
                    "daily_pe_prev_high",
                    "daily_pe_prev_low",
                    "daily_levels_date",
                ])

            update_fields.extend(_sync_contract_metadata(instrument))

            if not update_fields:
                continue

            instrument.save(update_fields=[*dict.fromkeys(update_fields), "updated_at"])
            updated += 1

        if updated:
            self.stdout.write(self.style.SUCCESS(f"Updated {updated} instrument(s)."))
        else:
            self.stdout.write("No instrument updates were required.")

        if missing:
            for instrument_code, options in missing.items():
                self.stdout.write(
                    self.style.WARNING(
                        f"No usable expiry found for {instrument_code}. Available options: {options or 'none'}"
                    )
                )
