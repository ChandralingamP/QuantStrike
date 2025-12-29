"""
Management command to run strategies for all active users automatically.
Designed for cron/scheduled execution.
"""
import subprocess
from datetime import datetime
from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from django.utils import timezone

from api.models import AlgoConfiguration, StrategyActivation, UserProfile


class Command(BaseCommand):
    help = "Run activated strategies for all users (for scheduled/cron execution)"

    def add_arguments(self, parser):
        parser.add_argument(
            "--strategy",
            type=str,
            default="strategy_alpha",
            help="Strategy code to run (default: strategy_alpha)",
        )
        parser.add_argument(
            "--mode",
            type=str,
            choices=["demo", "live"],
            help="Force execution mode (demo|live), otherwise uses user's activation mode",
        )

    def handle(self, *args, **options):
        strategy_code = options["strategy"]
        mode_override = options.get("mode")

        now = timezone.now()
        self.stdout.write("\n" + "=" * 80)
        self.stdout.write(self.style.SUCCESS("🤖 AUTOMATED STRATEGY EXECUTION"))
        self.stdout.write("=" * 80)
        self.stdout.write(f"⏰ Time: {now.strftime('%Y-%m-%d %H:%M:%S %Z')}")
        self.stdout.write(f"📊 Strategy: {strategy_code}")
        if mode_override:
            self.stdout.write(f"🎯 Mode: {mode_override} (forced)")
        self.stdout.write("=" * 80 + "\n")

        # Get all users with active algo config and strategy activation
        eligible_users = User.objects.filter(
            algo_configuration__algo_active=True,
            strategy_activations__strategy_code=strategy_code,
            strategy_activations__is_active=True,
        ).distinct()

        if not eligible_users.exists():
            self.stdout.write(
                self.style.WARNING("⚠️  No users with active algo and strategy activation found")
            )
            self.stdout.write("=" * 80 + "\n")
            return

        self.stdout.write(f"👥 Found {eligible_users.count()} eligible user(s)\n")

        success_count = 0
        skip_count = 0
        error_count = 0
        monitor_started_count = 0

        for user in eligible_users:
            self.stdout.write("\n" + "─" * 80)
            self.stdout.write(f"👤 Processing: {user.username}")
            self.stdout.write("─" * 80)

            try:
                # Check if user has valid profile for live mode
                algo_config = AlgoConfiguration.objects.get(user=user)
                activation = StrategyActivation.objects.get(
                    user=user, strategy_code=strategy_code
                )

                execution_mode = mode_override or activation.execution_mode

                # Validate credentials for both demo and live modes
                # (both need real market data from Angel API)
                try:
                    profile = UserProfile.objects.get(user=user)
                    if not profile.api_key or not profile.jwt_token:
                        self.stdout.write(
                            self.style.WARNING(
                                f"⏭️  Skipped: No brokerage credentials for {user.username}"
                            )
                        )
                        skip_count += 1
                        continue
                except UserProfile.DoesNotExist:
                    self.stdout.write(
                        self.style.WARNING(
                            f"⏭️  Skipped: No profile found for {user.username}"
                        )
                    )
                    skip_count += 1
                    continue

                # Additional validation for live mode only
                if execution_mode == "live":
                    if not algo_config.market_active:
                        self.stdout.write(
                            self.style.WARNING(
                                f"⏭️  Skipped: Market access disabled for {user.username}"
                            )
                        )
                        skip_count += 1
                        continue

                # Run strategy
                cmd = ["python3", "manage.py", "run_strategy_alpha", user.username]
                if mode_override:
                    cmd.extend(["--mode", mode_override])

                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=120,  # 2 minute timeout
                )

                if result.returncode == 0:
                    # Check if trades were opened (to start monitor)
                    if "opened_trades" in result.stdout and "Monitor started" in result.stdout:
                        monitor_started_count += 1
                        self.stdout.write(
                            self.style.SUCCESS(
                                f"✅ {user.username}: Strategy executed, monitor started"
                            )
                        )
                    else:
                        self.stdout.write(
                            self.style.SUCCESS(
                                f"✅ {user.username}: Strategy executed"
                            )
                        )
                    success_count += 1

                    # Show summary
                    if "opened_trades" in result.stdout:
                        for line in result.stdout.split("\n"):
                            if "opened_trades" in line or "closed_trades" in line or "net_pnl" in line:
                                self.stdout.write(f"   {line.strip()}")
                else:
                    self.stdout.write(
                        self.style.WARNING(
                            f"⏭️  {user.username}: Strategy skipped or no conditions met"
                        )
                    )
                    skip_count += 1

            except subprocess.TimeoutExpired:
                self.stdout.write(
                    self.style.ERROR(f"❌ {user.username}: Execution timeout (>2 min)")
                )
                error_count += 1
            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(f"❌ {user.username}: Error - {str(e)}")
                )
                error_count += 1

        # Final summary
        self.stdout.write("\n" + "=" * 80)
        self.stdout.write(self.style.SUCCESS("📊 EXECUTION SUMMARY"))
        self.stdout.write("=" * 80)
        self.stdout.write(f"✅ Success: {success_count} user(s)")
        self.stdout.write(f"⏭️  Skipped: {skip_count} user(s)")
        self.stdout.write(f"❌ Errors: {error_count} user(s)")
        self.stdout.write(f"🔍 Monitors Started: {monitor_started_count} user(s)")
        self.stdout.write(f"⏰ Completed at: {timezone.now().strftime('%Y-%m-%d %H:%M:%S')}")
        self.stdout.write("=" * 80 + "\n")
