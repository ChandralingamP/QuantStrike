from django.contrib.auth import authenticate
from django.contrib.auth.hashers import check_password
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers

from django.utils import timezone

from .models import (
    AlgoConfiguration,
    EmailOTP,
    Instrument,
    Strategy,
    StrategyActivation,
    UserProfile,
)
from .models import Trade
from .services.instruments import initialize_user_instruments
from .utils.trade_costs import (
    calculate_margin_required,
    calculate_net_pnl,
    calculate_total_brokerage,
)
from .utils.instrument_data import parse_expiry_code


class StrategySerializer(serializers.ModelSerializer):
    class Meta:
        model = Strategy
        fields = [
            "id",
            "name",
            "symbol",
            "timeframe",
            "status",
            "notes",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

class OTPRequestSerializer(serializers.Serializer):
    email = serializers.EmailField()
    username = serializers.CharField(required=False, allow_blank=True)

    def validate_username(self, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            return ""
        if User.objects.filter(username__iexact=cleaned).exists():
            raise serializers.ValidationError("Username already exists.")
        return cleaned

class SignupSerializer(serializers.Serializer):
    username = serializers.CharField(max_length=150)
    user_id = serializers.CharField(max_length=64)
    api_key = serializers.CharField(max_length=128)
    mobile = serializers.CharField(max_length=16)
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)
    confirm_password = serializers.CharField(write_only=True)
    otp = serializers.CharField(write_only=True, max_length=6)

    def validate_username(self, value: str) -> str:
        if User.objects.filter(username__iexact=value).exists():
            raise serializers.ValidationError("Username already exists.")
        return value

    def validate_email(self, value: str) -> str:
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError("Email already registered.")
        return value

    def validate(self, attrs):
        if attrs["password"] != attrs["confirm_password"]:
            raise serializers.ValidationError("Passwords do not match.")

        validate_password(attrs["password"])

        email = attrs["email"]
        otp_value = attrs["otp"]

        otp_records = EmailOTP.objects.filter(
            email=email,
            purpose=EmailOTP.Purpose.SIGNUP,
            is_used=False,
        ).order_by("-created_at")
        if not otp_records.exists():
            raise serializers.ValidationError("No OTP found for this email. Request a new one.")

        otp_record = otp_records.first()
        if not otp_record.is_valid() or not check_password(otp_value, otp_record.otp_hash):
            raise serializers.ValidationError("Invalid or expired OTP.")

        attrs["_otp_record"] = otp_record
        return attrs

    def create(self, validated_data):
        otp_record = validated_data.pop("_otp_record")
        validated_data.pop("confirm_password")
        validated_data.pop("otp")

        user = User.objects.create_user(
            username=validated_data["username"],
            email=validated_data["email"],
            password=validated_data["password"],
        )
        UserProfile.objects.create(
            user=user,
            brokerage_user_id=validated_data["user_id"],
            api_key=validated_data["api_key"],
            mobile_number=validated_data["mobile"],
        )
        initialize_user_instruments(user)

        otp_record.mark_used()
        return user


class PasswordResetRequestSerializer(serializers.Serializer):
    email = serializers.EmailField()

    def validate_email(self, value: str) -> str:
        if not User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError("No account found for this email.")
        return value


class PasswordResetVerifySerializer(serializers.Serializer):
    email = serializers.EmailField()
    otp = serializers.CharField(max_length=6)

    def validate(self, attrs):
        email = attrs["email"]
        otp_value = attrs["otp"]
        otp_record = EmailOTP.objects.filter(
            email=email,
            purpose=EmailOTP.Purpose.PASSWORD_RESET,
            is_used=False,
        ).order_by("-created_at").first()

        if not otp_record or not otp_record.is_valid():
            raise serializers.ValidationError("Invalid or expired OTP.")

        if not check_password(otp_value, otp_record.otp_hash):
            raise serializers.ValidationError("Invalid or expired OTP.")

        attrs["_otp_record"] = otp_record
        return attrs


class PasswordResetSerializer(serializers.Serializer):
    email = serializers.EmailField()
    otp = serializers.CharField(max_length=6, write_only=True)
    password = serializers.CharField(write_only=True)
    confirm_password = serializers.CharField(write_only=True)

    def validate(self, attrs):
        if attrs["password"] != attrs["confirm_password"]:
            raise serializers.ValidationError("Passwords do not match.")

        validate_password(attrs["password"])

        try:
            user = User.objects.get(email__iexact=attrs["email"])
        except User.DoesNotExist as exc:
            raise serializers.ValidationError("No account found for this email.") from exc

        otp_record = EmailOTP.objects.filter(
            email=attrs["email"],
            purpose=EmailOTP.Purpose.PASSWORD_RESET,
            is_used=False,
        ).order_by("-created_at").first()

        if not otp_record or not otp_record.is_valid():
            raise serializers.ValidationError("Invalid or expired OTP.")

        if not check_password(attrs["otp"], otp_record.otp_hash):
            raise serializers.ValidationError("Invalid or expired OTP.")

        attrs["_otp_record"] = otp_record
        attrs["_user"] = user
        return attrs

    def create(self, validated_data):
        otp_record = validated_data.pop("_otp_record")
        user = validated_data.pop("_user")
        validated_data.pop("confirm_password", None)
        validated_data.pop("otp", None)

        user.set_password(validated_data["password"])
        user.save(update_fields=["password"])
        otp_record.mark_used()
        return user

class LoginSerializer(serializers.Serializer):
    username = serializers.CharField()
    password = serializers.CharField(write_only=True)

    def validate(self, attrs):
        username = attrs.get("username")
        password = attrs.get("password")
        user = authenticate(username=username, password=password)
        if not user:
            raise serializers.ValidationError("Invalid credentials.")
        if not user.is_active:
            raise serializers.ValidationError("Account is disabled.")
        attrs["user"] = user
        return attrs


class AdminAccessSerializer(serializers.Serializer):
    admin_username = serializers.CharField()

    def validate(self, attrs):
        username = attrs["admin_username"]
        try:
            admin_user = User.objects.get(username__iexact=username)
        except User.DoesNotExist as exc:
            raise serializers.ValidationError(
                {"admin_username": "Admin user not found."}
            ) from exc
        if not admin_user.is_staff:
            raise serializers.ValidationError(
                {"admin_username": "Admin privileges required."}
            )
        attrs["_admin_user"] = admin_user
        return attrs


class AdminUserToggleSerializer(serializers.Serializer):
    admin_username = serializers.CharField()
    username = serializers.CharField()
    is_superuser = serializers.BooleanField()

    def validate(self, attrs):
        username = attrs["username"]
        admin_serializer = AdminAccessSerializer(
            data={"admin_username": attrs["admin_username"]}
        )
        admin_serializer.is_valid(raise_exception=True)
        attrs["_admin_user"] = admin_serializer.validated_data["_admin_user"]

        try:
            target_user = User.objects.get(username__iexact=username)
        except User.DoesNotExist as exc:
            raise serializers.ValidationError(
                {"username": "User not found."}
            ) from exc

        attrs["_target_user"] = target_user
        return attrs

    def save(self, **kwargs):
        target_user = self.validated_data["_target_user"]
        target_user.is_superuser = self.validated_data["is_superuser"]
        target_user.save(update_fields=["is_superuser"])
        return target_user


class AdminUserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["id", "username", "email", "is_superuser", "is_staff"]


class InstrumentSerializer(serializers.ModelSerializer):
    index_scrip = serializers.SerializerMethodField()
    available_expiries = serializers.SerializerMethodField()
    username = serializers.CharField(source="user.username", read_only=True)
    contract_expiry = serializers.CharField(
        source="contract_expiry_code",
        allow_blank=True,
        required=False,
    )
    contract_expiry_date = serializers.SerializerMethodField()

    class Meta:
        model = Instrument
        fields = [
            "id",
            "username",
            "instrument",
            "index_scrip",
            "contract_expiry",
            "contract_expiry_date",
            "available_expiries",
            "transaction",
            "strike_selection",
            "strike_step",
            "ce_strike_offset",
            "pe_strike_offset",
            "trading_symbol",
            "symbol_token",
            "alternate_trading_symbol",
            "alternate_symbol_token",
            "exchange",
            "lot_size",
            "no_of_lots",
            "pl_exit_lots",
            "premium_price",
            "pl_points",
            "sl_points",
            "trailing_points",
            "active",
            "daily_selection_date",
            "daily_ce_symbol",
            "daily_ce_token",
            "daily_pe_symbol",
            "daily_pe_token",
            "daily_underlying_price",
            "daily_ce_prev_high",
            "daily_ce_prev_low",
            "daily_pe_prev_high",
            "daily_pe_prev_low",
            "daily_levels_date",
        ]
        read_only_fields = [
            "instrument",
            "username",
            "daily_selection_date",
            "daily_ce_symbol",
            "daily_ce_token",
            "daily_pe_symbol",
            "daily_pe_token",
            "daily_underlying_price",
            "daily_ce_prev_high",
            "daily_ce_prev_low",
            "daily_pe_prev_high",
            "daily_pe_prev_low",
            "daily_levels_date",
        ]

    def get_index_scrip(self, obj: Instrument) -> str:
        return obj.get_instrument_display()

    def get_available_expiries(self, obj: Instrument) -> list[str]:
        expiry_map = self.context.get("expiry_map") or {}
        return expiry_map.get(obj.instrument.upper(), [])

    def get_contract_expiry_date(self, obj: Instrument) -> str | None:
        return obj.contract_expiry.isoformat() if obj.contract_expiry else None

    def validate(self, attrs):
        data = super().validate(attrs)
        expiry_code = data.get("contract_expiry_code")
        if expiry_code:
            expiry = parse_expiry_code(expiry_code)
            if not expiry:
                raise serializers.ValidationError(
                    {"contract_expiry": "Invalid expiry format. Use DDMMMYYYY."}
                )
            instrument_code = (
                self.instance.instrument
                if self.instance is not None
                else (self.initial_data.get("instrument") or "")
            )
            expiry_map = self.context.get("expiry_map") or {}
            allowed_values = {value.upper() for value in expiry_map.get(instrument_code.upper(), [])}
            if allowed_values and expiry_code.upper() not in allowed_values:
                raise serializers.ValidationError(
                    {"contract_expiry": "Expiry is not available for this instrument."}
                )
            data["_parsed_expiry"] = expiry

        lot_size = data.get("lot_size")
        if lot_size is not None and lot_size < 0:
            raise serializers.ValidationError(
                {"lot_size": "Lot size must be zero or a positive integer."}
            )

        strike_step = data.get("strike_step")
        if strike_step is not None and strike_step <= 0:
            raise serializers.ValidationError(
                {"strike_step": "Strike step must be a positive integer."}
            )

        return data

    def update(self, instance: Instrument, validated_data: dict) -> Instrument:
        parsed_expiry = validated_data.pop("_parsed_expiry", None)
        expiry_code = validated_data.pop("contract_expiry_code", None)

        for field, value in validated_data.items():
            setattr(instance, field, value)

        if expiry_code is not None:
            instance.contract_expiry_code = expiry_code
            instance.contract_expiry = parsed_expiry

        instance.save()
        return instance


class AdminUserDeleteSerializer(serializers.Serializer):
    admin_username = serializers.CharField()
    username = serializers.CharField()

    def validate(self, attrs):
        admin_serializer = AdminAccessSerializer(
            data={"admin_username": attrs["admin_username"]}
        )
        admin_serializer.is_valid(raise_exception=True)
        admin_user = admin_serializer.validated_data["_admin_user"]

        try:
            target_user = User.objects.get(username__iexact=attrs["username"])
        except User.DoesNotExist as exc:
            raise serializers.ValidationError({"username": "User not found."}) from exc

        if target_user.pk == admin_user.pk:
            raise serializers.ValidationError(
                {"username": "Admins cannot delete their own account."}
            )

        attrs["_admin_user"] = admin_user
        attrs["_target_user"] = target_user
        return attrs

    def save(self, **kwargs):
        target_user = self.validated_data["_target_user"]
        deleted_username = target_user.username
        target_user.delete()
        return deleted_username


class TradeSerializer(serializers.ModelSerializer):
    instrument_symbol = serializers.CharField(source="instrument.instrument", read_only=True)
    instrument_label = serializers.SerializerMethodField()
    instrument_trading_symbol = serializers.CharField(
        source="instrument.trading_symbol",
        read_only=True,
    )
    contract_symbol = serializers.CharField(read_only=True)
    contract_token = serializers.CharField(read_only=True)
    direction_display = serializers.CharField(source="get_direction_display", read_only=True)
    execution_mode_display = serializers.CharField(source="get_execution_mode_display", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    margin_required = serializers.SerializerMethodField()
    brokerage = serializers.SerializerMethodField()
    net_pnl = serializers.SerializerMethodField()

    class Meta:
        model = Trade
        fields = [
            "id",
            "strategy_code",
            "instrument_symbol",
            "instrument_label",
             "instrument_trading_symbol",
            "contract_symbol",
            "contract_token",
            "execution_mode",
            "execution_mode_display",
            "status",
            "status_display",
            "direction",
            "direction_display",
            "quantity",
            "entry_price",
            "exit_price",
            "entry_datetime",
            "exit_datetime",
            "target_price",
            "stop_loss_price",
            "trailing_stop_price",
            "pnl",
            "margin_required",
            "brokerage",
            "net_pnl",
            "external_entry_id",
            "external_exit_id",
            "notes",
        ]
        read_only_fields = fields

    def get_instrument_label(self, instance: Trade) -> str:
        if not instance.instrument_id:
            return ""
        return instance.instrument.get_instrument_display()

    def get_margin_required(self, instance: Trade) -> str:
        return str(calculate_margin_required(instance))

    def get_brokerage(self, instance: Trade) -> str:
        return str(calculate_total_brokerage(instance))

    def get_net_pnl(self, instance: Trade) -> str:
        return str(calculate_net_pnl(instance))


class AlgoConfigurationSerializer(serializers.ModelSerializer):
    strategy_alpha = serializers.SerializerMethodField(read_only=True)
    strategy_alpha_active = serializers.BooleanField(write_only=True, required=False)
    strategy_alpha_instrument_ids = serializers.ListField(
        child=serializers.IntegerField(min_value=1), write_only=True, required=False
    )

    strategy_alpha_mode = serializers.ChoiceField(
        choices=StrategyActivation.ExecutionMode.choices,
        write_only=True,
        required=False,
    )
    username = serializers.CharField(write_only=True, required=False, allow_blank=True)

    class Meta:
        model = AlgoConfiguration
        fields = [
            "algo_active",
            "market_active",
            "market_active_updated_at",
            "created_at",
            "updated_at",
            "strategy_alpha",
            "strategy_alpha_active",
            "strategy_alpha_instrument_ids",
            "strategy_alpha_mode",
            "username",
        ]
        read_only_fields = [
            "market_active_updated_at",
            "created_at",
            "updated_at",
            "strategy_alpha",
        ]

    def get_strategy_alpha(self, instance: AlgoConfiguration) -> dict:
        activation: StrategyActivation = self.context["activation"]
        user = self.context["user"]
        instrument_qs = self.context.get("instrument_qs")
        if instrument_qs is None:
            instrument_qs = Instrument.objects.filter(user=user).order_by("instrument")

        selected_ids = list(
            activation.selected_instruments.values_list("id", flat=True)
        )

        options: list[dict] = []
        for instrument in instrument_qs:
            options.append(
                {
                    "id": instrument.id,
                    "label": instrument.get_instrument_display(),
                    "instrument": instrument.instrument,
                    "expiry": instrument.contract_expiry_code or "",
                    "active": instrument.active,
                    "transaction": instrument.transaction,
                    "lots": instrument.no_of_lots,
                    "trading_symbol": instrument.trading_symbol,
                    "symbol_token": instrument.symbol_token,
                    "exchange": instrument.exchange,
                    "lot_size": instrument.lot_size,
                }
            )

        return {
            "active": activation.is_active,
            "mode": activation.execution_mode,
            "selected_instrument_ids": selected_ids,
            "instrument_options": options,
            "activated_at": activation.activated_at.isoformat()
            if activation.activated_at
            else None,
            "deactivated_at": activation.deactivated_at.isoformat()
            if activation.deactivated_at
            else None,
        }

    def validate(self, attrs):
        attrs = super().validate(attrs)
        user = self.context["user"]
        activation: StrategyActivation = self.context["activation"]

        attrs.pop("username", None)

        instrument_ids = attrs.get("strategy_alpha_instrument_ids")
        if instrument_ids is not None:
            deduped_ids: list[int] = []
            for instrument_id in instrument_ids:
                if instrument_id not in deduped_ids:
                    deduped_ids.append(instrument_id)
            instruments = list(
                Instrument.objects.filter(user=user, id__in=deduped_ids)
            )
            if len(instruments) != len(deduped_ids):
                raise serializers.ValidationError(
                    {
                        "strategy_alpha_instrument_ids": "One or more instruments are invalid or unavailable for this user.",
                    }
                )
            attrs["_strategy_alpha_instruments"] = instruments
            attrs["strategy_alpha_instrument_ids"] = deduped_ids

        active_flag = attrs.get("strategy_alpha_active")
        if active_flag is None:
            active_flag = activation.is_active

        if active_flag:
            new_selection = attrs.get("_strategy_alpha_instruments")
            if new_selection is not None:
                has_selection = len(new_selection) > 0
            else:
                has_selection = activation.selected_instruments.exists()
            if not has_selection:
                raise serializers.ValidationError(
                    {
                        "strategy_alpha_instrument_ids": "Select at least one instrument to enable the strategy.",
                    }
                )

        requested_mode = attrs.get("strategy_alpha_mode")
        if requested_mode:
            if (
                requested_mode == StrategyActivation.ExecutionMode.LIVE
                and not user.is_staff
                and not user.is_superuser
            ):
                raise serializers.ValidationError(
                    {
                        "strategy_alpha_mode": "Live mode is restricted to staff or superusers.",
                    }
                )

        return attrs

    def update(self, instance: AlgoConfiguration, validated_data):
        activation: StrategyActivation = self.context["activation"]

        strategy_instruments = validated_data.pop("_strategy_alpha_instruments", None)
        strategy_active = validated_data.pop("strategy_alpha_active", None)
        validated_data.pop("strategy_alpha_instrument_ids", None)
        strategy_mode = validated_data.pop("strategy_alpha_mode", None)

        update_fields: list[str] = []
        config_saved = False

        algo_active = validated_data.get("algo_active")
        if algo_active is not None and algo_active != instance.algo_active:
            instance.algo_active = algo_active
            update_fields.append("algo_active")

        market_active = validated_data.get("market_active")
        if market_active is not None and market_active != instance.market_active:
            instance.market_active = market_active
            instance.market_active_updated_at = timezone.now()
            update_fields.extend(["market_active", "market_active_updated_at"])

        if update_fields:
            update_fields.append("updated_at")
            instance.save(update_fields=update_fields)
            config_saved = True

        activation_modified = False
        if strategy_active is not None:
            if strategy_active and not activation.is_active:
                activation.activated_at = timezone.now()
                activation.deactivated_at = None
                activation_modified = True
            elif not strategy_active and activation.is_active:
                activation.deactivated_at = timezone.now()
                activation_modified = True
            activation.is_active = strategy_active
            activation_modified = True

        if strategy_instruments is not None:
            activation.selected_instruments.set(strategy_instruments)
            activation_modified = True

        if strategy_mode is not None and strategy_mode != activation.execution_mode:
            activation.execution_mode = strategy_mode
            activation_modified = True

        if activation_modified:
            activation.save()
            if not config_saved:
                instance.save(update_fields=["updated_at"])
                config_saved = True

        instance.refresh_from_db()
        activation.refresh_from_db()
        self.context["activation"] = activation
        return instance
