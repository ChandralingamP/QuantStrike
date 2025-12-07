from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

from django.conf import settings

MONEY_QUANTIZER = Decimal("0.01")


def _quantize(amount: Decimal) -> Decimal:
    if amount is None:
        return Decimal("0.00")
    return amount.quantize(MONEY_QUANTIZER, rounding=ROUND_HALF_UP)


def _ensure_decimal(value) -> Decimal:
    if isinstance(value, Decimal):
        return value
    if value is None:
        return Decimal("0")
    try:
        return Decimal(value)
    except Exception:  # pragma: no cover - defensive fallback
        return Decimal("0")


def calculate_margin_required(trade) -> Decimal:
    """Estimate the capital requirement for the trade entry leg."""
    entry_price = _ensure_decimal(getattr(trade, "entry_price", None))
    quantity = _ensure_decimal(getattr(trade, "quantity", 0))
    if entry_price <= 0 or quantity <= 0:
        return Decimal("0.00")

    margin = entry_price * quantity
    buffer_multiplier = getattr(settings, "QUANTSTRIKE_MARGIN_BUFFER_MULTIPLIER", Decimal("1"))
    try:
        margin *= buffer_multiplier
    except Exception:  # pragma: no cover - defensive fallback
        margin = entry_price * quantity

    return _quantize(margin)


def calculate_total_brokerage(trade) -> Decimal:
    """Calculate brokerage (including GST) for executed legs."""
    per_leg = getattr(settings, "QUANTSTRIKE_BROKERAGE_PER_LEG", Decimal("0"))
    gst_rate = getattr(settings, "QUANTSTRIKE_BROKERAGE_GST_RATE", Decimal("0"))

    try:
        per_leg = _ensure_decimal(per_leg)
    except Exception:  # pragma: no cover - defensive fallback
        per_leg = Decimal("0")

    if per_leg <= 0:
        return Decimal("0.00")

    executed_legs = 0
    if getattr(trade, "entry_price", None):
        executed_legs += 1
    if getattr(trade, "exit_price", None):
        executed_legs += 1

    if executed_legs == 0:
        return Decimal("0.00")

    brokerage = per_leg * Decimal(executed_legs)

    try:
        gst_rate = _ensure_decimal(gst_rate)
    except Exception:  # pragma: no cover - defensive fallback
        gst_rate = Decimal("0")

    if gst_rate > 0:
        brokerage += brokerage * gst_rate

    return _quantize(brokerage)


def calculate_net_pnl(trade) -> Decimal:
    """Gross P&L minus brokerage."""
    pnl = _ensure_decimal(getattr(trade, "pnl", Decimal("0")))
    brokerage = calculate_total_brokerage(trade)
    net = pnl - brokerage
    return _quantize(net)
