"""
Built-in job scheduler for QuantStrike.

Runs all scheduled tasks (strategy execution, scrip master refresh, etc.)
inside the Django process using APScheduler. No external crontab needed.

Started automatically when the Django server boots (see apps.py).
"""

import logging
import subprocess
import sys
from pathlib import Path

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from django.conf import settings

logger = logging.getLogger("scheduler")

_scheduler: BackgroundScheduler | None = None


def _run_management_command(*args: str) -> None:
    """Run a Django management command in a subprocess."""
    manage_py = str(Path(settings.BASE_DIR) / "manage.py")
    cmd = [sys.executable, manage_py, *args]
    log_dir = Path(settings.BASE_DIR) / "logs"
    log_dir.mkdir(exist_ok=True)

    # Pick log file based on command name
    cmd_name = args[0] if args else "unknown"
    log_map = {
        "update_instruments": "instruments.log",
        "update_scrip_master": "instruments.log",
        "load_instrument_metadata": "metadata.log",
        "run_all_strategies": "strategies.log",
        "cleanup_old_logs": "log_cleanup.log",
    }
    log_file = log_dir / log_map.get(cmd_name, f"{cmd_name}.log")

    logger.info("Running: %s", " ".join(args))
    try:
        with open(log_file, "a") as lf:
            subprocess.run(
                cmd,
                stdout=lf,
                stderr=subprocess.STDOUT,
                cwd=str(settings.BASE_DIR),
                timeout=600,
            )
        logger.info("Completed: %s", cmd_name)
    except subprocess.TimeoutExpired:
        logger.warning("Timed out: %s (600s limit)", cmd_name)
    except Exception:
        logger.exception("Failed: %s", cmd_name)


# ── Job functions ────────────────────────────────────────────


def job_clear_daily_caches():
    """7:00 AM IST — Clear stale daily caches before market opens."""
    _run_management_command("update_instruments", "--skip-refresh")


def job_run_strategies():
    """9:16 AM IST — Run Strategy Alpha for all active users."""
    _run_management_command("run_all_strategies", "--strategy", "strategy_alpha")


def job_refresh_scrip_master():
    """4:00 PM IST — Download latest contract list from Angel One."""
    _run_management_command("update_scrip_master", "--force")


def job_roll_expiries():
    """4:15 PM IST — Roll expired contracts, sync metadata."""
    _run_management_command("update_instruments")


def job_load_metadata():
    """4:20 PM IST — Load instrument metadata from JSON."""
    data_path = str(Path(settings.BASE_DIR) / "data" / "instruments.json")
    _run_management_command("load_instrument_metadata", "--path", data_path)


def job_cleanup_logs():
    """Midnight — Delete log files older than 5 days."""
    _run_management_command("cleanup_old_logs", "--days", "5")


# ── Scheduler lifecycle ─────────────────────────────────────


def start():
    """Start the background scheduler with all trading jobs."""
    global _scheduler
    if _scheduler is not None:
        return  # Already running

    _scheduler = BackgroundScheduler(timezone="Asia/Kolkata")

    # ── PRE-MARKET ──────────────────────────────────────────
    _scheduler.add_job(
        job_clear_daily_caches,
        CronTrigger(hour=7, minute=0, day_of_week="mon-fri", timezone="Asia/Kolkata"),
        id="clear_daily_caches",
        name="Clear stale daily caches (7:00 AM IST)",
        replace_existing=True,
    )

    _scheduler.add_job(
        job_run_strategies,
        CronTrigger(hour=9, minute=16, day_of_week="mon-fri", timezone="Asia/Kolkata"),
        id="run_strategies",
        name="Run Strategy Alpha (9:16 AM IST)",
        replace_existing=True,
    )

    # ── POST-MARKET ─────────────────────────────────────────
    _scheduler.add_job(
        job_refresh_scrip_master,
        CronTrigger(hour=16, minute=0, day_of_week="mon-fri", timezone="Asia/Kolkata"),
        id="refresh_scrip_master",
        name="Refresh scrip master (4:00 PM IST)",
        replace_existing=True,
    )

    _scheduler.add_job(
        job_roll_expiries,
        CronTrigger(hour=16, minute=15, day_of_week="mon-fri", timezone="Asia/Kolkata"),
        id="roll_expiries",
        name="Roll expiries + sync metadata (4:15 PM IST)",
        replace_existing=True,
    )

    _scheduler.add_job(
        job_load_metadata,
        CronTrigger(hour=16, minute=20, day_of_week="mon-fri", timezone="Asia/Kolkata"),
        id="load_metadata",
        name="Load instrument metadata (4:20 PM IST)",
        replace_existing=True,
    )

    # ── MAINTENANCE ─────────────────────────────────────────
    _scheduler.add_job(
        job_cleanup_logs,
        CronTrigger(hour=0, minute=0, timezone="Asia/Kolkata"),
        id="cleanup_logs",
        name="Clean up old logs (midnight IST)",
        replace_existing=True,
    )

    _scheduler.start()
    logger.info(
        "Scheduler started with %d jobs: %s",
        len(_scheduler.get_jobs()),
        ", ".join(j.name for j in _scheduler.get_jobs()),
    )


def stop():
    """Shut down the scheduler gracefully."""
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
        logger.info("Scheduler stopped")
