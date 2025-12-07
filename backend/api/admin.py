from django.contrib import admin

from .models import Strategy


@admin.register(Strategy)
class StrategyAdmin(admin.ModelAdmin):
    list_display = ("name", "symbol", "status", "timeframe", "created_at")
    list_filter = ("status", "timeframe")
    search_fields = ("name", "symbol")
    ordering = ("-created_at",)
