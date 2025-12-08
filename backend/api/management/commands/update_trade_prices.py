"""Management command to simulate real-time price updates for demo trades."""
from decimal import Decimal
from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from api.models import Trade


class Command(BaseCommand):
    help = "Simulate real-time price updates for open trades"

    def add_arguments(self, parser):
        parser.add_argument(
            "--username",
            type=str,
            help="Update prices only for specific user",
        )
        parser.add_argument(
            "--instrument",
            type=str,
            help="Update prices only for specific instrument",
        )
        parser.add_argument(
            "--price",
            type=float,
            help="Set specific price for the trade",
        )
        parser.add_argument(
            "--random",
            action="store_true",
            help="Update with random price movements",
        )

    def handle(self, *args, **options):
        username = options.get("username")
        instrument = options.get("instrument")
        price = options.get("price")
        use_random = options.get("random")

        trades = Trade.objects.filter(status=Trade.Status.OPEN)

        if username:
            trades = trades.filter(user__username=username)

        if instrument:
            trades = trades.filter(instrument__instrument=instrument)

        if not trades.exists():
            self.stdout.write(self.style.WARNING("No open trades found matching criteria."))
            return

        self.stdout.write(f"Found {trades.count()} open trades to update.")

        for trade in trades:
            if price is not None:
                # Set specific price
                new_price = Decimal(str(price))
            elif use_random:
                # Simulate random price movement
                import random
                movement = random.uniform(-100, 100)  # +/- 100 points
                new_price = Decimal(str(float(trade.entry_price) + movement))
            else:
                # Simulate upward movement towards target
                if trade.target_price:
                    movement = (trade.target_price - trade.entry_price) * Decimal("0.3")
                    new_price = trade.entry_price + movement
                else:
                    new_price = trade.entry_price + Decimal("50")  # Default +50 points

            trade.last_price = new_price.quantize(Decimal("0.01"))
            trade.save(update_fields=["last_price", "updated_at"])

            pnl = trade.get_realtime_pnl()
            self.stdout.write(
                self.style.SUCCESS(
                    f"✓ {trade.instrument.instrument}: Price {new_price} | P&L: ₹{pnl}"
                )
            )

        self.stdout.write(self.style.SUCCESS("Price update completed!"))
