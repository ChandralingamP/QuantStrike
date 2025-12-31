from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from ...models import Instrument


class Command(BaseCommand):
    help = "Load trading metadata for instruments from a JSON file."

    def add_arguments(self, parser):
        parser.add_argument(
            "--path",
            dest="path",
            default="",
            help="Path to JSON file mapping instrument codes to trading metadata.",
        )
        parser.add_argument(
            "--username",
            dest="username",
            default="",
            help="Optional username filter. When provided, only instruments for this user are updated.",
        )
        parser.add_argument(
            "--only-active",
            dest="only_active",
            action="store_true",
            help="Restrict updates to instruments marked as active.",
        )

    def handle(self, *args, **options):
        path_opt = options.get("path") or ""
        username = (options.get("username") or "").strip()
        only_active = bool(options.get("only_active"))

        path = self._resolve_path(path_opt)
        if not path.exists() or not path.is_file():
            raise CommandError(f"Metadata file not found: {path}")

        raw_meta = self._load_json(path)
        meta = self._normalize_metadata(raw_meta)

        updated = 0
        queryset = Instrument.objects.all()
        if username:
            queryset = queryset.filter(user__username__iexact=username)
        if only_active:
            queryset = queryset.filter(active=True)

        for instrument in queryset:
            payload = meta.get(instrument.instrument)
            if not isinstance(payload, dict):
                continue

            dirty = False
            update_fields = []
            
            # Update trading metadata fields
            for field in ("trading_symbol", "symbol_token", "exchange", "lot_size"):
                if field in payload and payload[field] is not None:
                    value = payload[field]
                    if getattr(instrument, field) != value:
                        setattr(instrument, field, value)
                        dirty = True
                        if field not in update_fields:
                            update_fields.append(field)
            
            # Update contract_expiry if present in metadata
            if "expiry" in payload and payload["expiry"]:
                expiry_str = str(payload["expiry"]).strip()
                if expiry_str:
                    # Parse expiry date (format: DDMMMYYYY, e.g., 27JAN2026)
                    try:
                        expiry_date = datetime.strptime(expiry_str, "%d%b%Y").date()
                        if instrument.contract_expiry != expiry_date:
                            instrument.contract_expiry = expiry_date
                            dirty = True
                            if "contract_expiry" not in update_fields:
                                update_fields.append("contract_expiry")
                    except (ValueError, AttributeError):
                        # Skip invalid expiry dates
                        pass

            if dirty:
                update_fields.append("updated_at")
                instrument.save(update_fields=update_fields)
                updated += 1
                self.stdout.write(self.style.SUCCESS(
                    f"Updated {instrument.instrument} for {instrument.user.username}"
                ))

        if updated == 0:
            self.stdout.write("No instruments required updates.")
        else:
            self.stdout.write(f"Total instruments updated: {updated}")

    def _resolve_path(self, path_option: str) -> Path:
        if path_option:
            return Path(path_option).expanduser().resolve()
        if getattr(settings, "ANGEL_INSTRUMENT_METADATA_PATH", ""):
            return Path(settings.ANGEL_INSTRUMENT_METADATA_PATH).expanduser().resolve()
        return Path(settings.BASE_DIR).parent.joinpath("docs", "smartapi-instrument-metadata.json").resolve()

    def _load_json(self, path: Path):
        content = path.read_text(encoding="utf-8")
        try:
            return json.loads(content)
        except json.JSONDecodeError as exc:  # pragma: no cover - invalid input guard
            raise CommandError(f"Unable to parse JSON metadata: {exc}") from exc

    def _normalize_metadata(self, data):
        if isinstance(data, dict):
            return {
                key: self._coerce_payload(value)
                for key, value in data.items()
                if isinstance(value, dict)
            }
        if isinstance(data, list):
            normalized = {}
            for entry in data:
                if not isinstance(entry, dict):
                    continue
                code = entry.get("instrument") or entry.get("name")
                if not code:
                    continue
                code = str(code).upper()
                payload = self._coerce_payload({
                    "trading_symbol": entry.get("symbol"),
                    "symbol_token": entry.get("token"),
                    "exchange": entry.get("exch_seg"),
                    "lot_size": entry.get("lotsize"),
                    "expiry": entry.get("expiry"),
                })
                # First occurrence wins; assumes file sorted by relevance
                normalized.setdefault(code, payload)
            return normalized
        raise CommandError("Unsupported metadata structure; expected object or array.")

    def _coerce_payload(self, payload):
        output = {}
        for field, value in payload.items():
            if value in (None, ""):
                continue
            if field == "lot_size":
                try:
                    coerced = int(float(value))
                except (TypeError, ValueError):
                    continue
                output[field] = coerced
            else:
                output[field] = value
        return output
