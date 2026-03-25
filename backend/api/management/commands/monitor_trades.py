"""
Real-time trade monitoring service that automatically exits trades when SL/TP is hit.
Runs continuously and checks open trades every 15 seconds.

Usage:
    python manage.py monitor_trades [username] [--interval SECONDS]
"""

import time
from datetime import datetime
from decimal import Decimal
from typing import Dict, List

from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth.models import User
from django.db import close_old_connections
from django.utils import timezone

from api.models import Trade, UserProfile
from api.services.smartapi_market import SmartAPIMarketClient


class Command(BaseCommand):
    help = "Monitor open trades and auto-exit when SL/TP is hit (runs continuously)"

    def add_arguments(self, parser):
        parser.add_argument(
            "username",
            type=str,
            help="Username to monitor trades for",
        )
        parser.add_argument(
            "--interval",
            type=int,
            default=15,
            help="Check interval in seconds (default: 15)",
        )
        parser.add_argument(
            "--strategy",
            type=str,
            default="strategy_alpha",
            help="Strategy code to monitor (default: strategy_alpha)",
        )

    def handle(self, *args, **options):
        username = options["username"]
        interval = options["interval"]
        strategy_code = options["strategy"]

        self.stdout.write("\n" + "=" * 80)
        self.stdout.write(self.style.SUCCESS("🔍 TRADE MONITOR SERVICE STARTED"))
        self.stdout.write("=" * 80)
        self.stdout.write(f"👤 User: {username}")
        self.stdout.write(f"📊 Strategy: {strategy_code}")
        self.stdout.write(f"⏱️  Check Interval: {interval} seconds")
        self.stdout.write(f"🕐 Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        self.stdout.write(f"📦 Product Type: INTRADAY (MIS)")
        self.stdout.write(f"⏰ EOD Auto-Exit: 3:35 PM (Demo trades only)")
        self.stdout.write("=" * 80)
        self.stdout.write(self.style.WARNING("\n⚠️  Press Ctrl+C to stop monitoring\n"))

        # Get user
        try:
            user = User.objects.get(username=username)
        except User.DoesNotExist:
            raise CommandError(f"User '{username}' not found")

        # Get user profile for API credentials
        try:
            profile = UserProfile.objects.get(user=user)
        except UserProfile.DoesNotExist:
            raise CommandError(f"UserProfile not found for {username}")

        # Initialize API client
        client = SmartAPIMarketClient(
            api_key=profile.api_key,
            jwt_token=profile.jwt_token
        )

        iteration = 0
        try:
            # Initial check - exit immediately if no open trades
            open_trades = Trade.objects.filter(
                user=user,
                strategy_code=strategy_code,
                status=Trade.Status.OPEN,
            ).select_related('instrument')

            if not open_trades.exists():
                self.stdout.write("\n" + "=" * 80)
                self.stdout.write(self.style.WARNING("⚠️  NO OPEN TRADES FOUND"))
                self.stdout.write("=" * 80)
                self.stdout.write("Monitor will exit. Start monitoring when trades are placed.")
                self.stdout.write("=" * 80 + "\n")
                return

            while True:
                iteration += 1
                current_time = datetime.now().strftime('%H:%M:%S')
                
                self.stdout.write(f"\n{'─' * 80}")
                self.stdout.write(f"🔄 Check #{iteration} at {current_time}")
                self.stdout.write(f"{'─' * 80}")

                # Close stale DB connections before each iteration
                close_old_connections()

                try:
                    self._monitor_iteration(
                        user, strategy_code, client, interval,
                    )
                except KeyboardInterrupt:
                    raise
                except Exception as iter_err:
                    self.stdout.write(
                        self.style.ERROR(f"⚠️  Iteration #{iteration} error: {iter_err}")
                    )
                    close_old_connections()

                # Sleep until next check
                time.sleep(interval)

        except KeyboardInterrupt:
            self.stdout.write("\n" + "=" * 80)
            self.stdout.write(self.style.WARNING("⏹️  Monitoring stopped by user"))
            self.stdout.write("=" * 80)
            self.stdout.write(f"Total checks performed: {iteration}")
            self.stdout.write(f"Stopped at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            self.stdout.write("=" * 80 + "\n")

        except Exception as e:
            self.stdout.write("\n" + "=" * 80)
            self.stdout.write(self.style.ERROR(f"❌ Error: {str(e)}"))
            self.stdout.write("=" * 80 + "\n")
            raise

    def _monitor_iteration(self, user, strategy_code, client, interval):
        """Single monitoring pass — query trades, fetch LTP, check SL/TP/EOD."""
        open_trades = Trade.objects.filter(
            user=user,
            strategy_code=strategy_code,
            status=Trade.Status.OPEN,
        ).select_related('instrument')

        if not open_trades.exists():
            self.stdout.write("\n" + "=" * 80)
            self.stdout.write(self.style.SUCCESS("✅ ALL TRADES CLOSED"))
            self.stdout.write("=" * 80)
            self.stdout.write(f"Stopped at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            self.stdout.write("Monitor exiting - no more trades to watch.")
            self.stdout.write("=" * 80 + "\n")
            raise SystemExit(0)

        self.stdout.write(f"📊 Monitoring {open_trades.count()} open trades...")

        # Fetch current prices - build exchange_tokens dict grouped by exchange
        exchange_tokens: Dict[str, List[str]] = {}
        token_trade_map: Dict[str, tuple] = {}  # token -> (exchange, trade)

        for trade in open_trades:
            if trade.contract_token:
                exchange = trade.instrument.exchange or "NFO"
                exchange_tokens.setdefault(exchange, []).append(trade.contract_token)
                token_trade_map[trade.contract_token] = (exchange, trade)

        if not token_trade_map:
            self.stdout.write(self.style.WARNING("⚠️  No contract tokens found"))
            return

        # Get LTP for all tokens
        ltp_data = client.get_ltp_batch(exchange_tokens=exchange_tokens)

        # Check current time for EOD auto-exit (3:35 PM for demo trades)
        now = timezone.now()
        current_time_val = now.time()
        eod_cutoff = datetime.strptime("15:35:00", "%H:%M:%S").time()

        # Check each trade for SL/TP/EOD
        exits_performed = 0
        for token, (exchange, trade) in token_trade_map.items():
            ltp_key = f"{exchange}:{token}"
            current_price = ltp_data.get(ltp_key)

            if not current_price:
                continue

            # Update last_price
            trade.last_price = current_price
            trade.pnl = trade.get_realtime_pnl()
            trade.save(update_fields=["last_price", "pnl", "updated_at"])

            should_exit = False
            exit_reason = ""

            # Check EOD cutoff (3:35 PM) for DEMO trades only
            if trade.execution_mode == Trade.ExecutionMode.DEMO and current_time_val >= eod_cutoff:
                should_exit = True
                exit_reason = f"EOD Auto-Square Off (Demo) at {now.strftime('%H:%M:%S')}"

            # Check Stop Loss
            elif trade.stop_loss_price and current_price <= trade.stop_loss_price:
                should_exit = True
                exit_reason = f"SL Hit (₹{current_price} <= ₹{trade.stop_loss_price})"

            # Check Target Price
            elif trade.target_price and current_price >= trade.target_price:
                should_exit = True
                exit_reason = f"Target Hit (₹{current_price} >= ₹{trade.target_price})"

            if should_exit:
                trade.status = Trade.Status.CLOSED
                trade.exit_price = current_price
                trade.exit_datetime = timezone.now()
                trade.pnl = trade.get_realtime_pnl()
                trade.save(update_fields=[
                    "status", "exit_price", "exit_datetime", "pnl", "updated_at",
                ])
                exits_performed += 1
                pnl_color = self.style.SUCCESS if trade.pnl >= 0 else self.style.ERROR
                self.stdout.write(self.style.WARNING(f"\n🚨 AUTO-EXIT EXECUTED:"))
                self.stdout.write(f"   Trade #{trade.id}: {trade.contract_symbol}")
                self.stdout.write(f"   Reason: {exit_reason}")
                self.stdout.write(f"   Entry: ₹{trade.entry_price} → Exit: ₹{trade.exit_price}")
                self.stdout.write(pnl_color(f"   P&L: ₹{trade.pnl}"))

        if exits_performed > 0:
            self.stdout.write(self.style.SUCCESS(f"\n✅ Closed {exits_performed} trade(s)"))
        else:
            self.stdout.write("✓ All trades within SL/TP bounds")
