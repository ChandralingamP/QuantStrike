"""Execution engine for Strategy Alpha."""
from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, Optional, Tuple
from uuid import uuid4

from django.contrib.auth.models import User
from django.db import transaction
from django.utils import timezone

from ..angel import AngelAPIError, place_order
from ..models import (
    AlgoConfiguration,
    Instrument,
    StrategyActivation,
    StrategyRunLog,
    Trade,
)
from ..models import UserProfile
from ..utils.contract_lookup import ContractLookupError, find_contract, lookup_contract
from ..utils.instrument_data import parse_expiry_code
from .market_data import (
    BaseMarketDataProvider,
    EntrySnapshot,
    MarketDataError,
    build_market_data_provider,
)
from .smartapi_market import Candle, SmartAPIMarketClient, SmartAPIMarketError

logger = logging.getLogger(__name__)


class StrategySkip(Exception):
    """Raised when a strategy run is intentionally skipped."""


def _as_decimal(value: Decimal | float | int | None) -> Decimal:
    if value is None:
        return Decimal("0")
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def _quantize(value: Decimal | float | int | None) -> Decimal:
    return _as_decimal(value).quantize(Decimal("0.05"), rounding=ROUND_HALF_UP)


@dataclass
class InstrumentSummary:
    instrument: str
    opened: int = 0
    closed: int = 0
    price: Optional[Decimal] = None
    message: Optional[str] = None
    pnl: Decimal = Decimal("0")

    def as_dict(self) -> Dict[str, object]:
        payload: Dict[str, object] = {
            "instrument": self.instrument,
            "opened": self.opened,
            "closed": self.closed,
        }
        if self.price is not None:
            payload["price"] = str(self.price)
        if self.message:
            payload["message"] = self.message
        if self.pnl:
            payload["pnl"] = str(self.pnl)
        return payload


@dataclass(frozen=True)
class ContractSpec:
    symbol: str
    token: str
    option_type: str
    strike: int
    label: str = "primary"


@dataclass
class EntryPlan:
    should_enter: bool
    entry_price: Optional[Decimal] = None
    stop_loss: Optional[Decimal] = None
    message: Optional[str] = None
    entry_time: Optional[datetime] = None
    reference_high: Optional[Decimal] = None
    reference_low: Optional[Decimal] = None


class OrderExecutor:
    """Handles demo and live order placement for Strategy Alpha."""

    def __init__(
        self,
        *,
        profile: Optional[UserProfile],
        execution_mode: str,
        logger: logging.Logger,
    ) -> None:
        self.profile = profile
        self.execution_mode = execution_mode
        self.logger = logger.getChild("OrderExecutor")

    @property
    def is_live(self) -> bool:
        return self.execution_mode == Trade.ExecutionMode.LIVE

    def _ensure_live_ready(self) -> None:
        if not self.is_live:
            return
        if not self.profile:
            raise StrategySkip("Brokerage profile missing; reconnect before live execution.")
        if not self.profile.api_key:
            raise StrategySkip("Brokerage API key missing for live execution.")
        if not self.profile.jwt_token:
            raise StrategySkip("Brokerage session expired; reconnect the brokerage account.")

    def _validate_instrument(self, instrument: Instrument) -> None:
        if not instrument.trading_symbol or not instrument.symbol_token:
            raise StrategySkip(
                (
                    f"Instrument {instrument.instrument} is missing trading symbol or token. "
                    "Update instrument settings before enabling live trading."
                )
            )
        if not instrument.lot_size:
            raise StrategySkip(
                (
                    f"Instrument {instrument.instrument} requires a lot size for live execution. "
                    "Update instrument settings with the correct lot size."
                )
            )

    def place_entry_order(
        self,
        *,
        instrument: Instrument,
        direction: str,
        quantity: int,
        reference_price: Decimal,
        contract_symbol: Optional[str] = None,
        contract_token: Optional[str] = None,
        target_price: Optional[Decimal] = None,
        stop_loss_price: Optional[Decimal] = None,
    ) -> Dict[str, object]:
        if not self.is_live:
            return {
                "order_id": f"demo-entry-{uuid4().hex}",
                "average_price": reference_price,
                "filled_quantity": quantity,
            }

        symbol = contract_symbol or instrument.trading_symbol
        token = contract_token or instrument.symbol_token
        if not symbol or not token:
            raise StrategySkip(
                "Trading symbol or token missing for live execution; update instrument details."
            )

        self._ensure_live_ready()
        if not contract_symbol and not contract_token:
            self._validate_instrument(instrument)

        # Calculate squareoff and stoploss from entry price if provided
        # For BUY: squareoff = target - entry, stoploss = entry - stop_loss
        # For SELL: squareoff = entry - target, stoploss = stop_loss - entry
        squareoff_value = "0"
        stoploss_value = "0"
        
        if target_price and direction == Instrument.Transaction.BUY:
            # BUY: profit when price goes up
            squareoff_value = str(float(target_price - reference_price))
        elif target_price and direction == Instrument.Transaction.SELL:
            # SELL: profit when price goes down
            squareoff_value = str(float(reference_price - target_price))
            
        if stop_loss_price and direction == Instrument.Transaction.BUY:
            # BUY: loss when price goes down
            stoploss_value = str(float(reference_price - stop_loss_price))
        elif stop_loss_price and direction == Instrument.Transaction.SELL:
            # SELL: loss when price goes up
            stoploss_value = str(float(stop_loss_price - reference_price))

        payload = {
            "variety": "NORMAL",
            "tradingsymbol": symbol,
            "symboltoken": token,
            "transactiontype": direction,
            "exchange": instrument.exchange or "NFO",
            "ordertype": "MARKET",
            "producttype": "INTRADAY",
            "duration": "DAY",
            "price": "0",
            "squareoff": squareoff_value,
            "stoploss": stoploss_value,
            "trailstoploss": "0",
            "quantity": str(max(quantity, 1)),
        }

        return self._submit_order(payload, reference_price, tag="ENTRY")

    def place_exit_order(
        self,
        *,
        instrument: Instrument,
        trade: Trade,
        reference_price: Decimal,
    ) -> Dict[str, object]:
        if not self.is_live:
            return {
                "order_id": f"demo-exit-{uuid4().hex}",
                "average_price": reference_price,
                "filled_quantity": trade.quantity or 0,
            }

        symbol = trade.contract_symbol or instrument.trading_symbol
        token = trade.contract_token or instrument.symbol_token
        if not symbol or not token:
            raise StrategySkip(
                "Trading symbol or token missing for exit; ensure contract metadata is configured."
            )

        self._ensure_live_ready()
        if not trade.contract_symbol and not trade.contract_token:
            self._validate_instrument(instrument)

        exit_direction = (
            Instrument.Transaction.SELL
            if trade.direction == Instrument.Transaction.BUY
            else Instrument.Transaction.BUY
        )

        payload = {
            "variety": "NORMAL",
            "tradingsymbol": symbol,
            "symboltoken": token,
            "transactiontype": exit_direction,
            "exchange": instrument.exchange or "NFO",
            "ordertype": "MARKET",
            "producttype": "INTRADAY",
            "duration": "DAY",
            "price": "0",
            "squareoff": "0",
            "stoploss": "0",
            "trailstoploss": "0",
            "quantity": str(max(trade.quantity or 0, 1)),
        }

        return self._submit_order(payload, reference_price, tag="EXIT")

    def _submit_order(
        self,
        payload: Dict[str, object],
        reference_price: Decimal,
        *,
        tag: str,
    ) -> Dict[str, object]:
        assert self.profile is not None  # for type checkers
        try:
            response = place_order(
                api_key=self.profile.api_key,
                jwt_token=self.profile.jwt_token,
                payload=payload,
            )
        except AngelAPIError as exc:  # pragma: no cover - network failure guard
            self.logger.warning("%s order failed: %s", tag, exc)
            raise StrategySkip(f"{tag.title()} order failed: {exc}") from exc

        data = response.get("data") or {}
        order_id = data.get("orderid") or data.get("order_id") or ""
        filled_quantity_raw = data.get("filledShares") or data.get("filledqty")
        try:
            filled_quantity = int(filled_quantity_raw) if filled_quantity_raw is not None else int(payload["quantity"])
        except (ValueError, TypeError):
            filled_quantity = int(payload.get("quantity", "0") or 0)

        result = {
            "order_id": order_id,
            "average_price": reference_price,
            "filled_quantity": max(filled_quantity, 0),
        }

        message = response.get("message")
        if message:
            self.logger.info("%s order acknowledged: %s", tag, message)

        return result


class StrategyAlphaEngine:
    """Coordinates execution of Strategy Alpha in demo or live mode."""

    STRATEGY_CODE = StrategyActivation.STRATEGY_ALPHA

    def __init__(
        self,
        *,
        user: User,
        execution_mode: Optional[str] = None,
        market_data_provider: Optional[BaseMarketDataProvider] = None,
        market_date: Optional[date] = None,
        logger: Optional[logging.Logger] = None,
        ignore_activation: bool = False,
        instrument_ids: Optional[list[int]] = None,
    ) -> None:
        self.user = user
        self._execution_mode = execution_mode
        self._market_data_provider = market_data_provider
        self.market_date = market_date
        self.ignore_activation = ignore_activation
        self.instrument_ids = instrument_ids or []
        
        # Use provided logger or create default one
        if logger:
            self.logger = logger
        else:
            default_logger = logging.getLogger(__name__)
            self.logger = default_logger.getChild(f"StrategyAlpha[{user.username}]")
        
        self._profile: Optional[UserProfile] = None
        self.market_client: Optional[SmartAPIMarketClient] = None
        self._intraday_cache: Dict[str, list[Candle]] = {}

    def run(self) -> Dict[str, object]:
        algo_config, _ = AlgoConfiguration.objects.get_or_create(user=self.user)
        activation, _ = StrategyActivation.objects.get_or_create(
            user=self.user,
            strategy_code=self.STRATEGY_CODE,
        )

        execution_mode = self._execution_mode or activation.execution_mode
        run_log = StrategyRunLog.objects.create(
            activation=activation,
            execution_mode=execution_mode,
            status=StrategyRunLog.Status.SUCCESS,
        )

        try:
            summary = self._execute(algo_config, activation, execution_mode)
        except StrategySkip as exc:
            message = str(exc)
            run_log.mark_completed(
                status=StrategyRunLog.Status.SKIPPED,
                message=message,
                extra={"mode": execution_mode},
            )
            return {
                "status": "skipped",
                "mode": execution_mode,
                "message": message,
            }
        except Exception as exc:  # pragma: no cover - defensive guard
            self.logger.exception("Strategy Alpha run failed: %s", exc)
            run_log.mark_completed(
                status=StrategyRunLog.Status.FAILED,
                message=str(exc),
                extra={"mode": execution_mode},
            )
            raise

        run_log.mark_completed(extra=summary)
        return summary

    def run_backtest(self) -> Dict[str, object]:
        """Run strategy and simulate trade monitoring using historical candles.

        Unlike ``run()`` which only opens trades (monitor closes them),
        this method walks through all remaining candles after entry to
        simulate SL / target / trailing / EOD exits in a single pass.
        """
        algo_config, _ = AlgoConfiguration.objects.get_or_create(user=self.user)
        activation, _ = StrategyActivation.objects.get_or_create(
            user=self.user,
            strategy_code=self.STRATEGY_CODE,
        )

        execution_mode = self._execution_mode or activation.execution_mode

        try:
            summary = self._execute_backtest(algo_config, activation, execution_mode)
        except StrategySkip as exc:
            return {
                "status": "skipped",
                "mode": execution_mode,
                "message": str(exc),
            }
        except Exception as exc:
            self.logger.exception("Backtest run failed: %s", exc)
            raise

        return summary

    def _execute_backtest(
        self,
        config: AlgoConfiguration,
        activation: StrategyActivation,
        execution_mode: str,
    ) -> Dict[str, object]:
        """Backtest variant of _execute that simulates full trade lifecycle."""
        if not config.algo_active and not self.ignore_activation:
            raise StrategySkip("Algo is currently disabled.")
        if not activation.is_active and not self.ignore_activation:
            raise StrategySkip("Strategy Alpha is not active for this user.")

        instruments = list(
            activation.selected_instruments.filter(active=True).order_by("instrument")
        )
        if self.instrument_ids:
            instruments = [i for i in instruments if i.id in self.instrument_ids]
        if not instruments:
            raise StrategySkip("No active instruments assigned to Strategy Alpha.")

        profile = self._resolve_profile()
        self._profile = profile
        self.market_client = self._build_market_client(profile)

        provider = self._market_data_provider or build_market_data_provider(
            profile=profile,
            execution_mode=execution_mode,
            seed=int(timezone.now().timestamp()),
            market_date=self.market_date,
        )

        if hasattr(provider, "prefetch_underlying_prices") and self.market_client:
            provider.prefetch_underlying_prices(instruments, self.market_client)

        # Delete any existing backtest trades for this user/date/mode to avoid duplicates
        if self.market_date:
            deleted_count, _ = Trade.objects.filter(
                user=self.user,
                strategy_code=self.STRATEGY_CODE,
                execution_mode=execution_mode,
                notes__startswith="Backtest:",
                entry_datetime__date=self.market_date,
            ).delete()
            if deleted_count:
                self.logger.info(f"Cleared {deleted_count} existing backtest trade(s) for {self.market_date}")

        summary = {
            "status": "completed",
            "mode": execution_mode,
            "opened_trades": 0,
            "closed_trades": 0,
            "net_pnl": Decimal("0"),
            "instrument_summaries": [],
            "trades": [],
        }

        import time as _time
        for idx, instrument in enumerate(instruments):
            if idx > 0:
                _time.sleep(2)
            for attempt in range(1, 4):
                try:
                    inst_summary, trade_details = self._backtest_instrument(
                        instrument=instrument,
                        provider=provider,
                        execution_mode=execution_mode,
                    )
                    summary["opened_trades"] += inst_summary.opened
                    summary["closed_trades"] += inst_summary.closed
                    summary["net_pnl"] += inst_summary.pnl
                    summary["instrument_summaries"].append(inst_summary.as_dict())
                    summary["trades"].extend(trade_details)
                    break
                except Exception as exc:
                    exc_msg = str(exc).lower()
                    is_retryable = (
                        "too many" in exc_msg
                        or "try after" in exc_msg
                        or "broken pipe" in exc_msg
                        or "connection reset" in exc_msg
                        or "connection aborted" in exc_msg
                    )
                    if is_retryable and attempt < 3:
                        wait = 3 * attempt
                        self.logger.warning(
                            f"Retryable error on {instrument.instrument}, retry {attempt}/3 after {wait}s: {exc}"
                        )
                        _time.sleep(wait)
                        continue
                    self.logger.error(f"Failed to process {instrument.instrument}: {exc}")
                    summary["instrument_summaries"].append({
                        "instrument": instrument.instrument,
                        "opened": 0,
                        "closed": 0,
                        "message": f"Error: {str(exc)}",
                    })
                    break

        summary["net_pnl"] = str(summary["net_pnl"])
        return summary

    def _backtest_instrument(
        self,
        *,
        instrument: Instrument,
        provider: BaseMarketDataProvider,
        execution_mode: str,
    ) -> tuple[InstrumentSummary, list[dict]]:
        """Process one instrument for backtest: detect entry, then simulate exit."""
        summary = InstrumentSummary(instrument=instrument.instrument)
        trade_details: list[dict] = []
        self.logger.info(f"═══ [BACKTEST] Processing {instrument.instrument} ═══")

        market_day = self._current_market_day()

        # For backtesting, fetch the underlying index price from historical candles
        # instead of relying on HistoricalMarketDataProvider which may fail for
        # expired contracts.
        underlying_price = self._get_backtest_underlying_price(instrument, market_day)
        if underlying_price is None:
            try:
                snapshot = self._get_entry_snapshot(provider, instrument)
                underlying_price = snapshot.underlying_price or snapshot.price
            except MarketDataError as exc:
                summary.message = f"Market data unavailable: {exc}"
                return summary, trade_details

        snapshot = EntrySnapshot(
            price=underlying_price,
            underlying_price=underlying_price,
        )
        summary.price = underlying_price

        contracts = self._contract_specs(instrument, snapshot, provider)

        for contract in contracts:
            self.logger.info(f"--- [BACKTEST] Contract: {contract.symbol} ({contract.option_type}) ---")

            # Fetch ALL candles for the day in one go (already cached by _get_intraday_candles)
            all_candles = self._get_intraday_candles(instrument, contract, market_day)
            if len(all_candles) < 2:
                summary.message = f"Not enough candles ({len(all_candles)})"
                continue

            # Get previous session levels
            prev_levels = self._ensure_previous_session_levels(instrument, contract, market_day)
            if not prev_levels:
                summary.message = "previous_levels_unavailable"
                continue

            reference_high, reference_low = prev_levels

            # Walk candles to find breakout entry
            entry_candle_idx, entry_price, stop_loss = self._find_breakout_entry(
                all_candles, reference_high, reference_low, instrument,
            )

            if entry_candle_idx is None:
                summary.message = "no_breakout"
                continue

            # Compute trade parameters
            direction = instrument.transaction or Instrument.Transaction.BUY
            lots = max(instrument.no_of_lots or 0, 1)
            lot_size = instrument.lot_size or 1
            quantity = max(lots * lot_size, 1)
            pl_points = _as_decimal(instrument.pl_points)
            sl_points = _as_decimal(instrument.sl_points)
            trailing_points = _as_decimal(instrument.trailing_points)
            price = _quantize(entry_price)

            if direction == Instrument.Transaction.BUY:
                target_price = _quantize(price + pl_points) if pl_points else None
                max_sl_price = _quantize(price - sl_points) if sl_points else None
                stop_price = _quantize(stop_loss) if stop_loss is not None else max_sl_price
                if max_sl_price is not None and stop_price is not None and stop_price < max_sl_price:
                    stop_price = max_sl_price
                trailing_price = _quantize(price - trailing_points) if trailing_points else stop_price
            else:
                target_price = _quantize(price - pl_points) if pl_points else None
                max_sl_price = _quantize(price + sl_points) if sl_points else None
                stop_price = _quantize(stop_loss) if stop_loss is not None else max_sl_price
                if max_sl_price is not None and stop_price is not None and stop_price > max_sl_price:
                    stop_price = max_sl_price
                trailing_price = _quantize(price + trailing_points) if trailing_points else stop_price

            entry_time = all_candles[entry_candle_idx].timestamp

            self.logger.info(
                f"BACKTEST ENTRY: {contract.symbol} @ {price}, "
                f"SL={stop_price}, TP={target_price}, Trail={trailing_price}"
            )

            # Simulate monitoring through remaining candles
            exit_price, exit_reason, exit_time = self._simulate_candle_monitoring(
                candles=all_candles[entry_candle_idx:],
                entry_price=price,
                target_price=target_price,
                stop_price=stop_price,
                trailing_price=trailing_price,
                trailing_points=trailing_points,
                direction=direction,
                market_day=market_day,
            )

            pnl = self._compute_backtest_pnl(
                entry_price=price,
                exit_price=exit_price,
                quantity=quantity,
                direction=direction,
            )

            self.logger.info(
                f"BACKTEST EXIT: {contract.symbol} @ {exit_price} ({exit_reason}), PnL={pnl}"
            )

            # Create actual Trade record for persistence
            entry_ts = entry_time
            if timezone.is_naive(entry_ts):
                entry_ts = timezone.make_aware(entry_ts, timezone.get_current_timezone())
            exit_ts = exit_time
            if exit_ts and timezone.is_naive(exit_ts):
                exit_ts = timezone.make_aware(exit_ts, timezone.get_current_timezone())

            trade = Trade.objects.create(
                user=self.user,
                strategy_code=self.STRATEGY_CODE,
                instrument=instrument,
                execution_mode=execution_mode,
                status=Trade.Status.CLOSED,
                direction=direction,
                quantity=quantity,
                entry_price=price,
                entry_datetime=entry_ts,
                exit_price=exit_price,
                exit_datetime=exit_ts,
                target_price=target_price,
                stop_loss_price=stop_price,
                trailing_stop_price=trailing_price,
                last_price=exit_price,
                pnl=pnl,
                notes=f"Backtest: closed on {exit_reason} at {exit_price}",
                contract_symbol=contract.symbol,
                contract_token=contract.token,
            )

            summary.opened += 1
            summary.closed += 1
            summary.pnl += pnl

            trade_details.append({
                "trade_id": trade.id,
                "instrument": instrument.instrument,
                "contract": contract.symbol,
                "option_type": contract.option_type,
                "direction": direction,
                "entry_price": str(price),
                "entry_time": str(entry_ts),
                "exit_price": str(exit_price),
                "exit_time": str(exit_ts),
                "exit_reason": exit_reason,
                "target": str(target_price) if target_price else None,
                "stop_loss": str(stop_price) if stop_price else None,
                "pnl": str(pnl),
                "quantity": quantity,
            })

        return summary, trade_details

    def _find_breakout_entry(
        self,
        candles: list[Candle],
        reference_high: Decimal,
        reference_low: Decimal,
        instrument: Instrument,
    ) -> tuple[Optional[int], Optional[Decimal], Optional[Decimal]]:
        """Walk candles to find the first breakout entry point.

        Returns (entry_candle_index, entry_price, stop_loss) or (None, None, None).
        """
        current_high = reference_high
        current_low = reference_low

        for index, candle in enumerate(candles[:-1]):
            if candle.close <= current_high:
                continue

            is_first = index == 0
            if is_first and candle.open > current_high:
                # Gap-up on first candle — skip, update levels
                current_high = candle.high
                current_low = candle.low
                continue

            # Breakout confirmed — enter on next candle's open
            next_candle = candles[index + 1]
            return index + 1, next_candle.open, current_low

        return None, None, None

    def _simulate_candle_monitoring(
        self,
        *,
        candles: list[Candle],
        entry_price: Decimal,
        target_price: Optional[Decimal],
        stop_price: Optional[Decimal],
        trailing_price: Optional[Decimal],
        trailing_points: Decimal,
        direction: str,
        market_day: date,
    ) -> tuple[Decimal, str, Optional[datetime]]:
        """Walk through candles after entry to simulate SL/TP/trailing/EOD checks.

        Returns (exit_price, exit_reason, exit_time).
        """
        last_price = entry_price
        current_trailing = trailing_price

        for candle in candles:
            # Check each candle's high and low for trigger hits
            if direction == Instrument.Transaction.BUY:
                # Check stop loss first (worst case: SL hit on low)
                if stop_price is not None and candle.low <= stop_price:
                    return stop_price, "stop_loss", candle.timestamp
                if current_trailing is not None and candle.low <= current_trailing:
                    return current_trailing, "trailing_stop", candle.timestamp
                # Check target (hit on high)
                if target_price is not None and candle.high >= target_price:
                    return target_price, "target", candle.timestamp
                # Update trailing stop if price moved favorably
                if trailing_points > 0 and candle.high > last_price:
                    candidate = _quantize(candle.high - trailing_points)
                    if current_trailing is None or candidate > current_trailing:
                        current_trailing = candidate
                last_price = candle.close
            else:
                # SELL direction
                if stop_price is not None and candle.high >= stop_price:
                    return stop_price, "stop_loss", candle.timestamp
                if current_trailing is not None and candle.high >= current_trailing:
                    return current_trailing, "trailing_stop", candle.timestamp
                if target_price is not None and candle.low <= target_price:
                    return target_price, "target", candle.timestamp
                if trailing_points > 0 and candle.low < last_price:
                    candidate = _quantize(candle.low + trailing_points)
                    if current_trailing is None or candidate < current_trailing:
                        current_trailing = candidate
                last_price = candle.close

        # EOD exit — use last candle's close price
        eod_time = self._market_time(market_day, time(15, 25))
        return _quantize(last_price), "end_of_day", eod_time

    @staticmethod
    def _compute_backtest_pnl(
        *,
        entry_price: Decimal,
        exit_price: Decimal,
        quantity: int,
        direction: str,
    ) -> Decimal:
        if direction == Instrument.Transaction.SELL:
            diff = entry_price - exit_price
        else:
            diff = exit_price - entry_price
        pnl = diff * quantity
        return pnl.quantize(Decimal("0.05"), rounding=ROUND_HALF_UP)

    def _get_backtest_underlying_price(
        self,
        instrument: Instrument,
        market_day: date,
    ) -> Optional[Decimal]:
        """Fetch the underlying index opening price for a historical date.

        Uses the market_client to fetch a 1-minute candle at 9:15 AM
        from the index (not option) token.
        """
        if not self.market_client:
            return None

        from .market_data import LiveMarketDataProvider
        mapping = LiveMarketDataProvider.INDEX_TOKEN_MAP.get(instrument.instrument)
        if not mapping:
            return None

        exchange, token = mapping
        start = self._market_time(market_day, time(9, 15))
        end = self._market_time(market_day, time(9, 20))
        try:
            candles = self.market_client.get_option_candles(
                exchange=exchange,
                symbol_token=token,
                interval="FIVE_MINUTE",
                start=start,
                end=end,
            )
            if candles:
                price = candles[0].open
                self.logger.info(
                    f"Backtest underlying price for {instrument.instrument} on {market_day}: {price}"
                )
                return Decimal(str(price)).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
        except Exception as exc:
            self.logger.warning(
                f"Failed to fetch backtest underlying price for {instrument.instrument}: {exc}"
            )
        return None

    def _execute(
        self,
        config: AlgoConfiguration,
        activation: StrategyActivation,
        execution_mode: str,
    ) -> Dict[str, object]:
        if not config.algo_active:
            raise StrategySkip("Algo is currently disabled.")
        if not activation.is_active:
            raise StrategySkip("Strategy Alpha is not active for this user.")
        if execution_mode == Trade.ExecutionMode.LIVE and not config.market_active:
            raise StrategySkip("Market access is disabled; enable market_active before live trading.")

        instruments = list(
            activation.selected_instruments.filter(active=True).order_by("instrument")
        )
        if not instruments:
            raise StrategySkip("No active instruments assigned to Strategy Alpha.")

        profile = self._resolve_profile()
        self._profile = profile
        self.market_client = self._build_market_client(profile)

        provider = self._market_data_provider or build_market_data_provider(
            profile=profile,
            execution_mode=execution_mode,
            seed=int(timezone.now().timestamp()),
            market_date=self.market_date,
        )

        order_executor = OrderExecutor(
            profile=profile,
            execution_mode=execution_mode,
            logger=self.logger,
        )

        # Batch-prefetch all underlying index prices in a single API call
        # instead of 3 separate ltpData calls (one per instrument).
        if hasattr(provider, "prefetch_underlying_prices") and self.market_client:
            provider.prefetch_underlying_prices(instruments, self.market_client)

        summary = {
            "status": "completed",
            "mode": execution_mode,
            "opened_trades": 0,
            "closed_trades": 0,
            "net_pnl": Decimal("0"),
            "instrument_summaries": [],
        }

        # Process instruments sequentially with delays to stay below SmartAPI rate limits.
        import time as _time
        for idx, instrument in enumerate(instruments):
            if idx > 0:
                # Pause between instruments to avoid rate-limit ("Too many requests")
                _time.sleep(2)
            for attempt in range(1, 4):
                try:
                    instrument_summary = self._process_instrument(
                        instrument=instrument,
                        provider=provider,
                        execution_mode=execution_mode,
                        order_executor=order_executor,
                    )
                    summary["opened_trades"] += instrument_summary.opened
                    summary["closed_trades"] += instrument_summary.closed
                    summary["net_pnl"] += instrument_summary.pnl
                    summary["instrument_summaries"].append(instrument_summary.as_dict())
                    break  # success
                except Exception as exc:
                    exc_msg = str(exc).lower()
                    is_retryable = (
                        "too many" in exc_msg
                        or "try after" in exc_msg
                        or "broken pipe" in exc_msg
                        or "connection reset" in exc_msg
                        or "connection aborted" in exc_msg
                    )
                    if is_retryable and attempt < 3:
                        wait = 3 * attempt
                        self.logger.warning(
                            f"Retryable error on {instrument.instrument}, retry {attempt}/3 after {wait}s: {exc}"
                        )
                        _time.sleep(wait)
                        continue
                    self.logger.error(f"Failed to process {instrument.instrument}: {exc}")
                    summary["instrument_summaries"].append({
                        "instrument": instrument.instrument,
                        "opened": 0,
                        "closed": 0,
                        "message": f"Error: {str(exc)}",
                    })
                    break

        summary["net_pnl"] = str(summary["net_pnl"])
        return summary

    def _resolve_profile(self) -> Optional[UserProfile]:
        try:
            return self.user.profile
        except UserProfile.DoesNotExist:
            return None

    def _build_market_client(self, profile: Optional[UserProfile]) -> Optional[SmartAPIMarketClient]:
        if not profile or not profile.api_key or not profile.jwt_token:
            return None
        try:
            return SmartAPIMarketClient(api_key=profile.api_key, jwt_token=profile.jwt_token)
        except SmartAPIMarketError as exc:
            self.logger.warning("SmartAPI market client unavailable: %s", exc)
            return None

    def _process_instrument(
        self,
        *,
        instrument: Instrument,
        provider: BaseMarketDataProvider,
        execution_mode: str,
        order_executor: OrderExecutor,
    ) -> InstrumentSummary:
        summary = InstrumentSummary(instrument=instrument.instrument)
        self.logger.info(f"═══ Processing {instrument.instrument} ═══")
        self.logger.info(f"Active: {instrument.active}, Direction: {instrument.transaction}, Lots: {instrument.no_of_lots}")
        
        try:
            snapshot = self._get_entry_snapshot(provider, instrument)
            summary.price = snapshot.price
            snapshot_volume = getattr(snapshot, "volume", None)
            self.logger.info(f"Market snapshot - Price: {snapshot.price}, Volume: {snapshot_volume}")
        except MarketDataError as exc:
            message = f"Market data unavailable: {exc}"
            summary.message = message
            self.logger.error(f"❌ {message}")
            return summary
        contracts = self._contract_specs(instrument, snapshot, provider)
        self.logger.info(f"Found {len(contracts)} contract(s) to process")
        
        for contract in contracts:
            self.logger.info(f"--- Contract: {contract.symbol} ({contract.option_type}, Strike: {contract.strike}) ---")
            try:
                with transaction.atomic():
                    open_trade = (
                        Trade.objects.select_for_update()
                        .filter(
                            user=self.user,
                            instrument=instrument,
                            strategy_code=self.STRATEGY_CODE,
                            execution_mode=execution_mode,
                            status=Trade.Status.OPEN,
                            contract_symbol=contract.symbol,
                        )
                        .order_by("-entry_datetime")
                        .first()
                    )
                    if open_trade:
                        # For ATM instruments, snapshot.price is the underlying index.
                        # We need the option's LTP for trade monitoring.
                        monitor_price = self._get_option_ltp(instrument, contract) or snapshot.price
                        self.logger.info(f"✓ Existing open trade found - ID: {open_trade.id}, Entry: {open_trade.entry_price}, Current: {monitor_price}")
                        closed, pnl_delta, reason = self._maybe_close_trade(
                            open_trade,
                            monitor_price,
                            instrument,
                            order_executor,
                        )
                        if closed:
                            self.logger.info(f"✓ Trade closed - Reason: {reason}, P&L: {pnl_delta}")
                        else:
                            self.logger.info("Trade remains open - Monitoring...")
                        summary.closed += closed
                        summary.pnl += pnl_delta
                        if reason:
                            summary.message = reason
                        trailing_updated = self._update_trailing_stop(open_trade, monitor_price, instrument)
                        if trailing_updated:
                            self.logger.info(f"Trailing stop updated to: {open_trade.trailing_stop_price}")
                        open_trade.last_price = monitor_price
                        update_fields = ["last_price", "updated_at"]
                        if trailing_updated:
                            update_fields.insert(1, "trailing_stop_price")
                        open_trade.save(update_fields=update_fields)
                    else:
                        self.logger.info("No open trade - Checking entry conditions...")
                        opened, message = self._maybe_open_trade(
                            instrument,
                            contract,
                            snapshot,
                            execution_mode,
                            order_executor,
                            provider,
                        )
                        if opened:
                            self.logger.info(f"✓ New trade opened - Entry: {snapshot.price}")
                        else:
                            self.logger.info(f"✗ Entry condition not met - {message}")
                        summary.opened += opened
                        if message:
                            summary.message = message
            except StrategySkip as exc:
                summary.message = str(exc)
                self.logger.warning(f"⏭️  Skipped: {exc}")
                self.logger.info(
                    "Skipping contract %s for %s: %s",
                    contract.symbol or contract.label,
                    instrument.instrument,
                    exc,
                )

        return summary

    def _contract_specs(
        self,
        instrument: Instrument,
        snapshot: EntrySnapshot,
        provider: BaseMarketDataProvider,
    ) -> list[ContractSpec]:
        specs: list[ContractSpec] = []
        mode = instrument.strike_selection or Instrument.StrikeSelection.STATIC
        if mode == Instrument.StrikeSelection.ATM:
            specs.extend(self._atm_contract_specs(instrument, snapshot, provider))
        else:
            primary_symbol = instrument.trading_symbol or ""
            primary_token = instrument.symbol_token or ""
            specs.append(
                ContractSpec(
                    symbol=primary_symbol,
                    token=primary_token,
                    option_type="CE" if primary_symbol.endswith("CE") else "PE",
                    strike=self._extract_strike(primary_symbol),
                    label="primary",
                )
            )
            if instrument.alternate_trading_symbol:
                specs.append(
                    ContractSpec(
                        symbol=instrument.alternate_trading_symbol,
                        token=instrument.alternate_symbol_token or "",
                        option_type="PE" if primary_symbol.endswith("CE") else "CE",
                        strike=self._extract_strike(instrument.alternate_trading_symbol),
                        label="alternate",
                    )
                )
        return [spec for spec in specs if spec.symbol]

    def _extract_strike(self, symbol: str) -> int:
        if not symbol:
            return 0
        upper_symbol = symbol.upper()
        base = symbol[:-2] if upper_symbol.endswith(("CE", "PE")) else symbol
        digits = "".join(ch for ch in base if ch.isdigit())
        if not digits:
            return 0
        return int(digits[-5:])

    def _atm_contract_specs(
        self,
        instrument: Instrument,
        snapshot: EntrySnapshot,
        provider: BaseMarketDataProvider,
    ) -> list[ContractSpec]:
        market_day = self._current_market_day()
        cached = self._cached_contract_specs(instrument, market_day)
        if cached:
            return cached

        expiry_code = self._resolve_expiry_code(instrument)
        if not expiry_code:
            raise StrategySkip("Contract expiry not configured for instrument.")
        underlying = snapshot.underlying_price or provider.get_underlying_price(instrument)
        if underlying is None:
            fallback_specs = self._fallback_current_contract_specs(instrument)
            if fallback_specs:
                self.logger.warning(
                    "Underlying price unavailable for %s; falling back to current configured contracts.",
                    instrument.instrument,
                )
                return fallback_specs
            raise StrategySkip("Unable to determine underlying price for dynamic strike selection.")
        step = max(instrument.strike_step or 0, 1)
        base_strike = self._round_to_step(_as_decimal(underlying), step)
        ce_strike = max(0, base_strike + (instrument.ce_strike_offset or 0) * step)
        pe_strike = max(0, base_strike + (instrument.pe_strike_offset or 0) * step)
        ce_spec = self._build_contract_spec(
            instrument,
            expiry_code,
            ce_strike,
            "CE",
            label="primary",
        )
        pe_spec = self._build_contract_spec(
            instrument,
            expiry_code,
            pe_strike,
            "PE",
            label="alternate",
        )

        # If tokens couldn't be resolved (expired contracts removed from
        # scrip master), try the nearest available expiry.
        if not ce_spec.token or not pe_spec.token:
            fallback_code = self._nearest_available_expiry(instrument)
            if fallback_code and fallback_code.upper() != expiry_code.upper():
                self.logger.info(
                    "Configured expiry %s not found in scrip master for %s; "
                    "using nearest available: %s",
                    expiry_code, instrument.instrument, fallback_code,
                )
                if not ce_spec.token:
                    ce_spec = self._build_contract_spec(
                        instrument, fallback_code, ce_strike, "CE", label="primary",
                    )
                if not pe_spec.token:
                    pe_spec = self._build_contract_spec(
                        instrument, fallback_code, pe_strike, "PE", label="alternate",
                    )

        specs = [spec for spec in (ce_spec, pe_spec) if spec]
        if not specs:
            raise StrategySkip("Unable to determine ATM contracts for instrument.")

        if self._should_persist_daily_selection(market_day):
            self._persist_daily_selection(
                instrument,
                market_day,
                underlying,
                ce_spec,
                pe_spec,
            )

        return specs

    def _build_contract_spec(
        self,
        instrument: Instrument,
        expiry_code: str,
        strike: int,
        option_type: str,
        *,
        label: str,
    ) -> ContractSpec:
        strike_component = f"{strike:05d}"
        symbol = f"{instrument.instrument}{expiry_code}{strike_component}{option_type.upper()}"
        try:
            metadata = find_contract(
                underlying=instrument.instrument,
                expiry_code=expiry_code,
                strike=strike,
                option_type=option_type.upper(),
            ) or lookup_contract(symbol)
        except ContractLookupError as exc:
            self.logger.debug("Contract metadata unavailable for %s: %s", symbol, exc)
            metadata = None
        token = metadata.token if metadata else ""
        return ContractSpec(
            symbol=metadata.symbol if metadata else symbol,
            token=token,
            option_type=option_type.upper(),
            strike=strike,
            label=label,
        )

    def _fallback_current_contract_specs(self, instrument: Instrument) -> list[ContractSpec]:
        specs: list[ContractSpec] = []
        if instrument.trading_symbol:
            specs.append(
                ContractSpec(
                    symbol=instrument.trading_symbol,
                    token=instrument.symbol_token or "",
                    option_type=self._infer_option_type(instrument.trading_symbol),
                    strike=self._extract_strike(instrument.trading_symbol),
                    label="primary",
                )
            )
        if instrument.alternate_trading_symbol:
            specs.append(
                ContractSpec(
                    symbol=instrument.alternate_trading_symbol,
                    token=instrument.alternate_symbol_token or "",
                    option_type=self._infer_option_type(instrument.alternate_trading_symbol),
                    strike=self._extract_strike(instrument.alternate_trading_symbol),
                    label="alternate",
                )
            )
        return [spec for spec in specs if spec.symbol and spec.token]

    def _nearest_available_expiry(self, instrument: Instrument) -> str:
        """Find the nearest valid expiry on or after the market day from the expiry map."""
        from ..utils.instrument_data import load_expiry_map, next_valid_expiry

        expiry_map = load_expiry_map()
        available = expiry_map.get(instrument.instrument.upper(), [])
        if not available:
            return ""
        market_day = self._current_market_day()
        code = next_valid_expiry(available, market_day)
        if not code:
            return ""
        parsed = parse_expiry_code(code)
        if parsed:
            return parsed.strftime("%d%b%y").upper()
        return code.upper()

    def _resolve_expiry_code(self, instrument: Instrument) -> str:
        if instrument.contract_expiry:
            return instrument.contract_expiry.strftime("%d%b%y").upper()
        if instrument.contract_expiry_code:
            parsed = parse_expiry_code(instrument.contract_expiry_code)
            if parsed:
                return parsed.strftime("%d%b%y").upper()
            return instrument.contract_expiry_code.upper()
        return ""

    def _round_to_step(self, value: Decimal, step: int) -> int:
        step_decimal = Decimal(step)
        multiplier = (value / step_decimal).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
        return int(multiplier * step_decimal)

    def _current_market_day(self) -> date:
        return self.market_date or timezone.localdate()

    def _cached_contract_specs(self, instrument: Instrument, market_day: date) -> list[ContractSpec]:
        if instrument.daily_selection_date != market_day:
            return []
        specs: list[ContractSpec] = []
        if instrument.daily_ce_symbol:
            specs.append(
                self._contract_spec_from_cache(
                    symbol=instrument.daily_ce_symbol,
                    token=instrument.daily_ce_token,
                    label="primary",
                )
            )
        if instrument.daily_pe_symbol:
            specs.append(
                self._contract_spec_from_cache(
                    symbol=instrument.daily_pe_symbol,
                    token=instrument.daily_pe_token,
                    label="alternate",
                )
            )
        return [spec for spec in specs if spec.symbol and spec.token]

    def _contract_spec_from_cache(self, *, symbol: str, token: str, label: str) -> ContractSpec:
        option_type = self._infer_option_type(symbol)
        return ContractSpec(
            symbol=symbol,
            token=token or "",
            option_type=option_type,
            strike=self._extract_strike(symbol),
            label=label,
        )

    def _infer_option_type(self, symbol: str) -> str:
        upper = (symbol or "").upper()
        if upper.endswith("PE"):
            return "PE"
        return "CE"

    def _should_persist_daily_selection(self, market_day: date) -> bool:
        if self.market_date and self.market_date != timezone.localdate():
            return False
        return True

    def _persist_daily_selection(
        self,
        instrument: Instrument,
        market_day: date,
        underlying: Decimal,
        ce_spec: ContractSpec | None,
        pe_spec: ContractSpec | None,
    ) -> None:
        instrument.daily_selection_date = market_day
        instrument.daily_underlying_price = underlying.quantize(Decimal("0.01"))
        instrument.daily_ce_symbol = ce_spec.symbol if ce_spec else ""
        instrument.daily_ce_token = ce_spec.token if ce_spec else ""
        instrument.daily_pe_symbol = pe_spec.symbol if pe_spec else ""
        instrument.daily_pe_token = pe_spec.token if pe_spec else ""
        instrument.save(
            update_fields=[
                "daily_selection_date",
                "daily_underlying_price",
                "daily_ce_symbol",
                "daily_ce_token",
                "daily_pe_symbol",
                "daily_pe_token",
                "updated_at",
            ]
        )

    def _plan_trade_entry(
        self,
        instrument: Instrument,
        contract: ContractSpec,
        snapshot: EntrySnapshot,
        provider: BaseMarketDataProvider,
    ) -> EntryPlan:
        direction = instrument.transaction or Instrument.Transaction.BUY

        if not instrument.active:
            self.logger.info("✗ Instrument is inactive")
            return EntryPlan(False, message="instrument_inactive")

        if instrument.strike_selection != Instrument.StrikeSelection.ATM or direction != Instrument.Transaction.BUY:
            if not self._entry_condition_met(instrument, snapshot):
                self.logger.info("✗ Entry condition not met (price/volume/gap check)")
                return EntryPlan(False, message="conditions_not_met")
            self.logger.info("✓ Entry condition met")
            return EntryPlan(True, entry_price=snapshot.price)

        if not self.market_client:
            raise StrategySkip("SmartAPI market client unavailable; connect Angel account before running strategy.")

        market_day = self._current_market_day()
        prev_levels = self._ensure_previous_session_levels(instrument, contract, market_day)
        if not prev_levels:
            self.logger.info("✗ Previous session levels not available")
            return EntryPlan(False, message="previous_levels_unavailable")

        reference_high, reference_low = prev_levels
        self.logger.info(f"Previous levels - High: {reference_high}, Low: {reference_low}")
        
        candles = self._get_intraday_candles(instrument, contract, market_day)
        if len(candles) < 2:
            self.logger.info(f"✗ Not enough candles yet (have: {len(candles)}, need: 2+)")
            return EntryPlan(False, message="awaiting_candles", stop_loss=reference_low)

        self.logger.info(f"Analyzing {len(candles)} candles for breakout...")
        now_local = timezone.localtime()
        current_high = reference_high
        current_low = reference_low

        for index, candle in enumerate(candles[:-1]):
            if candle.close <= current_high:
                continue

            is_first = index == 0
            if is_first and candle.open > current_high:
                self.logger.info(f"✗ Gap up detected on first candle - Open: {candle.open} > High: {current_high}")
                current_high = candle.high
                current_low = candle.low
                self._update_daily_levels(
                    instrument,
                    contract,
                    high=current_high,
                    low=current_low,
                    level_date=market_day,
                )
                continue

            next_candle = candles[index + 1]

            entry_time = next_candle.timestamp
            if entry_time > now_local:
                self.logger.info(f"⏰ Breakout detected but waiting for next candle - Entry time: {entry_time}")
                return EntryPlan(False, message="await_next_candle", stop_loss=current_low, entry_time=entry_time, reference_high=current_high, reference_low=current_low)

            entry_price = next_candle.open
            self.logger.info(f"✓ BREAKOUT CONFIRMED - Entry: {entry_price}, SL: {current_low}")
            return EntryPlan(
                True,
                entry_price=entry_price,
                stop_loss=current_low,
                entry_time=entry_time,
                reference_high=current_high,
                reference_low=current_low,
            )

        self.logger.info("✗ No breakout detected yet")
        return EntryPlan(False, message="no_breakout", stop_loss=current_low)

    def _ensure_previous_session_levels(
        self,
        instrument: Instrument,
        contract: ContractSpec,
        market_day: date,
    ) -> Optional[Tuple[Decimal, Decimal]]:
        if not self.market_client:
            return None
        high_field, low_field = self._prev_level_fields(contract)
        level_date = instrument.daily_levels_date
        current_high = getattr(instrument, high_field)
        current_low = getattr(instrument, low_field)
        if level_date == market_day and current_high is not None and current_low is not None:
            return Decimal(current_high), Decimal(current_low)

        exchange = instrument.exchange or "NFO"
        token = contract.token
        if not token:
            raise StrategySkip("Contract token missing; refresh instrument metadata.")

        # Try up to 5 previous weekdays to handle holidays
        candidate = market_day
        candles = []
        for _ in range(5):
            candidate = self._previous_trading_day(candidate)
            start = self._market_time(candidate, time(14, 45))
            end = self._market_time(candidate, time(15, 30))
            candles = self.market_client.get_option_candles(
                exchange=exchange,
                symbol_token=token,
                interval="FIVE_MINUTE",
                start=start,
                end=end,
            )
            if candles:
                self.logger.info(
                    "Previous session levels from %s (%d candles)",
                    candidate.isoformat(), len(candles),
                )
                break
            self.logger.info(
                "No candle data for %s (likely holiday), trying earlier day",
                candidate.isoformat(),
            )

        if not candles:
            return None

        prev_high = max(candle.high for candle in candles)
        prev_low = min(candle.low for candle in candles)

        self._update_daily_levels(
            instrument,
            contract,
            high=prev_high,
            low=prev_low,
            level_date=market_day,
        )

        return prev_high, prev_low

    def _previous_trading_day(self, market_day: date) -> date:
        candidate = market_day - timedelta(days=1)
        while candidate.weekday() >= 5:
            candidate -= timedelta(days=1)
        return candidate

    def _market_time(self, day: date, clock: time) -> datetime:
        tz = timezone.get_current_timezone()
        naive = datetime.combine(day, clock)
        return timezone.make_aware(naive, tz)

    def _get_intraday_candles(
        self,
        instrument: Instrument,
        contract: ContractSpec,
        market_day: date,
    ) -> list[Candle]:
        if not self.market_client:
            return []

        cache_key = f"{contract.symbol}:{market_day.isoformat()}"
        if cache_key in self._intraday_cache:
            return self._intraday_cache[cache_key]

        start = self._market_time(market_day, time(9, 15))
        if self.market_date and self.market_date != timezone.localdate():
            end = self._market_time(market_day, time(15, 30))
        else:
            end = timezone.localtime()
        exchange = instrument.exchange or "NFO"
        token = contract.token
        if not token:
            raise StrategySkip("Contract token missing; refresh instrument metadata.")

        candles = self.market_client.get_option_candles(
            exchange=exchange,
            symbol_token=token,
            interval="FIVE_MINUTE",
            start=start,
            end=end,
        )

        self._intraday_cache[cache_key] = candles
        return candles

    def _prev_level_fields(self, contract: ContractSpec) -> Tuple[str, str]:
        if contract.option_type.upper() == "PE":
            return "daily_pe_prev_high", "daily_pe_prev_low"
        return "daily_ce_prev_high", "daily_ce_prev_low"

    def _update_daily_levels(
        self,
        instrument: Instrument,
        contract: ContractSpec,
        *,
        high: Optional[Decimal],
        low: Optional[Decimal],
        level_date: Optional[date] = None,
    ) -> None:
        high_field, low_field = self._prev_level_fields(contract)
        update_fields: list[str] = []
        if high is not None:
            setattr(instrument, high_field, high.quantize(Decimal("0.05")))
            update_fields.append(high_field)
        if low is not None:
            setattr(instrument, low_field, low.quantize(Decimal("0.05")))
            update_fields.append(low_field)
        if level_date is not None:
            instrument.daily_levels_date = level_date
            update_fields.append("daily_levels_date")
        if update_fields:
            update_fields.append("updated_at")
            instrument.save(update_fields=update_fields)

    def _get_entry_snapshot(
        self,
        provider: BaseMarketDataProvider,
        instrument: Instrument,
    ) -> EntrySnapshot:
        get_snapshot = getattr(provider, "get_entry_snapshot", None)
        if callable(get_snapshot):
            snapshot = get_snapshot(instrument)
            if snapshot:
                return snapshot
        price = provider.get_price(instrument)
        return EntrySnapshot(price=price)

    def _get_option_ltp(self, instrument: Instrument, contract: ContractSpec) -> Optional[Decimal]:
        """Fetch the live option LTP for a specific contract via SmartAPI."""
        if not self.market_client or not contract.token:
            return None
        try:
            exchange = instrument.exchange or "NFO"
            ltp_map = self.market_client.get_ltp_batch(
                exchange_tokens={exchange: [contract.token]},
            )
            key = f"{exchange}:{contract.token}"
            return ltp_map.get(key)
        except Exception as exc:
            self.logger.debug("Option LTP fetch failed for %s: %s", contract.symbol, exc)
            return None

    def _maybe_open_trade(
        self,
        instrument: Instrument,
        contract: ContractSpec,
        snapshot: EntrySnapshot,
        execution_mode: str,
        order_executor: OrderExecutor,
        provider: BaseMarketDataProvider,
    ) -> tuple[int, Optional[str]]:
        plan = self._plan_trade_entry(instrument, contract, snapshot, provider)

        if not plan.should_enter:
            return 0, plan.message

        entry_reference = plan.entry_price or snapshot.price
        if entry_reference is None:
            raise StrategySkip("Entry price unavailable for trade execution.")

        price = _quantize(entry_reference)
        plan_stop = plan.stop_loss

        now = timezone.now()
        direction = instrument.transaction or Instrument.Transaction.BUY
        lots = max(instrument.no_of_lots or 0, 1)
        lot_size = instrument.lot_size or 1
        quantity = max(lots * lot_size, 1)

        pl_points = _as_decimal(instrument.pl_points)
        sl_points = _as_decimal(instrument.sl_points)
        trailing_points = _as_decimal(instrument.trailing_points)

        if direction == Instrument.Transaction.SELL:
            target_price = _quantize(price - pl_points) if pl_points else None
            stop_price = _quantize(price + sl_points) if sl_points else None
            trailing_price = _quantize(price + trailing_points) if trailing_points else stop_price
        else:
            target_price = _quantize(price + pl_points) if pl_points else None
            # Use breakout reference low as SL, but cap at sl_points from entry
            stop_anchor = plan_stop if plan_stop is not None else snapshot.previous_low
            max_sl_price = _quantize(price - sl_points) if sl_points else None
            if stop_anchor is not None:
                stop_price = _quantize(stop_anchor)
                # Never let SL be wider than sl_points from entry
                if max_sl_price is not None and stop_price < max_sl_price:
                    self.logger.info(
                        "SL capped: reference_low %s too far, using sl_points limit %s",
                        stop_price, max_sl_price,
                    )
                    stop_price = max_sl_price
            else:
                stop_price = max_sl_price
            trailing_price = _quantize(price - trailing_points) if trailing_points else stop_price

        order_result = order_executor.place_entry_order(
            instrument=instrument,
            direction=direction,
            quantity=quantity,
            reference_price=price,
            contract_symbol=contract.symbol,
            contract_token=contract.token,
        )
        filled_quantity_raw = order_result.get("filled_quantity")
        try:
            filled_quantity = int(filled_quantity_raw) if filled_quantity_raw is not None else quantity
        except (TypeError, ValueError):
            filled_quantity = quantity

        fill_price = _quantize(order_result.get("average_price", price))
        entry_order_id = order_result.get("order_id", "")
        entry_timestamp = plan.entry_time if plan.entry_time is not None else now
        if timezone.is_naive(entry_timestamp):
            entry_timestamp = timezone.make_aware(entry_timestamp, timezone.get_current_timezone())

        trade = Trade.objects.create(
            user=self.user,
            strategy_code=self.STRATEGY_CODE,
            instrument=instrument,
            execution_mode=execution_mode,
            status=Trade.Status.OPEN,
            direction=direction,
            quantity=max(filled_quantity, 1),
            entry_price=fill_price,
            entry_datetime=entry_timestamp,
            target_price=target_price,
            stop_loss_price=stop_price,
            trailing_stop_price=trailing_price,
            last_price=fill_price,
            external_entry_id=entry_order_id,
            contract_symbol=contract.symbol,
            contract_token=contract.token,
        )
        self.logger.info(
            "Opened %s position for %s at %s (target=%s, stop=%s)",
            direction,
            instrument.instrument,
            fill_price,
            target_price,
            stop_price,
        )
        message = "Opened (live)" if order_executor.is_live else "Opened"
        return 1, message

    def _entry_condition_met(self, instrument: Instrument, snapshot: EntrySnapshot) -> bool:
        if not instrument.active:
            return False
        price = snapshot.price
        previous_low = snapshot.previous_low
        next_open = snapshot.next_open or price
        if previous_low is not None:
            current_gap = (price - previous_low).copy_abs()
            next_gap = (next_open - previous_low).copy_abs()
            gap = min(current_gap, next_gap)
            if gap >= Decimal("40"):
                return False
        reference = instrument.premium_price
        if not reference or reference <= 0:
            return True
        if instrument.transaction == Instrument.Transaction.SELL:
            return price >= reference
        return price <= reference

    def _maybe_close_trade(
        self,
        trade: Trade,
        price: Decimal,
        instrument: Instrument,
        order_executor: OrderExecutor,
    ) -> tuple[int, Decimal, Optional[str]]:
        trigger = self._should_close_trade(trade, price)
        if not trigger:
            return 0, Decimal("0"), None

        # Use the exact SL/TP level as exit price instead of the current LTP.
        # In reality the order would fill at the trigger level, not at whatever
        # the LTP happens to be when we check.
        effective_price = self._effective_exit_price(trade, price, trigger)

        exit_result = order_executor.place_exit_order(
            instrument=instrument,
            trade=trade,
            reference_price=effective_price,
        )
        exit_price = _quantize(exit_result.get("average_price", effective_price))
        order_id = exit_result.get("order_id")

        pnl = self._close_trade(trade, exit_price, trigger, order_id=order_id)
        if trade.direction == Instrument.Transaction.SELL:
            pnl = pnl
        return 1, pnl, trigger

    @staticmethod
    def _effective_exit_price(
        trade: Trade, price: Decimal, trigger: str,
    ) -> Decimal:
        """Return the exact SL/TP/trailing level when a trigger fires.

        For demo and backtest we assume fills at the trigger price, not the
        observed LTP which may overshoot.
        """
        if trigger == "target" and trade.target_price is not None:
            return trade.target_price
        if trigger == "stop_loss" and trade.stop_loss_price is not None:
            return trade.stop_loss_price
        if trigger == "trailing_stop" and trade.trailing_stop_price is not None:
            return trade.trailing_stop_price
        return price

    def _should_close_trade(self, trade: Trade, price: Decimal) -> Optional[str]:
        if trade.direction == Instrument.Transaction.SELL:
            if trade.target_price and price <= trade.target_price:
                return "target"
            if trade.stop_loss_price and price >= trade.stop_loss_price:
                return "stop_loss"
            if trade.trailing_stop_price and price >= trade.trailing_stop_price:
                return "trailing_stop"
        else:
            if trade.target_price and price >= trade.target_price:
                return "target"
            if trade.stop_loss_price and price <= trade.stop_loss_price:
                return "stop_loss"
            if trade.trailing_stop_price and price <= trade.trailing_stop_price:
                return "trailing_stop"
        if self._should_exit_end_of_day(trade):
            return "end_of_day"
        return None

    def _close_trade(
        self,
        trade: Trade,
        price: Decimal,
        reason: str,
        order_id: Optional[str] = None,
    ) -> Decimal:
        now = timezone.now()
        exit_time = now
        if reason == "end_of_day":
            tz = timezone.get_current_timezone()
            if trade.entry_datetime:
                market_day = trade.entry_datetime.astimezone(tz).date()
            else:
                market_day = self._current_market_day()
            deadline = self._market_time(market_day, time(15, 25))
            if not self.market_date and deadline > now:
                exit_time = now
            else:
                exit_time = deadline

        trade.exit_price = price
        trade.exit_datetime = exit_time
        trade.status = Trade.Status.CLOSED
        pnl = self._calculate_pnl(trade, price)
        trade.pnl = pnl
        note_prefix = f"Closed on {reason}"
        trade.notes = f"{note_prefix} at {price}"
        trade.last_price = price
        update_fields = [
            "exit_price",
            "exit_datetime",
            "status",
            "pnl",
            "notes",
            "last_price",
            "updated_at",
        ]
        if order_id:
            trade.external_exit_id = order_id
            update_fields.append("external_exit_id")
        trade.save(update_fields=update_fields)
        self.logger.info(
            "Closed %s position for %s at %s (%s) PnL=%s",
            trade.direction,
            trade.instrument.instrument,
            price,
            reason,
            pnl,
        )
        return pnl

    def _calculate_pnl(self, trade: Trade, exit_price: Decimal) -> Decimal:
        entry_price = trade.entry_price or Decimal("0")
        quantity = trade.quantity or 0
        if quantity == 0:
            return Decimal("0")
        if trade.direction == Instrument.Transaction.SELL:
            diff = entry_price - exit_price
        else:
            diff = exit_price - entry_price
        pnl = diff * quantity
        return pnl.quantize(Decimal("0.05"), rounding=ROUND_HALF_UP)

    def _update_trailing_stop(
        self,
        trade: Trade,
        price: Decimal,
        instrument: Instrument,
    ) -> bool:
        trailing_points = _as_decimal(instrument.trailing_points)
        if trailing_points <= 0:
            return False
        last_price = trade.last_price or trade.entry_price or price
        updated = False
        if trade.direction == Instrument.Transaction.SELL:
            if price < last_price:
                candidate = _quantize(price + trailing_points)
                if trade.trailing_stop_price is None or candidate < trade.trailing_stop_price:
                    trade.trailing_stop_price = candidate
                    updated = True
        else:
            if price > last_price:
                candidate = _quantize(price - trailing_points)
                if trade.trailing_stop_price is None or candidate > trade.trailing_stop_price:
                    trade.trailing_stop_price = candidate
                    updated = True
        if updated:
            self.logger.debug(
                "Adjusted trailing stop for %s to %s",
                trade.instrument.instrument,
                trade.trailing_stop_price,
            )
        return updated

    def _should_exit_end_of_day(self, trade: Trade) -> bool:
        tz = timezone.get_current_timezone()
        if trade.exit_datetime:
            return False
        if trade.entry_datetime:
            market_day = trade.entry_datetime.astimezone(tz).date()
        else:
            market_day = self._current_market_day()

        if self.market_date and self.market_date != timezone.localdate():
            return True

        deadline = self._market_time(market_day, time(15, 25))
        now = timezone.now()
        if now >= deadline:
            return True
        if now.date() > market_day:
            return True
        return False
