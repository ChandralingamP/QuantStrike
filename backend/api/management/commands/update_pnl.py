"""Management command to update P&L for open trades using LTP batch API."""
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model

from api.models import Trade, UserProfile
from api.services.smartapi_market import SmartAPIMarketClient

User = get_user_model()


class Command(BaseCommand):
    help = "Update P&L for open trades using live LTP data"

    def add_arguments(self, parser):
        parser.add_argument(
            "username",
            type=str,
            help="Username of the trader",
        )
        parser.add_argument(
            "--strategy",
            type=str,
            default="strategy_one",
            help="Strategy code to filter trades (default: strategy_one)",
        )

    def handle(self, *args, **options):
        username = options["username"]
        strategy_code = options["strategy"]

        # Get user and profile
        try:
            user = User.objects.get(username=username)
            profile = UserProfile.objects.get(user=user)
        except User.DoesNotExist:
            self.stdout.write(self.style.ERROR(f"❌ User '{username}' not found"))
            return
        except UserProfile.DoesNotExist:
            self.stdout.write(self.style.ERROR(f"❌ User profile not found for '{username}'"))
            return

        # Get open trades
        open_trades = Trade.objects.filter(
            user=user,
            strategy_code=strategy_code,
            status=Trade.Status.OPEN,
        ).select_related('instrument')

        if not open_trades.exists():
            self.stdout.write(self.style.WARNING("⚠️  No open trades found"))
            return

        self.stdout.write(f"\n📊 Found {open_trades.count()} open trades for {username}")
        
        # Display trades before update
        self.stdout.write("\n" + "=" * 80)
        self.stdout.write("OPEN TRADES BEFORE UPDATE:")
        self.stdout.write("=" * 80)
        for trade in open_trades:
            # Get instrument display name
            instrument_display = trade.instrument.get_instrument_display() if hasattr(trade.instrument, 'get_instrument_display') else str(trade.instrument)
            self.stdout.write(
                f"Trade #{trade.id}: {instrument_display} | "
                f"{trade.contract_symbol} | "
                f"Direction: {trade.direction} | "
                f"Qty: {trade.quantity} | "
                f"Entry: ₹{trade.entry_price or 0} | "
                f"Last: ₹{trade.last_price or 0} | "
                f"P&L: ₹{trade.pnl}"
            )

        # Create SmartAPI client
        client = SmartAPIMarketClient(
            api_key=profile.api_key or "",
            jwt_token=profile.jwt_token or "",
        )

        # Update P&L
        self.stdout.write("\n🔄 Updating P&L using LTP batch API...")
        result = client.update_trades_pnl(list(open_trades))

        # Display results
        self.stdout.write("\n" + "=" * 80)
        self.stdout.write("UPDATE RESULTS:")
        self.stdout.write("=" * 80)
        self.stdout.write(f"✅ Updated: {result['updated']} trades")
        self.stdout.write(f"❌ Errors: {result['errors']} trades")
        self.stdout.write(f"📊 LTP Values Fetched: {result['total_ltps']}")
        self.stdout.write(f"💬 Message: {result['message']}")

        # Refresh and display trades after update
        open_trades = Trade.objects.filter(
            user=user,
            strategy_code=strategy_code,
            status=Trade.Status.OPEN,
        ).select_related('instrument')

        self.stdout.write("\n" + "=" * 80)
        self.stdout.write("OPEN TRADES AFTER UPDATE:")
        self.stdout.write("=" * 80)
        total_pnl = 0
        for trade in open_trades:
            # Get instrument display name
            instrument_display = trade.instrument.get_instrument_display() if hasattr(trade.instrument, 'get_instrument_display') else str(trade.instrument)
            self.stdout.write(
                f"Trade #{trade.id}: {instrument_display} | "
                f"{trade.contract_symbol} | "
                f"Direction: {trade.direction} | "
                f"Qty: {trade.quantity} | "
                f"Entry: ₹{trade.entry_price or 0} | "
                f"Last: ₹{trade.last_price or 0} | "
                f"P&L: ₹{trade.pnl}"
            )
            total_pnl += trade.pnl

        self.stdout.write("\n" + "=" * 80)
        self.stdout.write(f"💰 TOTAL P&L: ₹{total_pnl}")
        self.stdout.write("=" * 80 + "\n")
        
        self.stdout.write(self.style.SUCCESS(f"✅ P&L update completed"))
