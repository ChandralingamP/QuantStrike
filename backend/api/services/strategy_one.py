"""Execution engine for Strategy Alpha backtesting (ORB candle logic).

This implementation follows the steps documented in docs/Strategy_One.md and
reuses the existing market data and order infrastructure from Strategy Alpha.

Key behaviours (IST-based):
- Uses per-user Instrument rows and their configured contract expiry code.
- Derives contract symbol/token via existing contract lookup utilities.
- Fetches previous trading day's 14:45–15:30 candles to compute high/low.
- From 09:15 onwards, scans 5-minute candles for a close above previous high,
  then applies first-candle and <=40-point filters before placing an order.

The engine itself is pure Python and does not depend on any external
"My API" folders; all metadata comes from the database and backend/data.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import Dict, List, Optional, Tuple

from django.contrib.auth.models import User
from django.db import transaction
from django.utils import timezone

from ..models import AlgoConfiguration, Instrument, StrategyActivation, StrategyRunLog, Trade, UserProfile
from .market_data import (
    BaseMarketDataProvider,
    Candle,
    MarketDataError,
    build_market_data_provider,
    iter_symbol_token_pairs,
)
from .strategy_alpha import OrderExecutor, StrategySkip, _as_decimal
from .contract_selector import find_atm_contracts

try:  # optional dependency for precise exchange calendars
    from exchange_calendars import get_calendar  # type: ignore
except Exception:  # pragma: no cover - library may not be installed
    get_calendar = None  # type: ignore


@dataclass
class StrategyOneConfig:
    """Parameters controlling Strategy One behaviour.

    These are hard-coded defaults for now but could later come from
    AlgoConfiguration or per-instrument overrides.
    """

    # Candle timeframe and session boundaries (IST)
    candle_interval: str = "FIVE_MINUTE"
    session_start: time = time(9, 15)  # 09:15 AM
    # Previous-day high/low window (IST)
    prev_window_start: time = time(14, 45)
    prev_window_end: time = time(15, 30)
    # Max distance from previous low for entry
    max_open_minus_prev_low: Decimal = Decimal("40")


@dataclass
class InstrumentRunSummary:
    instrument: str
    opened: int = 0
    closed: int = 0
    price: Optional[Decimal] = None
    message: Optional[str] = None

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
        return payload


class OpeningRangeBreakoutEngine:
    """Execution engine for Strategy Alpha (Opening Range Breakout logic).

    Implements the 10-step candle logic described in docs/Strategy_One.md,
    using previous-day range and first 5-minute breakout behaviour.
    """

    STRATEGY_CODE = StrategyActivation.STRATEGY_ALPHA
    STRATEGY_MODES = ("demo", "live")

    def __init__(
        self,
        *,
        user: User,
        execution_mode: Optional[str] = None,
        market_data_provider: Optional[BaseMarketDataProvider] = None,
        market_date: Optional[date] = None,
        ignore_activation: bool = False,
        instrument_ids: Optional[List[int]] = None,
    ) -> None:
        self.user = user
        self._execution_mode = execution_mode
        self._market_data_provider = market_data_provider
        self.market_date = market_date or timezone.localdate()
        self.config = StrategyOneConfig()
        self._profile: Optional[UserProfile] = None
        self.ignore_activation = ignore_activation
        self.instrument_ids = instrument_ids or []

        self._calendar = None
        if get_calendar is not None:
            # XBOM calendar (Bombay Stock Exchange) from exchange_calendars
            try:
                self._calendar = get_calendar("XBOM")
            except Exception:
                self._calendar = None

    # Public API -----------------------------------------------------------

    def run(self) -> Dict[str, object]:
        """Run Strategy One for all active instruments assigned to this user."""
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
            run_log.mark_completed(
                status=StrategyRunLog.Status.FAILED,
                message=str(exc),
                extra={"mode": execution_mode},
            )
            raise

        run_log.mark_completed(extra=summary)
        return summary

    # Core execution -------------------------------------------------------

    def _execute(
        self,
        config: AlgoConfiguration,
        activation: StrategyActivation,
        execution_mode: str,
    ) -> Dict[str, object]:
        # Normal safety checks always apply unless ignore_activation was
        # explicitly requested by a backtest caller.
        if not self.ignore_activation:
            if not config.algo_active:
                raise StrategySkip("Algo is currently disabled.")
            if not activation.is_active:
                raise StrategySkip("Strategy Alpha is not active for this user.")
            if execution_mode == Trade.ExecutionMode.LIVE and not config.market_active:
                raise StrategySkip(
                    "Market access is disabled; enable market_active before live trading."
                )
        else:
            # Even when ignoring activation, still protect true live trading.
            if execution_mode == Trade.ExecutionMode.LIVE and not config.market_active:
                raise StrategySkip(
                    "Market access is disabled; enable market_active before live trading."
                )

        # Do not run the strategy on non-trading days.
        if not self._is_trading_day(self.market_date):
            raise StrategySkip("Selected date is not a trading day.")

        qs = activation.selected_instruments.all().order_by("instrument")
        if self.instrument_ids:
            qs = qs.filter(id__in=self.instrument_ids)
        elif not self.ignore_activation:
            qs = qs.filter(active=True)

        instruments = list(qs)
        if not instruments:
            raise StrategySkip("No instruments available for Strategy Alpha.")

        profile = self._resolve_profile()
        self._profile = profile

        provider = self._market_data_provider or build_market_data_provider(
            profile=profile,
            execution_mode=execution_mode,
            seed=int(timezone.now().timestamp()),
            market_date=self.market_date,
        )

        order_executor = OrderExecutor(
            profile=profile,
            execution_mode=execution_mode,
            logger=self._build_logger(),
        )

        summary = {
            "status": "completed",
            "mode": execution_mode,
            "opened_trades": 0,
            "closed_trades": 0,
            "instrument_summaries": [],
        }

        with transaction.atomic():
            for instrument in instruments:
                instrument_summary = self._process_instrument(
                    instrument=instrument,
                    provider=provider,
                    execution_mode=execution_mode,
                    order_executor=order_executor,
                )
                summary["opened_trades"] += instrument_summary.opened
                summary["closed_trades"] += instrument_summary.closed
                summary["instrument_summaries"].append(instrument_summary.as_dict())

        return summary

    def _build_logger(self):
        import logging

        logger = logging.getLogger(__name__)
        return logger.getChild(f"StrategyOne[{self.user.username}]")

    # Helpers --------------------------------------------------------------

    def _resolve_profile(self) -> Optional[UserProfile]:
        try:
            return self.user.profile
        except UserProfile.DoesNotExist:
            return None

    def _previous_trading_day(self) -> date:
        """Return the previous trading day for the configured market_date.

        Uses exchange_calendars when available; otherwise falls back to
        skipping weekends only.
        """

        if self._calendar is not None:
            # exchange_calendars expects pandas-like Timestamp inputs; we can
            # pass the date directly and rely on its previous session lookup.
            try:
                previous = self._calendar.previous_session(self.market_date)
                return previous.date()  # type: ignore[no-any-return]
            except Exception:
                pass

        # Fallback: move back to the previous weekday (Mon–Fri).
        candidate = self.market_date - timedelta(days=1)
        while candidate.weekday() >= 5:  # 5 = Saturday, 6 = Sunday
            candidate -= timedelta(days=1)
        return candidate

    def _is_trading_day(self, value: date) -> bool:
        """Return True if the given date is a trading day.

        Prefer the configured exchange calendar (which knows holidays);
        otherwise treat Monday–Friday as trading days.
        """

        if self._calendar is not None:
            try:
                return bool(self._calendar.is_session(value))
            except Exception:
                pass
        # Fallback: simple weekday check
        return value.weekday() < 5

    def _intraday_window(
        self,
        *,
        ref_date: date,
        start: time,
        end: time,
    ) -> Tuple[datetime, datetime]:
        tz = timezone.get_current_timezone()
        start_dt = datetime.combine(ref_date, start)
        end_dt = datetime.combine(ref_date, end)
        if timezone.is_naive(start_dt):
            start_dt = timezone.make_aware(start_dt, tz)
        if timezone.is_naive(end_dt):
            end_dt = timezone.make_aware(end_dt, tz)
        return start_dt, end_dt

    def _fetch_prev_day_high_low(
        self,
        *,
        provider: BaseMarketDataProvider,
        instrument: Instrument,
        contract_symbol: str,
        contract_token: str,
    ) -> Tuple[Decimal, Decimal]:
        """Step3: previous day's 14:45–15:30 high/low for the symbol.
        
        Searches back up to 10 trading days to find data if the immediate
        previous day doesn't have available candles.
        """
        max_lookback_days = 10
        current_date = self.market_date
        
        for attempt in range(max_lookback_days):
            # Find previous trading day relative to current_date
            if self._calendar is not None:
                try:
                    prev_day = self._calendar.previous_session(current_date)
                    prev_day = prev_day.date()  # type: ignore[assignment]
                except Exception:
                    prev_day = current_date - timedelta(days=1)
                    while prev_day.weekday() >= 5:
                        prev_day -= timedelta(days=1)
            else:
                prev_day = current_date - timedelta(days=1)
                while prev_day.weekday() >= 5:
                    prev_day -= timedelta(days=1)
            
            start_dt, end_dt = self._intraday_window(
                ref_date=prev_day,
                start=self.config.prev_window_start,
                end=self.config.prev_window_end,
            )

            try:
                candles: List[Candle] = provider.get_intraday_candles(
                    symbol=contract_symbol,
                    token=contract_token,
                    interval=self.config.candle_interval,
                    start=start_dt,
                    end=end_dt,
                )
                
                if candles:
                    # Found data! Calculate high/low and return
                    highs = [_as_decimal(c.high) for c in candles]
                    lows = [_as_decimal(c.low) for c in candles]
                    if attempt > 0:
                        # Log when we had to look back more than 1 day
                        from django.utils import timezone as dj_tz
                        import logging
                        logger = logging.getLogger(__name__)
                        logger.info(
                            f"Found previous-day data for {instrument.instrument} on {prev_day} "
                            f"(looked back {attempt + 1} trading days)"
                        )
                    return max(highs), min(lows)
                    
            except MarketDataError:
                # Data unavailable for this day, try further back
                pass
            
            # Move to the next previous day
            current_date = prev_day

        # If we've exhausted all attempts, raise an error
        raise StrategySkip(
            f"No previous-day candles found in 14:45–15:30 window for {instrument.instrument} "
            f"after searching {max_lookback_days} trading days back."
        )

    def _first_session_candle_open(
        self,
        *,
        provider: BaseMarketDataProvider,
        contract_symbol: str,
        contract_token: str,
    ) -> Optional[Decimal]:
        """Return the open of the first 5-min candle of the trading day (Step6)."""
        start_dt, end_dt = self._intraday_window(
            ref_date=self.market_date,
            start=self.config.session_start,
            end=(datetime.combine(self.market_date, self.config.session_start) + timedelta(minutes=5)).time(),
        )
        try:
            candles: List[Candle] = provider.get_intraday_candles(
                symbol=contract_symbol,
                token=contract_token,
                interval=self.config.candle_interval,
                start=start_dt,
                end=end_dt,
            )
        except MarketDataError:
            return None
        if not candles:
            return None
        return _as_decimal(candles[0].open)

    def _find_breakout_candle(
        self,
        *,
        provider: BaseMarketDataProvider,
        contract_symbol: str,
        contract_token: str,
        prev_high: Decimal,
    ) -> Optional[Candle]:
        """Steps 4–5: find first 5-min candle closing above prev_high from 09:15 onwards."""
        start_dt, end_dt = self._intraday_window(
            ref_date=self.market_date,
            start=self.config.session_start,
            end=time(15, 30),  # conservative end of session scan
        )
        try:
            candles: List[Candle] = provider.get_intraday_candles(
                symbol=contract_symbol,
                token=contract_token,
                interval=self.config.candle_interval,
                start=start_dt,
                end=end_dt,
            )
        except MarketDataError:
            return None

        for candle in candles:
            close_price = _as_decimal(candle.close)
            high_price = _as_decimal(candle.high)
            low_price = _as_decimal(candle.low)
            # candle body close above previous high
            if close_price > prev_high and high_price >= prev_high and low_price <= close_price:
                return candle
        return None

    def _process_instrument(
        self,
        *,
        instrument: Instrument,
        provider: BaseMarketDataProvider,
        execution_mode: str,
        order_executor: OrderExecutor,
    ) -> InstrumentRunSummary:
        """Execute Strategy One for a single instrument, possibly opening a trade.
        
        Dynamically fetches underlying index price at market open (9:15) and
        selects ATM PE/CE contracts from the Angel Broking scrip master.
        """
        summary = InstrumentRunSummary(instrument=instrument.instrument)

        # Step 1: Get underlying index price at 9:15 AM
        underlying_price = provider.get_underlying_price(instrument)
        if not underlying_price:
            raise StrategySkip(
                f"Unable to fetch underlying price for {instrument.instrument} at market open."
            )
        
        summary.price = underlying_price
        
        import logging
        logger = logging.getLogger(__name__)
        
        print(f"\n{'='*60}")
        print(f"📊 {instrument.instrument} Analysis for {self.market_date}")
        print(f"{'='*60}")
        print(f"Opening price at 9:15 AM: ₹{underlying_price}")
        
        logger.info(f"Underlying price for {instrument.instrument} at 9:15: {underlying_price}")
        
        # Step 2: Find ATM contracts dynamically from scrip master
        expiry_code = (instrument.contract_expiry_code or "").strip().upper() or None
        
        print(f"Expiry filter: {expiry_code if expiry_code else 'Nearest expiry'}")
        
        ce_contract, pe_contract = find_atm_contracts(
            underlying_name=instrument.instrument,
            underlying_price=underlying_price,
            expiry_date=expiry_code,
        )
        
        print(f"\n🔍 ATM Contracts Found:")
        if ce_contract:
            print(f"  CE: {ce_contract.symbol}")
            print(f"      Token: {ce_contract.token}")
            print(f"      Strike: ₹{ce_contract.strike}")
            print(f"      Expiry: {ce_contract.expiry}")
        else:
            print(f"  CE: Not found")
            
        if pe_contract:
            print(f"  PE: {pe_contract.symbol}")
            print(f"      Token: {pe_contract.token}")
            print(f"      Strike: ₹{pe_contract.strike}")
            print(f"      Expiry: {pe_contract.expiry}")
        else:
            print(f"  PE: Not found")
        
        if not ce_contract and not pe_contract:
            print(f"{'='*60}\n")
            raise StrategySkip(
                f"No ATM contracts found for {instrument.instrument} at price {underlying_price}"
            )
        
        # Strategy One: Trade BOTH CE and PE contracts (BUY only)
        print(f"\n✅ Selected Contracts for Trading (BUY both CE & PE):")
        
        contracts_to_trade = []
        if ce_contract:
            contracts_to_trade.append(("CE", ce_contract))
            print(f"   [1] CE Contract:")
            print(f"       Symbol: {ce_contract.symbol}")
            print(f"       Token: {ce_contract.token}")
            print(f"       Strike: ₹{ce_contract.strike}")
            print(f"       Transaction: BUY")
            logger.info(
                f"Selected CE contract for {instrument.instrument}: {ce_contract.symbol} "
                f"(token: {ce_contract.token}, strike: {ce_contract.strike})"
            )
        
        if pe_contract:
            contracts_to_trade.append(("PE", pe_contract))
            print(f"   [2] PE Contract:")
            print(f"       Symbol: {pe_contract.symbol}")
            print(f"       Token: {pe_contract.token}")
            print(f"       Strike: ₹{pe_contract.strike}")
            print(f"       Transaction: BUY")
            logger.info(
                f"Selected PE contract for {instrument.instrument}: {pe_contract.symbol} "
                f"(token: {pe_contract.token}, strike: {pe_contract.strike})"
            )
        
        print(f"{'='*60}\n")
        
        # Process both contracts and combine results
        total_opened = 0
        ce_summary = None
        pe_summary = None
        
        for option_type, contract in contracts_to_trade:
            try:
                contract_summary = self._process_instrument_contract(
                    instrument=instrument,
                    provider=provider,
                    execution_mode=execution_mode,
                    order_executor=order_executor,
                    contract_symbol=contract.symbol,
                    contract_token=contract.token,
                    summary_template=summary,
                    option_type=option_type,
                )
                
                if option_type == "CE":
                    ce_summary = contract_summary
                else:
                    pe_summary = contract_summary
                
                total_opened += contract_summary.opened
                
            except StrategySkip as e:
                logger.warning(f"Skipped {option_type} contract: {e}")
                print(f"⚠️  Skipped {option_type} contract: {e}\n")
            except Exception as e:
                logger.error(f"Error processing {option_type} contract: {e}", exc_info=True)
                print(f"❌ Error processing {option_type} contract: {e}\n")
        
        # Return combined summary (use CE summary as base, update opened count)
        final_summary = ce_summary or pe_summary or summary
        final_summary.opened = total_opened
        return final_summary

    def _process_instrument_contract(
        self,
        *,
        instrument: Instrument,
        provider: BaseMarketDataProvider,
        execution_mode: str,
        order_executor: OrderExecutor,
        contract_symbol: str,
        contract_token: str,
        summary_template: InstrumentRunSummary,
        option_type: str = "CE",
    ) -> InstrumentRunSummary:
        summary = InstrumentRunSummary(instrument=summary_template.instrument)

        # Step3: previous day's 14:45–15:30 high/low
        prev_high, prev_low = self._fetch_prev_day_high_low(
            provider=provider,
            instrument=instrument,
            contract_symbol=contract_symbol,
            contract_token=contract_token,
        )

        # Steps 4 & 5: find first candle that closes above prev_high
        breakout_candle = self._find_breakout_candle(
            provider=provider,
            contract_symbol=contract_symbol,
            contract_token=contract_token,
            prev_high=prev_high,
        )
        if not breakout_candle:
            summary.message = "No 5-min candle closed above previous high."
            return summary

        # Step6: determine if breakout candle is first candle of the day
        first_open = self._first_session_candle_open(
            provider=provider,
            contract_symbol=contract_symbol,
            contract_token=contract_token,
        )
        if first_open is None:
            raise StrategySkip("Unable to determine first candle of the day for contract.")

        breakout_open = _as_decimal(breakout_candle.open)
        breakout_high = _as_decimal(breakout_candle.high)
        breakout_low = _as_decimal(breakout_candle.low)

        is_first_candle = breakout_open == first_open

        if is_first_candle:
            if breakout_open > prev_high:
                prev_high = breakout_high
                prev_low = breakout_low
        # Step9: next candle open - previous low <= 40 filter
        next_open = _as_decimal(breakout_candle.close)
        if next_open - prev_low > self.config.max_open_minus_prev_low:
            summary.message = "Entry filter failed: distance from previous low > 40."
            return summary

        # Step10: place entry order at around next candle open
        quantity = (instrument.no_of_lots or 1) * (instrument.lot_size or 1)
        direction = instrument.transaction or Instrument.Transaction.BUY

        # Calculate SL and TP
        # Target: entry + 40 points (pl_points)
        target_price = next_open + Decimal("40")
        # Stop Loss: previous low (or entry - 40 as fallback)
        stop_loss_price = prev_low

        result = order_executor.place_entry_order(
            instrument=instrument,
            direction=direction,
            quantity=quantity,
            reference_price=next_open,
            contract_symbol=contract_symbol,
            contract_token=contract_token,
            target_price=target_price,
            stop_loss_price=stop_loss_price,
        )

        Trade.objects.create(
            user=self.user,
            strategy_code=self.STRATEGY_CODE,
            instrument=instrument,
            execution_mode=execution_mode,
            status=Trade.Status.OPEN,
            direction=direction,
            quantity=quantity,
            entry_price=next_open,
            entry_datetime=timezone.now(),
            contract_symbol=contract_symbol,
            contract_token=contract_token,
            external_entry_id=result.get("order_id", ""),
            target_price=target_price,
            stop_loss_price=stop_loss_price,
        )

        summary.opened = 1
        summary.price = next_open
        summary.message = "Entry order placed by Strategy One."
        return summary
