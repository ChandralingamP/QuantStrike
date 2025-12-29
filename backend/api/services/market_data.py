"""Market data providers for strategy execution."""
from __future__ import annotations

import logging
import random
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import List, Optional

from django.utils import timezone

from ..models import Instrument, UserProfile
from .smartapi_market import SmartAPIMarketClient, SmartAPIMarketError

logger = logging.getLogger(__name__)

try:  # pragma: no cover - optional dependency for live trading
    from SmartApi import SmartConnect  # type: ignore
except Exception:  # pragma: no cover - SmartAPI not installed
    SmartConnect = None  # type: ignore


class MarketDataError(RuntimeError):
    """Raised when market data cannot be retrieved."""


@dataclass(frozen=True)
class Candle:
    """Simple OHLCV candle used for strategy backtesting.

    This intentionally mirrors the shape of the historical files under
    docs/historical-data/ and can be produced from SmartAPI responses if
    intraday support is added later.
    """

    timestamp: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Optional[int] = None


@dataclass(frozen=True)
class EntrySnapshot:
    """Encapsulates market data needed for entry decisions."""

    price: Decimal
    previous_low: Optional[Decimal] = None
    next_open: Optional[Decimal] = None
    underlying_price: Optional[Decimal] = None


def iter_symbol_token_pairs(instrument: Instrument) -> List[tuple[str, str]]:
    """Yield candidate (symbol, token) pairs for an instrument.

    The ordering prefers explicitly configured symbols first, followed by
    dynamically selected CE/PE contracts. Tokens are resolved via metadata
    lookup when not persisted on the instrument.
    """

    primary_pairs = [
        (instrument.trading_symbol, instrument.symbol_token),
        (instrument.alternate_trading_symbol, instrument.alternate_symbol_token),
    ]
    daily_pairs = [
        (instrument.daily_ce_symbol, instrument.daily_ce_token),
        (instrument.daily_pe_symbol, instrument.daily_pe_token),
    ]
    if instrument.transaction == Instrument.Transaction.SELL:
        daily_pairs = list(reversed(daily_pairs))

    seen: set[tuple[str, str]] = set()
    ordered = primary_pairs + daily_pairs
    candidates: List[tuple[str, str]] = []

    for symbol_raw, token_raw in ordered:
        symbol = (symbol_raw or "").strip()
        if not symbol:
            continue

        token = (token_raw or "").strip()
        # Token must be configured in Instrument model fields
        # No automatic lookup from external files

        if not token or token == "0":
            continue

        key = (symbol.upper(), token)
        if key in seen:
            continue
        seen.add(key)
        candidates.append((symbol, token))

    return candidates


def resolve_symbol_token_pair(instrument: Instrument) -> Optional[tuple[str, str]]:
    pairs = iter_symbol_token_pairs(instrument)
    return pairs[0] if pairs else None


class BaseMarketDataProvider:
    """Abstract interface for fetching instrument pricing."""

    def get_price(self, instrument: Instrument) -> Decimal:
        raise NotImplementedError

    def get_underlying_price(self, instrument: Instrument) -> Optional[Decimal]:
        """Return the underlying index price for the instrument if available."""

        return None

    # --- Optional candle API used by OpeningRangeBreakoutEngine ----------

    def get_intraday_candles(
        self,
        *,
        symbol: str,
        token: str,
        interval: str,
        start: datetime,
        end: datetime,
    ) -> List[Candle]:
        """Return intraday candles for [start, end].

        Default implementation raises MarketDataError so that callers can
        gracefully skip when candle data is not wired for a given provider.
        """

        raise MarketDataError("Intraday candle data is not available for this provider.")

    def get_entry_snapshot(self, instrument: Instrument) -> EntrySnapshot:
        """Return pricing plus contextual levels for entry checks."""

        price = self.get_price(instrument)
        underlying = self.get_underlying_price(instrument)
        return EntrySnapshot(price=price, underlying_price=underlying)


class DemoMarketDataProvider(BaseMarketDataProvider):
    """Generates pseudo-random prices suitable for demo trading runs."""

    def __init__(self, *, seed: Optional[int] = None):
        self._random = random.Random(seed)

    def _base_price(self, instrument: Instrument) -> Decimal:
        if instrument.premium_price and instrument.premium_price > 0:
            return instrument.premium_price
        return Decimal("100.00")

    def _volatility(self, instrument: Instrument) -> float:
        points = max(
            instrument.pl_points or 0,
            instrument.sl_points or 0,
            instrument.trailing_points or 0,
            10,
        )
        return float(points)

    def _underlying_anchor(self, instrument: Instrument) -> Decimal:
        if instrument.instrument == Instrument.InstrumentCode.BANKNIFTY:
            return Decimal("48000")
        if instrument.instrument == Instrument.InstrumentCode.SENSEX:
            return Decimal("77000")
        return Decimal("23000")

    def get_price(self, instrument: Instrument) -> Decimal:
        base = self._base_price(instrument)
        spread = self._volatility(instrument)
        delta = Decimal(str(self._random.uniform(-spread, spread)))
        price = base + delta
        if price <= 0:
            price = base
        return price.quantize(Decimal("0.05"), rounding=ROUND_HALF_UP)

    def get_entry_snapshot(self, instrument: Instrument) -> EntrySnapshot:
        price = self.get_price(instrument)
        underlying = self.get_underlying_price(instrument)
        return EntrySnapshot(price=price, previous_low=None, next_open=None, underlying_price=underlying)

    def get_underlying_price(self, instrument: Instrument) -> Optional[Decimal]:
        anchor = self._underlying_anchor(instrument)
        jitter = Decimal(str(self._random.uniform(-150, 150)))
        value = anchor + jitter
        return value.quantize(Decimal("1"), rounding=ROUND_HALF_UP)

    # For backtesting via historical JSON, intraday candles are usually
    # served by HistoricalMarketDataProvider; Demo provider keeps the
    # BaseMarketDataProvider behaviour (no candles).


class LiveMarketDataProvider(BaseMarketDataProvider):
    """Attempts to retrieve live pricing via SmartAPI, with graceful fallback."""

    def __init__(
        self,
        profile: Optional[UserProfile],
        *,
        fallback: Optional[BaseMarketDataProvider] = None,
    ) -> None:
        self.profile = profile
        self.fallback = fallback
        self._client: Optional[SmartConnect] = None  # type: ignore[name-defined]

    def _fallback_price(self, instrument: Instrument) -> Decimal:
        if not self.fallback:
            raise MarketDataError("Live market data unavailable and no fallback configured.")
        logger.warning(
            "Falling back to demo pricing for %s due to unavailable live data.",
            instrument,
        )
        return self.fallback.get_price(instrument)

    def _ensure_client(self):  # pragma: no cover - SmartAPI path depends on external service
        if SmartConnect is None:
            raise MarketDataError("SmartAPI client is not installed.")
        if self._client is not None:
            return self._client
        if not self.profile or not self.profile.api_key:
            raise MarketDataError("User profile is missing SmartAPI credentials.")
        client = SmartConnect(api_key=self.profile.api_key)
        # SmartConnect requires a valid session to fetch LTP; we expect jwt_token to be current.
        if not self.profile.jwt_token or not self.profile.refresh_token:
            raise MarketDataError("SmartAPI tokens are unavailable; reconnect the brokerage account.")
        try:
            client.renewAccessToken(
                refreshToken=self.profile.refresh_token,
                jwtToken=self.profile.jwt_token,
            )
        except Exception as exc:
            raise MarketDataError(f"Unable to refresh SmartAPI session: {exc}") from exc
        self._client = client
        return client

    def get_price(self, instrument: Instrument) -> Decimal:
        try:
            client = self._ensure_client()
            exchange = instrument.exchange or "NFO"
            trading_symbol = instrument.trading_symbol or instrument.instrument
            if not instrument.symbol_token:
                raise MarketDataError(
                    f"Instrument {instrument.instrument} missing symbol token for live market data."
                )
            response = client.ltpData(  # type: ignore[attr-defined]
                exchange=exchange,
                tradingsymbol=trading_symbol,
                symboltoken=instrument.symbol_token,
            )
            ltp = response.get("data", {}).get("ltp") if isinstance(response, dict) else None
            if ltp is None:
                raise MarketDataError("SmartAPI response missing LTP.")
            price = Decimal(str(ltp))
            return price.quantize(Decimal("0.05"), rounding=ROUND_HALF_UP)
        except MarketDataError:
            return self._fallback_price(instrument)
        except Exception as exc:  # pragma: no cover - protective guard
            logger.warning("Live price fetch failed for %s: %s", instrument, exc)
            return self._fallback_price(instrument)

    def get_entry_snapshot(self, instrument: Instrument) -> EntrySnapshot:
        price = self.get_price(instrument)
        underlying = self.get_underlying_price(instrument)
        return EntrySnapshot(price=price, previous_low=None, underlying_price=underlying)

    def get_underlying_price(self, instrument: Instrument) -> Optional[Decimal]:
        try:
            client = self._ensure_client()
            response = client.ltpData(  # type: ignore[attr-defined]
                exchange="NSE",
                tradingsymbol=instrument.instrument,
                symboltoken=self._resolve_index_token(instrument),
            )
            ltp = response.get("data", {}).get("ltp") if isinstance(response, dict) else None
            if ltp is None:
                raise MarketDataError("SmartAPI response missing underlying LTP.")
            return Decimal(str(ltp)).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
        except Exception as exc:  # pragma: no cover - defensive guard
            logger.debug("Underlying price fallback for %s: %s", instrument.instrument, exc)
            if self.fallback:
                return self.fallback.get_underlying_price(instrument)
            return None

    def _resolve_index_token(self, instrument: Instrument) -> str:
        mapping = {
            Instrument.InstrumentCode.NIFTY: "99926000",
            Instrument.InstrumentCode.BANKNIFTY: "99926009",
            Instrument.InstrumentCode.SENSEX: "99919000",
        }
        token = mapping.get(instrument.instrument)
        if not token:
            raise MarketDataError(f"No index token configured for {instrument.instrument}.")
        return token


class HistoricalDataUnavailable(MarketDataError):
    """Raised when historical data cannot be found."""


class SmartAPIHistoricalProvider(BaseMarketDataProvider):
    """Direct SmartAPI candle provider for on-demand historical runs."""

    def __init__(self, *, profile: Optional[UserProfile]) -> None:
        self.profile = profile
        self._client: Optional[SmartAPIMarketClient] = None
        self._client_error = False

    def get_price(self, instrument: Instrument) -> Decimal:
        snapshot = self.get_entry_snapshot(instrument)
        return snapshot.price if snapshot else Decimal("0")

    def get_entry_snapshot(self, instrument: Instrument) -> EntrySnapshot:
        candles = self._fetch_candles_for_instrument(
            instrument=instrument,
            start=self._session_start(),
            end=self._session_start() + timedelta(minutes=5),
        )
        if not candles:
            raise MarketDataError("SmartAPI historical data unavailable for instrument.")
        first = candles[0]
        return EntrySnapshot(price=first.open)

    def get_intraday_candles(
        self,
        *,
        symbol: str,
        token: str,
        interval: str,
        start: datetime,
        end: datetime,
    ) -> List[Candle]:
        candles = self._fetch_candles(
            symbol=symbol,
            token=token,
            interval=interval,
            start=start,
            end=end,
            exchange=None,
        )
        if candles is None:
            raise MarketDataError("SmartAPI historical candles unavailable.")
        return candles

    def _fetch_candles_for_instrument(
        self,
        *,
        instrument: Instrument,
        start: datetime,
        end: datetime,
    ) -> Optional[List[Candle]]:
        pair = resolve_symbol_token_pair(instrument)
        if not pair:
            return None
        symbol, token = pair
        return self._fetch_candles(
            symbol=symbol,
            token=token,
            interval="FIVE_MINUTE",
            start=start,
            end=end,
            exchange=instrument.exchange,
        )

    def _fetch_candles(
        self,
        *,
        symbol: str,
        token: str,
        interval: str,
        start: datetime,
        end: datetime,
        exchange: Optional[str],
    ) -> Optional[List[Candle]]:
        client = self._ensure_client()
        if not client:
            return None
        resolved_exchange = exchange or self._exchange_for_slug(symbol)
        logger.info(
            "SmartAPI get_option_candles",
            extra={
                "exchange": resolved_exchange,
                "symbol_token": token,
                "interval": interval,
                "start": start.isoformat(),
                "end": end.isoformat(),
            },
        )
        try:
            api_candles = client.get_option_candles(
                exchange=resolved_exchange,
                symbol_token=token,
                interval=interval,
                start=start,
                end=end,
            )
        except SmartAPIMarketError as exc:
            logger.warning("SmartAPI fallback failed for %s (%s): %s", symbol, token, exc)
            return None

        tz = timezone.get_current_timezone()
        start_local = self._as_local(start, tz)
        end_local = self._as_local(end, tz)
        candles: List[Candle] = []
        for candle in api_candles:
            ts = candle.timestamp.astimezone(tz)
            if ts < start_local or ts > end_local:
                continue
            candles.append(
                Candle(
                    timestamp=ts,
                    open=candle.open,
                    high=candle.high,
                    low=candle.low,
                    close=candle.close,
                    volume=candle.volume,
                )
            )
        return candles

    def _resolve_token(self, instrument: Instrument) -> Optional[str]:
        pair = resolve_symbol_token_pair(instrument)
        return pair[1] if pair else None

    def _ensure_client(self) -> Optional[SmartAPIMarketClient]:
        if self._client_error:
            return None
        if self._client is not None:
            return self._client
        profile = self.profile
        if not profile or not profile.api_key or not profile.jwt_token:
            self._client_error = True
            return None
        try:
            self._client = SmartAPIMarketClient(
                api_key=profile.api_key,
                jwt_token=profile.jwt_token,
            )
            return self._client
        except SmartAPIMarketError as exc:
            logger.warning("Unable to create SmartAPI client: %s", exc)
            self._client_error = True
            return None

    @staticmethod
    def _exchange_for_slug(value: str) -> str:
        upper_value = str(value).upper()
        if upper_value.startswith("SENSEX"):
            return "BFO"
        return "NFO"

    @staticmethod
    def _session_start() -> datetime:
        today = timezone.localdate()
        dt = datetime.combine(today, time(9, 15))
        if timezone.is_naive(dt):
            return timezone.make_aware(dt)
        return dt

    @staticmethod
    def _as_local(value: datetime, tz) -> datetime:
        if value.tzinfo is None:
            return timezone.make_aware(value, tz)
        return value.astimezone(tz)


class HistoricalMarketDataProvider(BaseMarketDataProvider):
    """Serves quotes from SmartAPI for historical backtesting, with demo fallback."""

    def __init__(
        self,
        *,
        market_date: date,
        fallback: Optional[BaseMarketDataProvider] = None,
        profile: Optional[UserProfile] = None,
    ) -> None:
        if not profile or not profile.api_key or not profile.jwt_token:
            raise HistoricalDataUnavailable(
                "SmartAPI credentials required for historical data. Profile missing or incomplete."
            )
        self.market_date = market_date
        self.fallback = fallback
        self.profile = profile
        self._smart_client: Optional[SmartAPIMarketClient] = None
        self._smart_client_error = False

    def get_price(self, instrument: Instrument) -> Decimal:
        snapshot = self._fetch_live_snapshot(instrument)
        if snapshot:
            return snapshot.price
        raise HistoricalDataUnavailable(
            f"Unable to fetch price for {instrument}. "
            f"Please check your API connection or try reconnecting your brokerage account."
        )

    def get_entry_snapshot(self, instrument: Instrument) -> EntrySnapshot:
        snapshot = self._fetch_live_snapshot(instrument)
        if snapshot:
            return snapshot
        raise HistoricalDataUnavailable(
            f"Unable to fetch entry snapshot for {instrument}. "
            f"Please check your API connection or try reconnecting your brokerage account."
        )

    def get_underlying_price(self, instrument: Instrument) -> Optional[Decimal]:
        client = self._ensure_smart_client()
        if not client:
            raise HistoricalDataUnavailable(
                f"SmartAPI client not available. Please reconnect your brokerage account."
            )
        
        try:
            index_token = self._resolve_index_token(instrument)
            index_symbol = instrument.instrument or ""
            
            # Check if we're running for today (real-time) or past date (backtesting)
            from django.utils import timezone
            today = timezone.now().date()
            market_date = self.market_date.date() if hasattr(self.market_date, 'date') else self.market_date
            
            is_today = market_date == today
            
            if is_today:
                # Real-time trading: Use OHLC API for today's opening price
                logger.info(f"📊 Real-time mode: Fetching OHLC for {index_symbol} (token: {index_token})")
                ohlc_data = client.get_ohlc(exchange="NSE", token=index_token)
                
                if ohlc_data and ohlc_data.get("open") is not None:
                    underlying_price = Decimal(str(ohlc_data["open"]))
                    logger.info(f"✅ Found underlying opening price for {index_symbol}: ₹{underlying_price}")
                    logger.info(f"   OHLC Data - Open: {ohlc_data['open']}, High: {ohlc_data['high']}, "
                               f"Low: {ohlc_data['low']}, Close: {ohlc_data['close']}, LTP: {ohlc_data['ltp']}")
                    return underlying_price
                else:
                    raise HistoricalDataUnavailable(
                        f"No OHLC data available for {index_symbol}. "
                        f"The market might be closed or your API connection has expired."
                    )
            else:
                # Backtesting mode: Use historical candles API for past date at 9:15 AM
                logger.info(f"📈 Backtesting mode: Fetching historical candles for {index_symbol}")
                session_start = datetime.combine(self.market_date, time(9, 15))
                start_dt = session_start
                if timezone.is_naive(start_dt):
                    start_dt = timezone.make_aware(start_dt)
                end_dt = start_dt
                
                candles = self._fetch_live_candles(
                    symbol=index_symbol,
                    token=index_token,
                    interval="ONE_MINUTE",
                    start=start_dt,
                    end=end_dt,
                    exchange="NSE",
                )
                
                if candles:
                    underlying_price = Decimal(str(candles[0].open))
                    logger.info(f"✅ Found underlying price for {index_symbol} at {start_dt}: ₹{underlying_price}")
                    return underlying_price
                else:
                    raise HistoricalDataUnavailable(
                        f"No price data available for {index_symbol} at {start_dt}. "
                        f"The market might be closed or your API connection has expired."
                    )
        except HistoricalDataUnavailable:
            raise
        except Exception as exc:
            logger.error(f"SmartAPI fetch failed for {instrument.instrument}: {exc}", exc_info=True)
            raise HistoricalDataUnavailable(
                f"Failed to fetch underlying price for {instrument.instrument}: {exc}"
            ) from exc

    @staticmethod
    def _resolve_index_token(instrument: Instrument) -> str:
        """Map instrument to its NSE index token for SmartAPI."""
        mapping = {
            Instrument.InstrumentCode.NIFTY: "99926000",
            Instrument.InstrumentCode.BANKNIFTY: "99926009",
            Instrument.InstrumentCode.SENSEX: "99919000",
        }
        token = mapping.get(instrument.instrument)
        if not token:
            raise MarketDataError(f"No index token configured for {instrument.instrument}.")
        return token

    # SmartAPI helpers --------------------------------------------------

    def _fetch_live_snapshot(self, instrument: Instrument) -> Optional[EntrySnapshot]:
        client = self._ensure_smart_client()
        if not client:
            return None

        pair = resolve_symbol_token_pair(instrument)
        if not pair:
            return None
        symbol, token = pair

        exchange = instrument.exchange or self._exchange_for_slug(symbol)
        session_start = datetime.combine(self.market_date, time(9, 15))
        start_dt = session_start
        if timezone.is_naive(start_dt):
            start_dt = timezone.make_aware(start_dt)
        end_dt = start_dt + timedelta(minutes=5)

        candles = self._fetch_live_candles(
            symbol=symbol,
            token=token,
            interval="FIVE_MINUTE",
            start=start_dt,
            end=end_dt,
            exchange=exchange,
        )
        if not candles:
            return None

        first = candles[0]
        return EntrySnapshot(
            price=first.open,
            previous_low=None,
            next_open=None,
            underlying_price=None,
        )

    def _fetch_live_candles(
        self,
        *,
        symbol: str,
        token: str,
        interval: str,
        start: datetime,
        end: datetime,
        exchange: Optional[str] = None,
    ) -> Optional[List[Candle]]:
        client = self._ensure_smart_client()
        if not client:
            return None
        sanitized_token = token.strip()
        if not sanitized_token or sanitized_token == "0":
            return None

        resolved_exchange = exchange or self._exchange_for_slug(symbol)

        print(f"🔍 Fetching candles: exchange={resolved_exchange}, token={sanitized_token}, interval={interval}, start={start}, end={end}")
        
        try:
            api_candles = client.get_option_candles(
                exchange=resolved_exchange,
                symbol_token=sanitized_token,
                interval=interval,
                start=start,
                end=end,
            )
            print(f"✅ SmartAPI returned {len(api_candles) if api_candles else 0} candles")
        except SmartAPIMarketError as exc:
            print(f"❌ SmartAPI error: {exc}")
            logger.warning("SmartAPI candle fetch failed for %s (%s): %s", symbol, token, exc)
            return None

        tz = timezone.get_current_timezone()
        if start.tzinfo is None:
            start_local = timezone.make_aware(start, tz)
        else:
            start_local = start.astimezone(tz)
        if end.tzinfo is None:
            end_local = timezone.make_aware(end, tz)
        else:
            end_local = end.astimezone(tz)
        candles: List[Candle] = []
        for candle in api_candles:
            ts = candle.timestamp.astimezone(tz)
            if ts < start_local or ts > end_local:
                continue
            candles.append(
                Candle(
                    timestamp=ts,
                    open=candle.open,
                    high=candle.high,
                    low=candle.low,
                    close=candle.close,
                    volume=candle.volume,
                )
            )
        return candles

    def _ensure_smart_client(self) -> Optional[SmartAPIMarketClient]:
        if self._smart_client_error:
            return None
        if self._smart_client is not None:
            return self._smart_client
        profile = self.profile
        if not profile or not profile.api_key or not profile.jwt_token:
            self._smart_client_error = True
            return None
        try:
            self._smart_client = SmartAPIMarketClient(
                api_key=profile.api_key,
                jwt_token=profile.jwt_token,
            )
            return self._smart_client
        except SmartAPIMarketError as exc:
            logger.info("SmartAPI market client unavailable: %s", exc)
            self._smart_client_error = True
            return None

    @staticmethod
    def _exchange_for_slug(value: str) -> str:
        upper_value = str(value).upper()
        if upper_value.startswith("SENSEX"):
            return "BFO"
        return "NFO"

    def get_intraday_candles(
        self,
        *,
        symbol: str,
        token: str,
        interval: str,
        start: datetime,
        end: datetime,
    ) -> List[Candle]:
        candles = self._fetch_live_candles(
            symbol=symbol,
            token=token,
            interval=interval,
            start=start,
            end=end,
        )
        if candles is not None:
            return candles
        
        raise HistoricalDataUnavailable(
            f"Unable to fetch intraday candles for {symbol} ({token}). "
            f"Please check your API connection or try reconnecting your brokerage account."
        )


def build_market_data_provider(
    *,
    profile: Optional[UserProfile],
    execution_mode: str,
    seed: Optional[int] = None,
    market_date: Optional[date] = None,
) -> BaseMarketDataProvider:
    if market_date:
        # No fallback - fail fast if SmartAPI is not available
        return HistoricalMarketDataProvider(
            market_date=market_date,
            fallback=None,
            profile=profile,
        )
    
    # Both demo and live modes use REAL market data from Angel API
    # The only difference is order placement (simulated vs real)
    if execution_mode == "live" or execution_mode == "demo":
        # Use real market data for both demo and live trading
        return LiveMarketDataProvider(profile, fallback=None)
    
    # Fallback to simulated data only if mode is not specified
    return DemoMarketDataProvider(seed=seed)
