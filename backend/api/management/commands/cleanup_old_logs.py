"""
Management command to clean up log files older than specified days.
"""
import os
from datetime import datetime, timedelta
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Clean up log files older than specified days"

    def add_arguments(self, parser):
        parser.add_argument(
            "--days",
            type=int,
            default=5,
            help="Delete logs older than this many days (default: 5)",
        )

    def handle(self, *args, **options):
        days = options["days"]
        cutoff_date = datetime.now() - timedelta(days=days)

        logs_dir = Path(settings.BASE_DIR) / "logs"
        if not logs_dir.exists():
            self.stdout.write(self.style.WARNING("Logs directory does not exist"))
            return

        deleted_count = 0
        total_size = 0

        for log_file in logs_dir.glob("**/*.log"):
            try:
                file_mtime = datetime.fromtimestamp(log_file.stat().st_mtime)
                if file_mtime < cutoff_date:
                    file_size = log_file.stat().st_size
                    log_file.unlink()
                    deleted_count += 1
                    total_size += file_size
                    self.stdout.write(
                        f"Deleted: {log_file.name} (modified: {file_mtime.strftime('%Y-%m-%d')})"
                    )
            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(f"Error deleting {log_file.name}: {e}")
                )

        if deleted_count > 0:
            size_mb = total_size / (1024 * 1024)
            self.stdout.write(
                self.style.SUCCESS(
                    f"✅ Deleted {deleted_count} log file(s), freed {size_mb:.2f} MB"
                )
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(f"✅ No log files older than {days} days found")
            )
