"""Contract metadata lookup - DEPRECATED.

This module is no longer used. All contract metadata is stored
directly in the Instrument model database fields:
- trading_symbol
- symbol_token
- exchange
- lot_size

No external JSON files or caches required.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class ContractMetadata:
    """Legacy contract metadata structure - kept for backward compatibility."""
    symbol: str
    token: str
    exchange: Optional[str] = None
    lot_size: Optional[int] = None


class ContractLookupError(RuntimeError):
    """Raised when instrument metadata cannot be loaded."""


def lookup_contract(symbol: str) -> Optional[ContractMetadata]:
    """Legacy function - returns None.
    
    Contract metadata should be retrieved from Instrument model fields:
    - instrument.trading_symbol
    - instrument.symbol_token
    - instrument.exchange
    - instrument.lot_size
    """
    return None
