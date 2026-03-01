from __future__ import annotations

import logging
import subprocess
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.test.utils import override_settings
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

        # Auto-start monitor if trades were opened
        if summary.get("opened_trades", 0) > 0:
            self.stdout.write("\n" + "=" * 80)
            self.stdout.write(self.style.SUCCESS("🚀 STARTING TRADE MONITOR"))
            self.stdout.write("=" * 80)
            try:
                subprocess.Popen(
                    ["python3", "manage.py", "monitor_trades", username, "--interval", "15"],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                )
                self.stdout.write(self.style.SUCCESS("✅ Monitor started in background"))
                self.stdout.write("Monitor will run until all trades are closed.")
            except Exception as e:
                self.stdout.write(self.style.WARNING(f"⚠️  Could not auto-start monitor: {e}"))
                self.stdout.write(f"Please manually run: python manage.py monitor_trades {username}")
            self.stdout.write("=" * 80 + "\n")

    def _get_user(self, username):
        User = get_user_model()
        try:
            return User.objects.get(username__iexact=username)
        except User.DoesNotExist as exc:
            raise CommandError(f"User '{username}' not found.") from exc
