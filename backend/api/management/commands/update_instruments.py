from __future__ import annotations

from typing import Dict, List

from django.core.management.base import BaseCommand
from django.utils import timezone

from api.models import Instrument
from api.utils.instrument_data import (
    ensure_parent_directories,
    load_expiry_map,
    next_valid_expiry,
    parse_expiry_code,
    refresh_external_instrument_files,
)


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

            if (
                current_code == next_code
                and current_date is not None
                and current_date >= today
            ):
                continue

            instrument.contract_expiry_code = next_code
            instrument.contract_expiry = next_date
            instrument.save(update_fields=["contract_expiry", "contract_expiry_code", "updated_at"])
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
