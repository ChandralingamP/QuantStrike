from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


class Strategy(models.Model):
    STATUS_CHOICES = [
        ("draft", "Draft"),
        ("live", "Live"),
        ("paused", "Paused"),
        ("retired", "Retired"),
    ]

    name = models.CharField(max_length=255)
    symbol = models.CharField(max_length=32, blank=True)
    timeframe = models.CharField(max_length=32, blank=True)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default="draft")
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:  # pragma: no cover - convenience representation
        return self.name


class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="profile")
    brokerage_user_id = models.CharField(max_length=64)
    api_key = models.CharField(max_length=128)
    mobile_number = models.CharField(max_length=16)
    jwt_token = models.TextField(blank=True)
    refresh_token = models.TextField(blank=True)
    feed_token = models.TextField(blank=True)
    token_state = models.CharField(max_length=64, blank=True)
    token_received_at = models.DateTimeField(null=True, blank=True)
    last_token_check_at = models.DateTimeField(null=True, blank=True)
    last_token_status = models.CharField(max_length=64, blank=True)
    last_token_message = models.CharField(max_length=255, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:  # pragma: no cover - admin clarity
        return f"Profile for {self.user.username}"


class EmailOTP(models.Model):
    class Purpose(models.TextChoices):
        SIGNUP = "signup", "Signup"
        PASSWORD_RESET = "password_reset", "Password Reset"

    email = models.EmailField()
    otp_hash = models.CharField(max_length=128)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    is_used = models.BooleanField(default=False)
    purpose = models.CharField(
        max_length=32,
        choices=Purpose.choices,
        default=Purpose.SIGNUP,
    )

    class Meta:
        indexes = [
            models.Index(fields=["email", "is_used"]),
            models.Index(fields=["email", "purpose", "is_used"]),
        ]

    def mark_used(self) -> None:
        self.is_used = True
        self.save(update_fields=["is_used"])

    def is_valid(self) -> bool:
        return not self.is_used and timezone.now() <= self.expires_at

    @classmethod
    def create_for_email(
        cls,
        email: str,
        otp_hash: str,
        ttl_minutes: int = 10,
        purpose: str | None = None,
    ) -> "EmailOTP":
        return cls.objects.create(
            email=email,
            otp_hash=otp_hash,
            expires_at=timezone.now() + timedelta(minutes=ttl_minutes),
            purpose=purpose or cls.Purpose.SIGNUP,
        )


class Instrument(models.Model):
    class InstrumentCode(models.TextChoices):
        NIFTY = "NIFTY", "Nifty 50"
        BANKNIFTY = "BANKNIFTY", "Nifty Bank"
        SENSEX = "SENSEX", "Sensex"

    class Transaction(models.TextChoices):
        BUY = "BUY", "Buy"
        SELL = "SELL", "Sell"

    class StrikeSelection(models.TextChoices):
        STATIC = "static", "Static"
        ATM = "atm", "ATM (dynamic)"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="instruments",
    )
    instrument = models.CharField(
        max_length=16,
        choices=InstrumentCode.choices,
    )
    contract_expiry = models.DateField(null=True, blank=True)
    contract_expiry_code = models.CharField(max_length=16, blank=True, default="")
    transaction = models.CharField(
        max_length=4,
        choices=Transaction.choices,
        default=Transaction.BUY,
    )
    strike_selection = models.CharField(
        max_length=16,
        choices=StrikeSelection.choices,
        default=StrikeSelection.STATIC,
    )
    strike_step = models.PositiveIntegerField(default=50)
    ce_strike_offset = models.IntegerField(default=0)
    pe_strike_offset = models.IntegerField(default=0)
    trading_symbol = models.CharField(max_length=64, blank=True, default="")
    symbol_token = models.CharField(max_length=32, blank=True, default="")
    alternate_trading_symbol = models.CharField(max_length=64, blank=True, default="")
    alternate_symbol_token = models.CharField(max_length=32, blank=True, default="")
    exchange = models.CharField(max_length=16, blank=True, default="NFO")
    lot_size = models.PositiveIntegerField(default=0)
    no_of_lots = models.PositiveIntegerField(default=0)
    pl_exit_lots = models.PositiveIntegerField(default=0)
    premium_price = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    pl_points = models.IntegerField(default=0)
    sl_points = models.IntegerField(default=0)
    trailing_points = models.IntegerField(default=0)
    active = models.BooleanField(default=False)
    daily_selection_date = models.DateField(null=True, blank=True)
    daily_ce_symbol = models.CharField(max_length=64, blank=True, default="")
    daily_ce_token = models.CharField(max_length=32, blank=True, default="")
    daily_pe_symbol = models.CharField(max_length=64, blank=True, default="")
    daily_pe_token = models.CharField(max_length=32, blank=True, default="")
    daily_underlying_price = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    daily_ce_prev_high = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    daily_ce_prev_low = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    daily_pe_prev_high = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    daily_pe_prev_low = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    daily_levels_date = models.DateField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["instrument"]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "instrument"],
                name="unique_instrument_per_user",
            )
        ]

    def __str__(self) -> str:  # pragma: no cover - admin readability
        username = getattr(self.user, "username", "unknown")
        return (
            f"{self.get_instrument_display()}"
            f" for {username} ({self.contract_expiry_code or 'unset'})"
        )


class AlgoConfiguration(models.Model):
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="algo_configuration",
    )
    algo_active = models.BooleanField(default=False)
    market_active = models.BooleanField(default=False)
    market_active_updated_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Algo Configuration"
        verbose_name_plural = "Algo Configurations"

    def __str__(self) -> str:  # pragma: no cover - admin convenience
        return f"AlgoConfiguration<{self.user.username}>"


class StrategyActivation(models.Model):
    STRATEGY_ALPHA = "strategy_alpha"

    STRATEGY_CHOICES = [
        (STRATEGY_ALPHA, "Strategy Alpha"),
    ]

    class ExecutionMode(models.TextChoices):
        DEMO = "demo", "Demo"
        LIVE = "live", "Live"

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="strategy_activations",
    )
    strategy_code = models.CharField(max_length=64, choices=STRATEGY_CHOICES)
    is_active = models.BooleanField(default=False)
    activated_at = models.DateTimeField(null=True, blank=True)
    deactivated_at = models.DateTimeField(null=True, blank=True)
    execution_mode = models.CharField(
        max_length=8,
        choices=ExecutionMode.choices,
        default=ExecutionMode.DEMO,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    selected_instruments = models.ManyToManyField(
        "Instrument",
        through="StrategyActivationInstrument",
        related_name="strategy_activations",
        blank=True,
    )

    class Meta:
        unique_together = ("user", "strategy_code")
        verbose_name = "Strategy Activation"
        verbose_name_plural = "Strategy Activations"

    def __str__(self) -> str:  # pragma: no cover - admin convenience
        return f"{self.strategy_code} activation for {self.user.username}"


class StrategyActivationInstrument(models.Model):
    activation = models.ForeignKey(
        StrategyActivation,
        on_delete=models.CASCADE,
        related_name="instrument_links",
    )
    instrument = models.ForeignKey(
        Instrument,
        on_delete=models.CASCADE,
        related_name="activation_links",
    )
    added_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("activation", "instrument")
        verbose_name = "Strategy Activation Instrument"
        verbose_name_plural = "Strategy Activation Instruments"

    def clean(self) -> None:
        if self.activation.user_id != self.instrument.user_id:
            raise ValidationError("Instrument does not belong to this user.")

    def save(self, *args, **kwargs):
        self.clean()
        return super().save(*args, **kwargs)


class StrategyRunLog(models.Model):
    class Status(models.TextChoices):
        SUCCESS = "success", "Success"
        SKIPPED = "skipped", "Skipped"
        FAILED = "failed", "Failed"

    activation = models.ForeignKey(
        StrategyActivation,
        on_delete=models.CASCADE,
        related_name="run_logs",
    )
    execution_mode = models.CharField(
        max_length=8,
        choices=StrategyActivation.ExecutionMode.choices,
    )
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.SUCCESS,
    )
    message = models.TextField(blank=True)
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    extra = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-started_at"]

    def mark_completed(self, *, status: str | None = None, message: str | None = None, extra: dict | None = None) -> None:
        if status:
            self.status = status
        if message:
            self.message = message
        if extra:
            self.extra = extra
        self.completed_at = timezone.now()
        self.save(update_fields=["status", "message", "completed_at", "extra"])


class Trade(models.Model):
    class ExecutionMode(models.TextChoices):
        DEMO = "demo", "Demo"
        LIVE = "live", "Live"

    class Status(models.TextChoices):
        OPEN = "open", "Open"
        CLOSED = "closed", "Closed"
        CANCELLED = "cancelled", "Cancelled"
        ERROR = "error", "Error"

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="trades",
    )
    strategy_code = models.CharField(max_length=64)
    instrument = models.ForeignKey(
        Instrument,
        on_delete=models.CASCADE,
        related_name="trades",
    )
    execution_mode = models.CharField(
        max_length=8,
        choices=ExecutionMode.choices,
        default=ExecutionMode.DEMO,
    )
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.OPEN,
    )
    direction = models.CharField(
        max_length=4,
        choices=Instrument.Transaction.choices,
    )
    quantity = models.PositiveIntegerField(default=0)
    entry_price = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    exit_price = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    entry_datetime = models.DateTimeField(null=True, blank=True)
    exit_datetime = models.DateTimeField(null=True, blank=True)
    target_price = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    stop_loss_price = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    trailing_stop_price = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    last_price = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    pnl = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"))
    contract_symbol = models.CharField(max_length=64, blank=True, default="")
    contract_token = models.CharField(max_length=32, blank=True, default="")
    external_entry_id = models.CharField(max_length=64, blank=True)
    external_exit_id = models.CharField(max_length=64, blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-entry_datetime", "-created_at"]

    def get_realtime_pnl(self) -> Decimal:
        """Calculate P&L based on current last_price (real-time market data)."""
        if not self.entry_price or not self.quantity:
            return Decimal("0")
        
        current_price = self.last_price or self.entry_price
        if self.direction == "BUY":
            pnl = (current_price - self.entry_price) * self.quantity
        else:  # SELL
            pnl = (self.entry_price - current_price) * self.quantity
        
        return pnl.quantize(Decimal("0.01"), rounding=Decimal("ROUND_HALF_UP"))

    def __str__(self) -> str:  # pragma: no cover - display helper
        symbol = self.instrument.instrument if self.instrument_id else "unknown"
        return f"{self.strategy_code} {symbol} {self.execution_mode} ({self.status})"
