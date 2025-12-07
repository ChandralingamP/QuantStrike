from __future__ import annotations

from contextlib import contextmanager
from django.utils.dateparse import parse_date

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.test.utils import override_settings

from ...services.strategy_alpha import StrategyAlphaEngine


@contextmanager
def maybe_override_sandbox(enable: bool):
    if not enable:
        yield
        return
    with override_settings(ANGEL_SANDBOX_ENABLED=True):
        yield


class Command(BaseCommand):
    help = "Run Strategy Alpha for a specific user and report the summary."

    def add_arguments(self, parser):
        parser.add_argument("username", help="Username to run the strategy for.")
        parser.add_argument(
            "--mode",
            dest="mode",
            default="",
            help="Override execution mode (demo|live). Defaults to the user's activation mode.",
        )
        parser.add_argument(
            "--sandbox",
            dest="sandbox",
            action="store_true",
            help="Force sandbox mode for SmartAPI interactions.",
        )
        parser.add_argument(
            "--market-date",
            dest="market_date",
            default="",
            help="Run the strategy against a historical date (YYYY-MM-DD).",
        )

    def handle(self, *args, **options):
        username = options["username"].strip()
        mode_override = (options.get("mode") or "").strip().lower()
        sandbox = bool(options.get("sandbox"))
        market_date_raw = options.get("market_date") or ""
        market_date = None
        if market_date_raw:
            market_date = parse_date(market_date_raw)
            if not market_date:
                raise CommandError("Invalid market date. Use YYYY-MM-DD format.")

        if not username:
            raise CommandError("Username is required.")

        user = self._get_user(username)
        execution_mode = mode_override if mode_override in {"demo", "live"} else None

        with maybe_override_sandbox(sandbox):
            summary = StrategyAlphaEngine(
                user=user,
                execution_mode=execution_mode,
                market_date=market_date,
            ).run()

        self.stdout.write(self.style.SUCCESS("Strategy Alpha run completed."))
        for key, value in summary.items():
            if key == "instrument_summaries":
                self.stdout.write("instrument_summaries:")
                for instrument_summary in value:
                    self.stdout.write(f"  - {instrument_summary}")
            else:
                self.stdout.write(f"{key}: {value}")

    def _get_user(self, username):
        User = get_user_model()
        try:
            return User.objects.get(username__iexact=username)
        except User.DoesNotExist as exc:
            raise CommandError(f"User '{username}' not found.") from exc
