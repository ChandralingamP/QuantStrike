import os

from django.apps import AppConfig


class ApiConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "api"

    def ready(self):
        # Start the scheduler only in the main process (not in autoreload child
        # or management commands). RUN_MAIN is set by Django's autoreloader.
        is_runserver = "runserver" in os.environ.get("DJANGO_SETTINGS_MODULE", "") or True
        is_main_process = os.environ.get("RUN_MAIN") == "true"

        # Also skip if running management commands (migrate, shell, etc.)
        import sys
        is_management_cmd = len(sys.argv) > 1 and sys.argv[1] != "runserver"

        if is_main_process and not is_management_cmd:
            from . import scheduler
            scheduler.start()
