"""Dynamic contract selection using locally cached scrip master data.

This module reads option contracts from local JSON files that are updated daily
via the update_scrip_master management command. Falls back to Angel Broking API
if local files are missing or stale (>24 hours old).

Performance: Local file read is ~100x faster than API call during trading hours.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

SCRIP_MASTER_URL = (
    "https://margincalculator.angelbroking.com/OpenAPI_File/files/"
    "OpenAPIScripMaster.json"
)

# Local file paths
INSTRUMENTS_FILE = settings.BASE_DIR / "data" / "instruments.json"
EXPIRIES_FILE = settings.BASE_DIR / "data" / "instruments_expiries.json"

# In-memory cache for scrip master data
_scrip_cache: Optional[List[Dict]] = None
_cache_timestamp: Optional[datetime] = None
CACHE_DURATION = timedelta(hours=24)  # Local files valid for 24 hours
FILE_MAX_AGE = timedelta(hours=24)  # Files older than this are considered stale


@dataclass
class ContractInfo:
    """Information about an option contract."""
    symbol: str
    token: str
    strike: Decimal
    expiry: str
    option_type: str  # CE or PE
    name: str
    exchange: str


def _fetch_scrip_master() -> List[Dict]:
    """Fetch scrip master from local files or Angel Broking API as fallback.
    
    Prioritizes local files for performance:
    1. Check in-memory cache (valid for 24 hours)
    2. Read from local JSON file (if exists and < 24 hours old)
    3. Fallback to API call (and update local files)
    """
    global _scrip_cache, _cache_timestamp
    
    now = datetime.now()
    
    # Check in-memory cache first
    if _scrip_cache and _cache_timestamp and (now - _cache_timestamp) < CACHE_DURATION:
        logger.debug("Using in-memory scrip master cache")
        return _scrip_cache
    
    # Try to load from local file
    if INSTRUMENTS_FILE.exists():
        file_age = now - datetime.fromtimestamp(INSTRUMENTS_FILE.stat().st_mtime)
        
        if file_age < FILE_MAX_AGE:
            try:
                logger.info(f"Loading scrip master from local file (age: {file_age.seconds // 3600}h)")
                with INSTRUMENTS_FILE.open("r", encoding="utf-8") as f:
                    data = json.load(f)
                
                _scrip_cache = data
                _cache_timestamp = now
                logger.info(f"Loaded {len(data)} instruments from local file")
                return data
            except Exception as exc:
                logger.warning(f"Failed to load local scrip file: {exc}, falling back to API")
        else:
            logger.warning(
                f"Local scrip file is stale (age: {file_age.seconds // 3600}h), "
                "falling back to API. Run 'python manage.py update_scrip_master' to update."
            )
    else:
        logger.warning(
            "Local scrip file not found. Run 'python manage.py update_scrip_master' to create it. "
            "Falling back to API..."
        )
    
    # Fallback: fetch from API
    logger.info("Fetching scrip master from Angel Broking API...")
    try:
        response = requests.get(SCRIP_MASTER_URL, timeout=120)
        response.raise_for_status()
        raw_data = response.json()
        
        # Convert to same format as our optimized local files
        data = _process_raw_scrip_data(raw_data)
        
        _scrip_cache = data
        _cache_timestamp = now
        logger.info(f"Fetched {len(data)} instruments from API")
        
        # Try to save to local file for future use
        try:
            INSTRUMENTS_FILE.parent.mkdir(parents=True, exist_ok=True)
            with INSTRUMENTS_FILE.open("w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            logger.info(f"Saved API data to {INSTRUMENTS_FILE}")
        except Exception as save_exc:
            logger.warning(f"Could not save API data to file: {save_exc}")
        
        return data
    except Exception as exc:
        logger.error(f"Failed to fetch scrip master from API: {exc}")
        if _scrip_cache:
            logger.warning("Using stale in-memory cache as last resort")
            return _scrip_cache
        raise


def _process_raw_scrip_data(raw_data: List[Dict]) -> List[Dict]:
    """Convert raw API data to our optimized format."""
    target_underlyings = {"NIFTY", "BANKNIFTY", "SENSEX"}
    processed = []
    
    for item in raw_data:
        name = (item.get("name") or "").upper().strip()
        if name not in target_underlyings:
            continue
        
        instrument_type = (item.get("instrumenttype") or "").upper()
        if instrument_type not in ("OPTIDX", "OPTSTK"):
            continue
        
        symbol = item.get("symbol", "")
        if not (symbol.endswith("CE") or symbol.endswith("PE")):
            continue
        
        try:
            strike_raw = item.get("strike", 0)
            if strike_raw == 0:
                continue
            strike = float(strike_raw)
        except (ValueError, TypeError):
            continue
        
        expiry_str = (item.get("expiry") or "").strip()
        if not expiry_str:
            continue
        
        processed.append({
            "token": str(item.get("token", "")),
            "symbol": symbol,
            "name": name,
            "expiry": expiry_str,
            "strike": str(strike),
            "lotsize": str(item.get("lotsize", "1")),
            "instrumenttype": instrument_type,
            "exch_seg": item.get("exch_seg", "NFO"),
            "tick_size": str(item.get("tick_size", "5.00")),
        })
    
    return processed


def _parse_expiry(expiry_str: str) -> Optional[datetime]:
    """Parse expiry date from various formats."""
    cleaned = (expiry_str or "").strip().upper()
    for fmt in ("%d%b%Y", "%d%b%y", "%d-%b-%Y", "%d-%b-%y"):
        try:
            return datetime.strptime(cleaned, fmt)
        except ValueError:
            continue
    return None


def _round_to_strike(price: Decimal, instrument_name: str) -> Decimal:
    """Round price to nearest strike based on instrument."""
    instrument_upper = instrument_name.upper()
    
    if "NIFTY" in instrument_upper and "BANK" not in instrument_upper:
        # NIFTY strikes are in multiples of 50
        strike_interval = Decimal("50")
    elif "BANKNIFTY" in instrument_upper or "BANKIFTY" in instrument_upper:
        # BANKNIFTY strikes are in multiples of 100
        strike_interval = Decimal("100")
    else:
        # Default to 50
        strike_interval = Decimal("50")
    
    rounded = round(price / strike_interval) * strike_interval
    return rounded


def _get_available_expiries(underlying_name: str, scrip_data: List[Dict]) -> List[str]:
    """Get unique sorted expiry dates for a given underlying from scrip data."""
    expiries = set()
    underlying_upper = underlying_name.upper().strip()
    
    for item in scrip_data:
        name = (item.get("name") or "").upper().strip()
        if name != underlying_upper:
            continue
        
        instrument_type = (item.get("instrumenttype") or "").upper()
        if instrument_type not in ("OPTIDX", "OPTSTK"):
            continue
        
        expiry_str = item.get("expiry", "")
        if expiry_str:
            expiries.add(expiry_str)
    
    # Sort by parsed date
    sorted_expiries = sorted(
        expiries,
        key=lambda x: _parse_expiry(x) or datetime.min
    )
    return sorted_expiries


def find_atm_contracts(
    underlying_name: str,
    underlying_price: Decimal,
    expiry_date: Optional[str] = None,
) -> Tuple[Optional[ContractInfo], Optional[ContractInfo]]:
    """Find ATM CE and PE contracts for the given underlying price.
    
    Args:
        underlying_name: Name of underlying (e.g., "NIFTY", "BANKNIFTY")
        underlying_price: Current price of the underlying index
        expiry_date: Specific expiry date string (e.g., "30DEC2025"), or None for nearest expiry
    
    Returns:
        Tuple of (CE contract, PE contract), either can be None if not found
    """
    scrip_data = _fetch_scrip_master()
    
    # Normalize underlying name
    underlying_upper = underlying_name.upper().strip()
    
    # Round to nearest strike
    atm_strike = _round_to_strike(underlying_price, underlying_upper)
    
    # Load expiries file to check if requested expiry exists
    expiry_to_use = expiry_date
    if expiry_date:
        expiry_requested_dt = _parse_expiry(expiry_date)
        if expiry_requested_dt:
            # Check if this expiry is in the past or doesn't exist
            today = datetime.now().date()
            if expiry_requested_dt.date() < today:
                logger.warning(
                    f"Requested expiry {expiry_date} is in the past. "
                    "Will use nearest future expiry instead."
                )
                expiry_to_use = None
            else:
                # Check if exact expiry exists in our data
                expiries_available = _get_available_expiries(underlying_upper, scrip_data)
                if expiry_date.upper() not in [e.upper() for e in expiries_available]:
                    logger.warning(
                        f"Exact expiry {expiry_date} not found for {underlying_upper}. "
                        f"Available: {expiries_available[:3]}. Will use nearest expiry."
                    )
                    expiry_to_use = None
    
    logger.info(
        f"Finding ATM contracts for {underlying_upper} at price {underlying_price}, "
        f"ATM strike: {atm_strike}, expiry: {expiry_to_use or 'nearest'}"
    )
    
    # Filter contracts for this underlying
    candidates = []
    for item in scrip_data:
        name = (item.get("name") or "").upper().strip()
        if name != underlying_upper:
            continue
        
        # Must be an option
        instrument_type = (item.get("instrumenttype") or "").upper()
        if instrument_type not in ("OPTIDX", "OPTSTK"):
            continue
        
        # Parse strike price - local files have it already processed
        try:
            strike_raw = Decimal(str(item.get("strike") or "0"))
            # Check if this is raw API data (needs division by 100) or processed data
            if strike_raw > 100000:  # Raw API data has strikes like 4800000
                strike = strike_raw / Decimal("100")
            else:  # Processed local file data has strikes like 48000.0
                strike = strike_raw
        except (ValueError, TypeError):
            continue
        
        if strike == 0:
            continue
        
        # Parse expiry
        expiry_str = item.get("expiry", "")
        expiry_dt = _parse_expiry(expiry_str)
        if not expiry_dt:
            continue
        
        # If specific expiry requested, filter by it
        if expiry_to_use:
            expiry_normalized = expiry_str.upper().strip()
            expiry_req_normalized = expiry_to_use.upper().strip()
            if expiry_normalized != expiry_req_normalized and expiry_dt.strftime("%d%b%Y").upper() != expiry_req_normalized:
                continue
        
        # Extract option type from symbol
        symbol = item.get("symbol", "")
        option_type = None
        if symbol.endswith("CE"):
            option_type = "CE"
        elif symbol.endswith("PE"):
            option_type = "PE"
        else:
            continue
        
        candidates.append({
            "symbol": symbol,
            "token": str(item.get("token", "")),
            "strike": strike,
            "expiry": expiry_str,
            "expiry_dt": expiry_dt,
            "option_type": option_type,
            "name": name,
            "exchange": item.get("exch_seg", "NFO"),
        })
    
    if not candidates:
        logger.warning(f"No option contracts found for {underlying_upper}")
        return None, None
    
    # Sort by expiry date (nearest first), then by strike distance from ATM
    candidates.sort(key=lambda x: (x["expiry_dt"], abs(x["strike"] - atm_strike)))
    
    # Try to find exact ATM strike first
    ce_contract = None
    pe_contract = None
    
    for candidate in candidates:
        if candidate["strike"] == atm_strike:
            if candidate["option_type"] == "CE" and ce_contract is None:
                ce_contract = ContractInfo(
                    symbol=candidate["symbol"],
                    token=candidate["token"],
                    strike=candidate["strike"],
                    expiry=candidate["expiry"],
                    option_type="CE",
                    name=candidate["name"],
                    exchange=candidate["exchange"],
                )
            elif candidate["option_type"] == "PE" and pe_contract is None:
                pe_contract = ContractInfo(
                    symbol=candidate["symbol"],
                    token=candidate["token"],
                    strike=candidate["strike"],
                    expiry=candidate["expiry"],
                    option_type="PE",
                    name=candidate["name"],
                    exchange=candidate["exchange"],
                )
            
            if ce_contract and pe_contract:
                break
    
    # If exact ATM not found, use nearest strike
    if not ce_contract or not pe_contract:
        logger.info(f"Exact ATM strike {atm_strike} not found, using nearest available strikes")
        
        for candidate in candidates:
            if candidate["option_type"] == "CE" and ce_contract is None:
                ce_contract = ContractInfo(
                    symbol=candidate["symbol"],
                    token=candidate["token"],
                    strike=candidate["strike"],
                    expiry=candidate["expiry"],
                    option_type="CE",
                    name=candidate["name"],
                    exchange=candidate["exchange"],
                )
            elif candidate["option_type"] == "PE" and pe_contract is None:
                pe_contract = ContractInfo(
                    symbol=candidate["symbol"],
                    token=candidate["token"],
                    strike=candidate["strike"],
                    expiry=candidate["expiry"],
                    option_type="PE",
                    name=candidate["name"],
                    exchange=candidate["exchange"],
                )
            
            if ce_contract and pe_contract:
                break
    
    if ce_contract:
        logger.info(f"Found CE contract: {ce_contract.symbol} (token: {ce_contract.token}, strike: {ce_contract.strike})")
    if pe_contract:
        logger.info(f"Found PE contract: {pe_contract.symbol} (token: {pe_contract.token}, strike: {pe_contract.strike})")
    
    return ce_contract, pe_contract
