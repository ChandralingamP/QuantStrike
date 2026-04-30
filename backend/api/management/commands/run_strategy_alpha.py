from __future__ import annotations

import logging
import subprocess
import time as _time
from contextlib import contextmanager
from datetime import datetime, time, timedelta
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.test.utils import override_settings
from django.utils import timezone
from django.utils.dateparse import parse_date

from ...services.strategy_alpha import StrategyAlphaEngine


def setup_user_logger(username: str) -> logging.Logger:
    """Set up a dedicated logger for a user with file handler."""
    logs_dir = Path(settings.BASE_DIR) / "logs" / "users"
    logs_dir.mkdir(parents=True, exist_ok=True)
    
    log_file = logs_dir / f"{username}_strategy.log"
    
    # Create logger
    logger = logging.getLogger(f"strategy_alpha.{username}")
    logger.setLevel(logging.INFO)
    logger.propagate = False
    
    # Clear existing handlers
    logger.handlers.clear()
    
    # File handler
    file_handler = logging.FileHandler(log_file)
    file_handler.setLevel(logging.INFO)
    formatter = logging.Formatter(
        '%(asctime)s | %(levelname)s | %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    
    # Also log to console for immediate feedback
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    return logger


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
        parser.add_argument(
            "--scan-entries",
            dest="scan_entries",
            action="store_true",
            help="Re-run strategy every 5 minutes until trades open or market closes (for breakout strategies).",
        )
        parser.add_argument(
            "--scan-interval",
            dest="scan_interval",
            type=int,
            default=300,
            help="Seconds between entry scans (default: 300 = 5 minutes).",
        )

    def handle(self, *args, **options):
        username = options["username"].strip()
        mode_override = (options.get("mode") or "").strip().lower()
        sandbox = bool(options.get("sandbox"))
        scan_entries = bool(options.get("scan_entries"))
        scan_interval = options.get("scan_interval") or 300
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

        # Set up user-specific logger
        user_logger = setup_user_logger(username)
        user_logger.info("=" * 80)
        user_logger.info(f"STRATEGY ALPHA EXECUTION - {username}")
        user_logger.info("=" * 80)
        user_logger.info(f"Mode: {execution_mode or 'auto'}")
        user_logger.info(f"Market Date: {market_date or 'today'}")
        user_logger.info(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        user_logger.info("=" * 80)

        with maybe_override_sandbox(sandbox):
            summary = StrategyAlphaEngine(
                user=user,
                execution_mode=execution_mode,
                market_date=market_date,
                logger=user_logger,
            ).run()

        user_logger.info("=" * 80)
        user_logger.info("EXECUTION SUMMARY")
        user_logger.info("=" * 80)
        user_logger.info(f"Status: {summary.get('status')}")
        user_logger.info(f"Mode: {summary.get('mode')}")
        user_logger.info(f"Opened Trades: {summary.get('opened_trades', 0)}")
        user_logger.info(f"Closed Trades: {summary.get('closed_trades', 0)}")
        user_logger.info(f"Net P&L: {summary.get('net_pnl', 0)}")
        user_logger.info("=" * 80)

        self.stdout.write(self.style.SUCCESS("Strategy Alpha run completed."))
        for key, value in summary.items():
            if key == "instrument_summaries":
                self.stdout.write("instrument_summaries:")
                for instrument_summary in value:
                    self.stdout.write(f"  - {instrument_summary}")
            else:
                self.stdout.write(f"{key}: {value}")

        opened = summary.get("opened_trades", 0)

        # Auto-start monitor if trades were opened
        if opened > 0:
            self._start_monitor(username, user_logger)
        # Auto-start entry scanner if breakout instruments are pending
        elif not market_date and not scan_entries and self._needs_entry_scan(summary):
            self._start_entry_scanner(username, mode_override, user_logger)

        # Entry scanning loop (when --scan-entries is active)
        if scan_entries and not market_date:
            self._run_entry_scan_loop(
                user, username, execution_mode, sandbox, scan_interval, user_logger,
            )

    def _get_user(self, username):
        User = get_user_model()
        try:
            return User.objects.get(username__iexact=username)
        except User.DoesNotExist as exc:
            raise CommandError(f"User '{username}' not found.") from exc

    # ------------------------------------------------------------------
    # Entry scanning helpers
    # ------------------------------------------------------------------

    _PENDING_MESSAGES = frozenset({
        "awaiting_candles",
        "no_breakout",
        "await_next_candle",
        "previous_levels_unavailable",
    })

    def _needs_entry_scan(self, summary: dict) -> bool:
        """Return True if any instrument is waiting for a breakout entry."""
        for inst_summary in summary.get("instrument_summaries", []):
            msg = inst_summary.get("message", "")
            if msg in self._PENDING_MESSAGES:
                return True
        return False

    @staticmethod
    def _market_is_open() -> bool:
        """Return True if current IST time is within 09:15 – 15:25."""
        now = timezone.localtime()
        return time(9, 15) <= now.time() <= time(15, 25)

    @staticmethod
    def _seconds_until_next_candle_close(candle_minutes: int = 5, buffer_secs: int = 2) -> float:
        """Return seconds to sleep until the next candle boundary + buffer.

        For 5-minute candles closing at :00, :05, :10, ... :55,
        this calculates the wait so the scanner wakes at e.g. 09:20:02,
        09:25:02 — right after the candle closes, with no drift.
        """
        now = timezone.localtime()
        current_minute = now.minute
        current_second = now.second + now.microsecond / 1_000_000

        # Minutes into the current candle period
        minutes_into_candle = current_minute % candle_minutes
        # Seconds remaining until the candle boundary
        remaining_minutes = candle_minutes - minutes_into_candle
        remaining_seconds = (remaining_minutes * 60) - current_second + buffer_secs

        # If we're past the boundary + buffer (e.g. 09:20:03 with 2s buffer),
        # wait for the next one
        if remaining_seconds <= 0:
            remaining_seconds += candle_minutes * 60

        return remaining_seconds

    def _start_monitor(self, username: str, logger: logging.Logger) -> None:
        self.stdout.write("\n" + "=" * 80)
        self.stdout.write(self.style.SUCCESS("🚀 STARTING TRADE MONITOR"))
        self.stdout.write("=" * 80)
        try:
            import sys as _sys
            logs_dir = Path(settings.BASE_DIR) / "logs" / "users"
            logs_dir.mkdir(parents=True, exist_ok=True)
            monitor_log = open(logs_dir / f"{username}_monitor.log", "a")
            subprocess.Popen(
                [_sys.executable, "manage.py", "monitor_trades", username, "--interval", "15"],
                stdout=monitor_log,
                stderr=monitor_log,
                start_new_session=True,
            )
            self.stdout.write(self.style.SUCCESS("✅ Monitor started in background"))
            logger.info("Monitor started in background")
        except Exception as e:
            self.stdout.write(self.style.WARNING(f"⚠️  Could not auto-start monitor: {e}"))
            self.stdout.write(f"Please manually run: python manage.py monitor_trades {username}")
        self.stdout.write("=" * 80 + "\n")

    def _start_entry_scanner(self, username: str, mode_override: str, logger: logging.Logger) -> None:
        """Spawn a background process that re-runs the strategy every 5 min."""
        self.stdout.write("\n" + "=" * 80)
        self.stdout.write(self.style.SUCCESS("🔄 STARTING ENTRY SCANNER"))
        self.stdout.write("=" * 80)
        try:
            import sys as _sys
            cmd = [_sys.executable, "manage.py", "run_strategy_alpha", username, "--scan-entries"]
            if mode_override:
                cmd.extend(["--mode", mode_override])
            logs_dir = Path(settings.BASE_DIR) / "logs" / "users"
            logs_dir.mkdir(parents=True, exist_ok=True)
            scanner_log = open(logs_dir / f"{username}_scanner.log", "a")
            subprocess.Popen(
                cmd,
                stdout=scanner_log,
                stderr=scanner_log,
                start_new_session=True,
            )
            self.stdout.write(self.style.SUCCESS("✅ Entry scanner started in background"))
            self.stdout.write("Scanner will re-check every 5 minutes until trades open or market closes.")
            logger.info("Entry scanner started in background (--scan-entries)")
        except Exception as e:
            self.stdout.write(self.style.WARNING(f"⚠️  Could not auto-start entry scanner: {e}"))
        self.stdout.write("=" * 80 + "\n")

    def _run_entry_scan_loop(
        self,
        user,
        username: str,
        execution_mode: str | None,
        sandbox: bool,
        interval: int,
        logger: logging.Logger,
    ) -> None:
        """Re-run strategy aligned to 5-minute candle boundaries until trades open or market closes."""
        scan_number = 0
        logger.info("=" * 80)
        logger.info("ENTRY SCANNER ACTIVE — aligned to 5-minute candle closes")
        logger.info("=" * 80)

        while self._market_is_open():
            # Sleep until the next 5-minute candle boundary (e.g. 9:20:02, 9:25:02)
            wait = self._seconds_until_next_candle_close(candle_minutes=5, buffer_secs=2)
            next_wake = (timezone.localtime() + timedelta(seconds=wait)).strftime("%H:%M:%S")
            logger.info("Sleeping %.1fs until next candle close at ~%s", wait, next_wake)
            _time.sleep(wait)
            scan_number += 1

            if not self._market_is_open():
                break

            logger.info("─" * 60)
            logger.info("Entry scan #%d at %s", scan_number, datetime.now().strftime("%H:%M:%S"))
            logger.info("─" * 60)

            try:
                with maybe_override_sandbox(sandbox):
                    summary = StrategyAlphaEngine(
                        user=user,
                        execution_mode=execution_mode,
                        logger=logger,
                    ).run()

                opened = summary.get("opened_trades", 0)
                logger.info("Scan #%d result — opened: %d", scan_number, opened)

                if opened > 0:
                    logger.info("✓ Trades opened — stopping entry scanner, starting monitor")
                    self._start_monitor(username, logger)
                    return

                if not self._needs_entry_scan(summary):
                    logger.info("No instruments awaiting breakout — stopping entry scanner")
                    return

            except Exception as exc:
                logger.warning("Entry scan #%d failed: %s", scan_number, exc)

        logger.info("Market closed — entry scanner stopped after %d scans", scan_number)
