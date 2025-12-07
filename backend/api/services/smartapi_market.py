from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, DecimalException
from pathlib import Path
from typing import List, Optional

import requests
from django.conf import settings
from django.utils import timezone

from ..angel import AngelAPIError, build_headers

logger = logging.getLogger(__name__)

HISTORICAL_URL = "https://apiconnect.angelone.in/rest/secure/angelbroking/historical/v1/getCandleData"


class SmartAPIMarketError(RuntimeError):
    """Raised when SmartAPI market data cannot be retrieved."""


@dataclass(frozen=True)
class Candle:
    timestamp: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int


class SmartAPIMarketClient:
    """Lightweight SmartAPI client focused on historical candle retrieval."""

    def __init__(self, *, api_key: str, jwt_token: str) -> None:
        if not api_key or not jwt_token:
            raise SmartAPIMarketError("SmartAPI credentials are required for market data access.")
        self.api_key = api_key
        self.jwt_token = jwt_token

    def get_option_candles(
        self,
        *,
        exchange: str,
        symbol_token: str,
        interval: str,
        start: datetime,
        end: datetime,
    ) -> List[Candle]:
        fixture = self._load_fixture_candles(
            exchange=exchange,
            symbol_token=symbol_token,
            interval=interval,
            start=start,
        )
        if fixture is not None:
            return fixture

        payload = {
            "exchange": exchange,
            "symboltoken": str(symbol_token),
            "interval": interval,
            "fromdate": self._format_timestamp(start),
            "todate": self._format_timestamp(end),
        }

        response = self._post(HISTORICAL_URL, payload)
        if not response.get("status"):
            raise SmartAPIMarketError(response.get("message") or "SmartAPI returned an error response.")

        candles_raw = response.get("data") or []
        candles: List[Candle] = []
        for entry in candles_raw:
            try:
                timestamp = self._parse_timestamp(entry[0])
                candles.append(
                    Candle(
                        timestamp=timestamp,
                        open=Decimal(str(entry[1])),
                        high=Decimal(str(entry[2])),
                        low=Decimal(str(entry[3])),
                        close=Decimal(str(entry[4])),
                        volume=int(entry[5]) if len(entry) > 5 and entry[5] is not None else 0,
                    )
                )
            except (IndexError, ValueError, TypeError, DecimalException) as exc:  # type: ignore[name-defined]
                logger.debug("Skipping malformed candle entry %s: %s", entry, exc)
                continue

        candles.sort(key=lambda candle: candle.timestamp)
        return candles

    def _post(self, url: str, payload: dict) -> dict:
        headers = build_headers(api_key=self.api_key, bearer_token=self.jwt_token)
        timeout = float(getattr(settings, "ANGEL_API_TIMEOUT", 30))
        try:
            response = requests.post(url, headers=headers, json=payload, timeout=timeout)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as exc:  # pragma: no cover - network interaction
            raise SmartAPIMarketError(f"SmartAPI request failed: {exc}") from exc
        except ValueError as exc:  # pragma: no cover - invalid JSON
            raise SmartAPIMarketError("Invalid JSON received from SmartAPI.") from exc

    def _load_fixture_candles(
        self,
        *,
        exchange: str,
        symbol_token: str,
        interval: str,
        start: datetime,
    ) -> Optional[List[Candle]]:
        if not getattr(settings, "ANGEL_SANDBOX_ENABLED", False):
            return None
        root_value = getattr(settings, "HISTORICAL_DATA_ROOT", "")
        if not root_value:
            return None
        root = Path(root_value)
        path = root / "candles" / f"{exchange.upper()}-{symbol_token}-{interval}-{start.date().isoformat()}.json"
        if not path.exists():
            return None
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            logger.warning("Invalid candle fixture JSON at %s: %s", path, exc)
            return []

        candles: List[Candle] = []
        for entry in raw:
            try:
                timestamp = self._parse_timestamp(entry[0])
                candles.append(
                    Candle(
                        timestamp=timestamp,
                        open=Decimal(str(entry[1])),
                        high=Decimal(str(entry[2])),
                        low=Decimal(str(entry[3])),
                        close=Decimal(str(entry[4])),
                        volume=int(entry[5]) if len(entry) > 5 and entry[5] is not None else 0,
                    )
                )
            except (IndexError, ValueError, TypeError, DecimalException) as exc:  # type: ignore[name-defined]
                logger.debug("Skipping malformed candle fixture entry %s: %s", entry, exc)
                continue

        candles.sort(key=lambda candle: candle.timestamp)
        return candles

    def _format_timestamp(self, dt: datetime) -> str:
        aware = self._ensure_timezone(dt)
        return aware.strftime("%Y-%m-%d %H:%M")

    def _parse_timestamp(self, value: str) -> datetime:
        dt = datetime.fromisoformat(value)
        return self._ensure_timezone(dt)

    def _ensure_timezone(self, dt: datetime) -> datetime:
        tz = timezone.get_current_timezone()
        if dt.tzinfo is None:
            return timezone.make_aware(dt, tz)
        return dt.astimezone(tz)