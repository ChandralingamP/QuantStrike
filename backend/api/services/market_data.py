"""Market data providers for strategy execution."""
from __future__ import annotations

import json
import logging
import random
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Optional

from django.utils import timezone
from django.conf import settings

from ..models import Instrument, UserProfile

logger = logging.getLogger(__name__)

try:  # pragma: no cover - optional dependency for live trading
    from SmartApi import SmartConnect  # type: ignore
except Exception:  # pragma: no cover - SmartAPI not installed
    SmartConnect = None  # type: ignore


class MarketDataError(RuntimeError):
    """Raised when market data cannot be retrieved."""


@dataclass(frozen=True)
class EntrySnapshot:
    """Encapsulates market data needed for entry decisions."""

    price: Decimal
    previous_low: Optional[Decimal] = None
    next_open: Optional[Decimal] = None
    underlying_price: Optional[Decimal] = None


class BaseMarketDataProvider:
    """Abstract interface for fetching instrument pricing."""

    def get_price(self, instrument: Instrument) -> Decimal:
        raise NotImplementedError

    def get_underlying_price(self, instrument: Instrument) -> Optional[Decimal]:
        """Return the underlying index price for the instrument if available."""

        return None

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
            Instrument.InstrumentCode.NIFTY: "26000",
            Instrument.InstrumentCode.BANKNIFTY: "26009",
            Instrument.InstrumentCode.SENSEX: "1",
        }
        token = mapping.get(instrument.instrument)
        if not token:
            raise MarketDataError(f"No index token configured for {instrument.instrument}.")
        return token


class HistoricalDataUnavailable(MarketDataError):
    """Raised when historical data cannot be found."""


class FileHistoricalDataSource:
    """Loads historical quotes from JSON snapshots stored on disk."""

    def __init__(self, root: Path) -> None:
        self.root = root

    def _file_for(self, instrument: Instrument, market_date: date) -> Path:
        slug = instrument.instrument.upper()
        filename = f"{market_date:%Y%m%d}-{slug}.json"
        return self.root.joinpath(filename)

    def load_quote(self, instrument: Instrument, market_date: date) -> EntrySnapshot:
        path = self._file_for(instrument, market_date)
        if not path.exists():
            raise HistoricalDataUnavailable(f"Historical file missing: {path}")
        payload = json.loads(path.read_text(encoding="utf-8"))
        if "price" not in payload:
            raise HistoricalDataUnavailable(f"Historical payload missing price: {path}")
        price = Decimal(str(payload.get("price")))
        previous_low = payload.get("previous_low")
        next_open = payload.get("next_open")
        underlying = payload.get("underlying_price")
        return EntrySnapshot(
            price=price,
            previous_low=Decimal(str(previous_low)) if previous_low is not None else None,
            next_open=Decimal(str(next_open)) if next_open is not None else None,
            underlying_price=Decimal(str(underlying)) if underlying is not None else None,
        )


class HistoricalMarketDataProvider(BaseMarketDataProvider):
    """Serves quotes from a historical data source, with optional fallback."""

    def __init__(
        self,
        *,
        market_date: date,
        data_source: Optional[FileHistoricalDataSource] = None,
        fallback: Optional[BaseMarketDataProvider] = None,
    ) -> None:
        if data_source is None:
            root = getattr(settings, "HISTORICAL_DATA_ROOT", "")
            if not root:
                raise HistoricalDataUnavailable("HISTORICAL_DATA_ROOT is not configured.")
            data_source = FileHistoricalDataSource(Path(root))
        self.market_date = market_date
        self.data_source = data_source
        self.fallback = fallback

    def get_price(self, instrument: Instrument) -> Decimal:
        snapshot = self.data_source.load_quote(instrument, self.market_date)
        return snapshot.price

    def get_entry_snapshot(self, instrument: Instrument) -> EntrySnapshot:
        try:
            return self.data_source.load_quote(instrument, self.market_date)
        except HistoricalDataUnavailable as exc:
            if not self.fallback:
                raise
            logger.warning("Historical data missing (%s); using fallback provider.", exc)
            return self.fallback.get_entry_snapshot(instrument)

    def get_underlying_price(self, instrument: Instrument) -> Optional[Decimal]:
        try:
            snapshot = self.data_source.load_quote(instrument, self.market_date)
            return snapshot.underlying_price
        except HistoricalDataUnavailable:
            if self.fallback:
                return self.fallback.get_underlying_price(instrument)
            return None


def build_market_data_provider(
    *,
    profile: Optional[UserProfile],
    execution_mode: str,
    seed: Optional[int] = None,
    market_date: Optional[date] = None,
) -> BaseMarketDataProvider:
    if market_date and market_date < timezone.now().date():
        fallback = DemoMarketDataProvider(seed=seed or int(market_date.strftime("%Y%m%d")))
        try:
            return HistoricalMarketDataProvider(
                market_date=market_date,
                fallback=fallback,
            )
        except HistoricalDataUnavailable:
            logger.warning("Historical data unavailable for %s; falling back to demo feed.", market_date)
            return fallback
    if execution_mode == "live":
        fallback = DemoMarketDataProvider(seed=seed or int(timezone.now().timestamp()))
        return LiveMarketDataProvider(profile, fallback=fallback)
    return DemoMarketDataProvider(seed=seed)
