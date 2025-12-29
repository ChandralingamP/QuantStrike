from __future__ import annotations

from contextlib import contextmanager
from datetime import timedelta

from django.utils.dateparse import parse_date
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.test.utils import override_settings

from ...services.strategy_one import OpeningRangeBreakoutEngine

try:  # optional dependency for precise exchange calendars
    from exchange_calendars import get_calendar  # type: ignore
except Exception:  # pragma: no cover - library may not be installed
    get_calendar = None  # type: ignore


@contextmanager
def maybe_override_sandbox(enable: bool):
    if not enable:
        yield
        return
    with override_settings(ANGEL_SANDBOX_ENABLED=True):
        yield


class Command(BaseCommand):
    help = "Run Strategy One for a specific user and optional date range."

    def add_arguments(self, parser):
        parser.add_argument("username", help="Username to run the strategy for.")
        parser.add_argument(
            "--mode",
            dest="mode",
            default="demo",
            help="Execution mode (demo|live). Defaults to demo.",
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
            help="Run the strategy against a single historical date (YYYY-MM-DD).",
        )
        parser.add_argument(
            "--start-date",
            dest="start_date",
            default="",
            help="Backtest start date (YYYY-MM-DD).",
        )
        parser.add_argument(
            "--end-date",
            dest="end_date",
            default="",
            help="Backtest end date (YYYY-MM-DD).",
        )

    def handle(self, *args, **options):
        username = options["username"].strip()
        mode = (options.get("mode") or "demo").strip().lower()
        sandbox = bool(options.get("sandbox"))
        market_date_raw = options.get("market_date") or ""
        start_date_raw = options.get("start_date") or ""
        end_date_raw = options.get("end_date") or ""

        if not username:
            raise CommandError("Username is required.")

        if mode not in set(OpeningRangeBreakoutEngine.STRATEGY_MODES):
            raise CommandError("Invalid execution mode. Use 'demo' or 'live'.")

        market_date = parse_date(market_date_raw) if market_date_raw else None
        start_date = parse_date(start_date_raw) if start_date_raw else None
        end_date = parse_date(end_date_raw) if end_date_raw else None

        if market_date and (start_date or end_date):
            raise CommandError("Specify either --market-date or --start-date/--end-date, not both.")

        if (start_date and not end_date) or (end_date and not start_date):
            raise CommandError("Both --start-date and --end-date are required for a range.")

        if start_date and end_date and start_date > end_date:
            raise CommandError("start-date cannot be after end-date.")

        user = self._get_user(username)

        with maybe_override_sandbox(sandbox):
            if market_date:
                self._run_for_date(user, mode, market_date)
            else:
                current = start_date or None
                if not current:
                    # default to today if nothing is provided
                    from django.utils import timezone

                    current = timezone.localdate()
                    end_date = current
                while current <= end_date:
                    self._run_for_date(user, mode, current)
                    from datetime import timedelta

                    current += timedelta(days=1)

    def _find_trading_day(self, requested_date):
        """Find the nearest trading day on or before the requested date.
        
        If the requested date is a holiday/weekend, this will go back to find
        the previous trading day (24th, 23rd, 22nd, etc.).
        """
        calendar = None
        if get_calendar is not None:
            try:
                calendar = get_calendar("XBOM")  # Bombay Stock Exchange calendar
            except Exception:
                pass
        
        candidate = requested_date
        max_attempts = 30  # Look back up to 30 days to handle extended holidays
        
        for _ in range(max_attempts):
            if self._is_trading_day(candidate, calendar):
                if candidate != requested_date:
                    self.stdout.write(
                        self.style.WARNING(
                            f"Note: {requested_date} is not a trading day. Using {candidate} instead."
                        )
                    )
                return candidate
            candidate -= timedelta(days=1)
        
        # If we couldn't find a trading day in 30 days, raise an error
        raise CommandError(
            f"Could not find a trading day within 30 days before {requested_date}"
        )
    
    def _is_trading_day(self, value, calendar):
        """Check if a date is a trading day using the exchange calendar."""
        if calendar is not None:
            try:
                return bool(calendar.is_session(value))
            except Exception:
                pass
        # Fallback: simple weekday check (Monday-Friday)
        return value.weekday() < 5

    def _run_for_date(self, user, mode, market_date):
        # Automatically adjust to the nearest trading day if holiday
        trading_date = self._find_trading_day(market_date)
        
        summary = OpeningRangeBreakoutEngine(
            user=user,
            execution_mode=mode,
            market_date=trading_date,
        ).run()
        self.stdout.write(self.style.SUCCESS(f"Strategy One run completed for {trading_date}."))
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
