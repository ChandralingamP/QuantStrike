from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone as dt_timezone
from decimal import Decimal, DecimalException
from pathlib import Path
from typing import List, Optional

import requests
from django.conf import settings
from django.utils import timezone

from ..angel import AngelAPIError, build_headers

logger = logging.getLogger(__name__)

HISTORICAL_URL = "https://apiconnect.angelone.in/rest/secure/angelbroking/historical/v1/getCandleData"
MARKET_QUOTE_URL = "https://apiconnect.angelone.in/rest/secure/angelbroking/market/v1/quote/"


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

        from_date_str = self._format_timestamp(start)
        to_date_str = self._format_timestamp(end)
        
        logger.info(f"SmartAPI getCandleData request: {exchange} {symbol_token} {interval} from {from_date_str} to {to_date_str}")

        payload = {
            "exchange": exchange,
            "symboltoken": str(symbol_token),
            "interval": interval,
            "fromdate": from_date_str,
            "todate": to_date_str,
        }
        
        # Small delay to avoid rate limiting on consecutive calls
        time.sleep(0.5)

        response = self._post(HISTORICAL_URL, payload)
        logger.info(f"🔍 SmartAPI Raw Response: {response}")
        
        if not response.get("status"):
            error_msg = response.get("message") or "SmartAPI returned an error response."
            logger.warning(f"SmartAPI error: {error_msg} - Response: {response}")
            raise SmartAPIMarketError(error_msg)

        candles_raw = response.get("data") or []
        print(f"📊 SmartAPI data field: {candles_raw}")
        logger.info(f"SmartAPI returned {len(candles_raw)} candles. Response: {response}")
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

    def get_ohlc(
        self,
        *,
        exchange: str,
        token: str,
    ) -> Optional[dict]:
        """Fetch OHLC (Open, High, Low, Close) data for the current day.
        
        Args:
            exchange: Exchange code (e.g., "NSE", "NFO")
            token: Symbol token
        
        Returns:
            dict with keys: ltp, open, high, low, close
            Example: {'ltp': 25942.1, 'open': 26063.35, 'high': 26106.8, 'low': 25920.3, 'close': 26042.3}
        """
        payload = {
            "mode": "OHLC",
            "exchangeTokens": {exchange: [str(token)]},
        }
        
        logger.info(f"📊 Fetching OHLC: exchange={exchange}, token={token}")
        response = self._post(MARKET_QUOTE_URL, payload)
        
        if not response.get("status"):
            error_msg = response.get("message") or "Failed to fetch OHLC data"
            logger.warning(f"OHLC fetch failed: {error_msg}")
            return None
        
        data = response.get("data", {})
        fetched = data.get("fetched", [])
        
        if not fetched:
            logger.warning(f"No OHLC data returned for {exchange}:{token}")
            return None
        
        quote = fetched[0]
        return {
            "ltp": quote.get("ltp"),
            "open": quote.get("open"),
            "high": quote.get("high"),
            "low": quote.get("low"),
            "close": quote.get("close"),
        }

    def get_ltp_batch(
        self,
        *,
        exchange_tokens: dict,
    ) -> dict:
        """Fetch Last Traded Price (LTP) for multiple symbols.
        
        Args:
            exchange_tokens: Dict mapping exchange to list of tokens
                            Example: {"NSE": ["99926000"], "NFO": ["51416", "51417"]}
        
        Returns:
            dict mapping exchange:token to ltp value
            Example: {"NSE:99926000": 26121.50, "NFO:51416": 450.25}
        """
        payload = {
            "mode": "LTP",
            "exchangeTokens": exchange_tokens,
        }
        
        logger.info(f"📊 Fetching LTP batch: {exchange_tokens}")
        response = self._post(MARKET_QUOTE_URL, payload)
        
        if not response.get("status"):
            error_msg = response.get("message") or "Failed to fetch LTP data"
            logger.warning(f"LTP batch fetch failed: {error_msg}")
            return {}
        
        data = response.get("data", {})
        fetched = data.get("fetched", [])
        
        ltp_map = {}
        for quote in fetched:
            exchange = quote.get("exchange")
            token = quote.get("symbolToken")
            ltp = quote.get("ltp")
            if exchange and token and ltp is not None:
                key = f"{exchange}:{token}"
                ltp_map[key] = Decimal(str(ltp))
        
        logger.info(f"✅ Fetched {len(ltp_map)} LTP values")
        return ltp_map

    def update_trades_pnl(self, trades: list) -> dict:
        """Update P&L for a list of open trades using LTP batch API.
        
        Args:
            trades: List of Trade model instances
        
        Returns:
            dict with update statistics
        """
        if not trades:
            return {"updated": 0, "errors": 0, "message": "No trades to update"}
        
        # Group trades by exchange
        exchange_tokens = {"NFO": [], "NSE": []}
        token_to_trades = {}  # Map tokens to trade objects
        
        for trade in trades:
            if not trade.contract_token:
                continue
            
            # Determine exchange (options are on NFO)
            exchange = "NFO" if trade.contract_symbol else "NSE"
            token = trade.contract_token
            
            if token not in exchange_tokens[exchange]:
                exchange_tokens[exchange].append(token)
            
            key = f"{exchange}:{token}"
            if key not in token_to_trades:
                token_to_trades[key] = []
            token_to_trades[key].append(trade)
        
        # Remove empty exchanges
        exchange_tokens = {k: v for k, v in exchange_tokens.items() if v}
        
        if not exchange_tokens:
            return {"updated": 0, "errors": 0, "message": "No valid tokens to fetch"}
        
        # Fetch LTP data
        ltp_map = self.get_ltp_batch(exchange_tokens=exchange_tokens)
        
        # Update trades
        updated_count = 0
        error_count = 0
        
        for key, ltp in ltp_map.items():
            if key not in token_to_trades:
                continue
            
            for trade in token_to_trades[key]:
                try:
                    trade.last_price = ltp
                    
                    # Calculate P&L if entry price exists
                    if trade.entry_price and trade.quantity:
                        if trade.direction == "BUY":
                            trade.pnl = (ltp - trade.entry_price) * trade.quantity
                        else:  # SELL
                            trade.pnl = (trade.entry_price - ltp) * trade.quantity
                    
                    trade.save(update_fields=['last_price', 'pnl', 'updated_at'])
                    updated_count += 1
                    logger.info(f"✅ Updated trade {trade.id}: LTP={ltp}, P&L={trade.pnl}")
                except Exception as e:
                    error_count += 1
                    logger.error(f"❌ Failed to update trade {trade.id}: {e}")
        
        return {
            "updated": updated_count,
            "errors": error_count,
            "total_ltps": len(ltp_map),
            "message": f"Updated {updated_count} trades with {len(ltp_map)} LTP values"
        }

    def _post(self, url: str, payload: dict, max_retries: int = 3) -> dict:
        headers = build_headers(api_key=self.api_key, bearer_token=self.jwt_token)
        timeout = float(getattr(settings, "ANGEL_API_TIMEOUT", 30))
        
        for attempt in range(max_retries):
            try:
                if attempt > 0:
                    # Exponential backoff: 1s, 2s, 4s
                    delay = 2 ** attempt
                    logger.info(f"⏳ Retry {attempt + 1}/{max_retries} after {delay}s delay...")
                    time.sleep(delay)
                
                print(f"📤 POST Request:")
                print(f"   URL: {url}")
                print(f"   Payload: {payload}")
                print(f"   Headers: {headers}")
                response = requests.post(url, headers=headers, json=payload, timeout=timeout)
                response.raise_for_status()
                result = response.json()
                print(f"📥 Response: {result}")
                return result
            except requests.HTTPError as exc:
                if exc.response.status_code == 403 and attempt < max_retries - 1:
                    logger.warning(f"⚠️  Rate limit hit (403), retrying... Attempt {attempt + 1}/{max_retries}")
                    continue
                raise SmartAPIMarketError(f"SmartAPI request failed: {exc}") from exc
            except requests.RequestException as exc:  # pragma: no cover - network interaction
                if attempt < max_retries - 1:
                    logger.warning(f"⚠️  Request failed: {exc}, retrying... Attempt {attempt + 1}/{max_retries}")
                    continue
                raise SmartAPIMarketError(f"SmartAPI request failed: {exc}") from exc
            except ValueError as exc:  # pragma: no cover - invalid JSON
                raise SmartAPIMarketError("Invalid JSON received from SmartAPI.") from exc
        
        raise SmartAPIMarketError(f"Failed after {max_retries} retry attempts")

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
        """Format datetime for SmartAPI.
        
        SmartAPI expects timestamps in IST (Asia/Kolkata timezone) format: "YYYY-MM-DD HH:MM"
        Do NOT convert to UTC - keep in IST.
        """
        aware = self._ensure_timezone(dt)
        # SmartAPI expects IST time, not UTC
        return aware.strftime("%Y-%m-%d %H:%M")

    def _parse_timestamp(self, value: str) -> datetime:
        try:
            if isinstance(value, str) and value.endswith("Z"):
                dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
            else:
                dt = datetime.fromisoformat(value)
        except (ValueError, AttributeError):
            raise ValueError(f"Unable to parse timestamp: {value}")
        if dt.tzinfo is None:
            tz = timezone.get_current_timezone()
            dt = timezone.make_aware(dt, tz)
        return dt.astimezone(timezone.get_current_timezone())

    def _ensure_timezone(self, dt: datetime) -> datetime:
        tz = timezone.get_current_timezone()
        if dt.tzinfo is None:
            return timezone.make_aware(dt, tz)
        return dt.astimezone(tz)