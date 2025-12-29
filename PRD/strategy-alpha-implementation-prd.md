# Strategy Alpha - Product Requirements Document

## Opening Range Breakout (ORB) Strategy

**Version:** 1.0  
**Last Updated:** December 27, 2025  
**Status:** Implemented  
**Strategy Code:** `strategy_alpha`

---

## 1. Executive Summary

Strategy Alpha is an intraday opening range breakout (ORB) trading strategy for Indian equity index options (NIFTY, BANKNIFTY, SENSEX). The strategy identifies momentum-based entry opportunities by analyzing previous trading day's price action and detecting breakouts during the current session.

**Key Characteristics:**

- **Type:** Intraday momentum breakout
- **Instruments:** NIFTY/BANKNIFTY/SENSEX weekly options (CE/PE)
- **Timeframe:** 5-minute candles
- **Execution Modes:** Demo (paper trading) and Live (Angel SmartAPI)
- **Trading Hours:** 09:15 IST - 15:30 IST
- **Timezone:** All times in IST (Asia/Kolkata, UTC+5:30)

---

## 2. Strategy Logic - 10-Step Process

### Step 1: Initialization & Precondition Checks

**Objective:** Validate trading environment and user configuration before execution.

**Implementation:**

- **Location:** `OpeningRangeBreakoutEngine.__init__()` and `run()`
- **Engine Class:** `OpeningRangeBreakoutEngine` in `backend/api/services/strategy_one.py`
- **Strategy Code:** `StrategyActivation.STRATEGY_ALPHA`

**Preconditions Checked:**

1. **Algo Configuration:**

   - `AlgoConfiguration.algo_active = True` (unless `ignore_activation=True` for backtesting)
   - `AlgoConfiguration.market_active = True` (required for live mode)

2. **Strategy Activation:**

   - `StrategyActivation.is_active = True` (for the user)
   - `StrategyActivation.strategy_code = "strategy_alpha"`

3. **Instrument Configuration:**

   - At least one active instrument assigned to user
   - `Instrument.active = True`
   - `Instrument.instrument` ∈ {NIFTY, BANKNIFTY, SENSEX}

4. **Contract Configuration:**

   - `Instrument.contract_expiry_code` must be set (e.g., "02JAN2026")
   - Valid trading symbol and token available
   - Lot size configured (`Instrument.lot_size`)
   - Lot count configured (`Instrument.no_of_lots`)

5. **Trading Day Validation:**

   - Market date must be a valid trading day (uses XBOM calendar)
   - Skips weekends and market holidays

6. **Brokerage Profile (Live Mode):**
   - `UserProfile.api_key` must be set
   - `UserProfile.jwt_token` must be valid
   - SmartAPI session active

**Code Flow:**

```python
def run(self) -> Dict[str, object]:
    # 1. Load algo configuration
    algo_config, _ = AlgoConfiguration.objects.get_or_create(user=self.user)

    # 2. Load strategy activation
    activation, _ = StrategyActivation.objects.get_or_create(
        user=self.user,
        strategy_code=self.STRATEGY_CODE,
    )

    # 3. Validate preconditions (unless backtesting with ignore_activation)
    if not self.ignore_activation:
        if not config.algo_active:
            raise StrategySkip("Algo is currently disabled.")
        if not activation.is_active:
            raise StrategySkip("Strategy Alpha is not active for this user.")

    # 4. Validate trading day
    if not self._is_trading_day(self.market_date):
        raise StrategySkip("Selected date is not a trading day.")

    # 5. Load active instruments
    qs = activation.selected_instruments.all().order_by("instrument")
    if not self.ignore_activation:
        qs = qs.filter(active=True)
```

**Error Handling:**

- Raises `StrategySkip` exception for validation failures
- Logs skip reason in `StrategyRunLog` with status `SKIPPED`
- Returns summary with status and message to caller

---

### Step 2: Market Data Provider Initialization

**Objective:** Establish connection to market data source based on execution mode and date.

**Implementation:**

- **Function:** `build_market_data_provider()` in `backend/api/services/market_data.py`
- **Provider Types:**
  - `HistoricalMarketDataProvider` - For backtesting with historical data
  - `LiveMarketDataProvider` - For real-time live trading
  - `DemoMarketDataProvider` - For demo/paper trading

**Provider Selection Logic:**

```python
def build_market_data_provider(
    *,
    profile: Optional[UserProfile],
    execution_mode: str,
    seed: Optional[int] = None,
    market_date: Optional[date] = None,
) -> BaseMarketDataProvider:

    # Historical data for any specified market_date (past or present)
    if market_date:
        fallback = DemoMarketDataProvider(seed=seed or int(market_date.strftime("%Y%m%d")))
        return HistoricalMarketDataProvider(
            market_date=market_date,
            fallback=fallback,
            profile=profile,  # For SmartAPI fallback
        )

    # Live trading with real-time data
    if execution_mode == "live":
        fallback = DemoMarketDataProvider(seed=seed or int(timezone.now().timestamp()))
        return LiveMarketDataProvider(profile, fallback=fallback)

    # Demo trading with synthetic data
    return DemoMarketDataProvider(seed=seed)
```

**Historical Data Source:**

1. **SmartAPI (Primary):**

   - Fetches real-time and historical candles via Angel SmartAPI
   - Requires valid `UserProfile.api_key` and `jwt_token`
   - Uses `SmartAPIMarketClient.get_option_candles()`
   - Fetches data on-demand for all historical and live scenarios

2. **Demo Provider (Fallback):**
   - Generates synthetic price data using seeded random numbers
   - Used only when SmartAPI credentials are unavailable or API fails

**Configuration:**

- No local JSON files required
- All historical data fetched via SmartAPI
- Demo mode for testing without API credentials

---

### Step 3: Contract Symbol & Token Resolution

**Objective:** Determine the exact option contract (symbol and token) to trade for each instrument.

**Implementation:**

- **Function:** `iter_symbol_token_pairs()` in `backend/api/services/market_data.py`
- **Called from:** `_process_instrument()` in strategy engine

**Contract Resolution Strategy:**
The system tries multiple contract candidates in priority order:

```python
def iter_symbol_token_pairs(instrument: Instrument) -> List[tuple[str, str]]:
    # Priority 1: Explicitly configured primary symbol
    primary_pairs = [
        (instrument.trading_symbol, instrument.symbol_token),
        (instrument.alternate_trading_symbol, instrument.alternate_symbol_token),
    ]

    # Priority 2: Daily selected CE/PE symbols
    daily_pairs = [
        (instrument.daily_ce_symbol, instrument.daily_ce_token),
        (instrument.daily_pe_symbol, instrument.daily_pe_token),
    ]

    # For SELL transactions, try PE first, then CE
    if instrument.transaction == Instrument.Transaction.SELL:
        daily_pairs = list(reversed(daily_pairs))

    # Combine and deduplicate
    ordered = primary_pairs + daily_pairs
    candidates = []
    seen = set()

    for symbol, token in ordered:
        if not symbol:
            continue

        # Auto-lookup token from metadata if missing
        if not token or token == "0":
            metadata = lookup_contract(symbol)  # from utils/contract_lookup.py
            token = metadata.token if metadata else ""

        pair = (symbol, token)
        if pair not in seen and symbol and token:
            candidates.append(pair)
            seen.add(pair)

    return candidates
```

**Contract Metadata Storage:**

- **Source:** Stored directly in the `Instrument` model database fields
- **Fields:**
  - `trading_symbol` - Primary contract symbol (e.g., "NIFTY02JAN2623850CE")
  - `symbol_token` - Token for API calls (e.g., "42501")
  - `exchange` - Exchange code ("NFO" or "BFO")
  - `lot_size` - Contracts per lot (75 for NIFTY, 35 for BANKNIFTY)
- **Note:** No external JSON files required, all metadata in database

**Contract Naming Convention:**

- Format: `{INDEX}{DDMMMYY}{STRIKE}{CE/PE}`
- Examples:
  - `NIFTY02JAN2623850CE` - NIFTY 23850 Call expiring Jan 2, 2026
  - `BANKNIFTY30DEC2547500CE` - BANKNIFTY 47500 Call expiring Dec 30, 2025

**Error Handling:**

- If no valid symbol/token pairs found: `StrategySkip("Instrument missing trading symbol/token")`
- Strategy tries each candidate contract in order
- First successful contract is used for trade execution

---

### Step 4: Previous Trading Day Calculation

**Objective:** Identify the most recent trading day before the current market date, accounting for weekends and holidays.

**Implementation:**

- **Function:** `_previous_trading_day()` in strategy engine
- **Uses:** `exchange_calendars` library with XBOM (Bombay Stock Exchange) calendar

**Algorithm:**

```python
def _previous_trading_day(self) -> date:
    if self._calendar is not None:  # XBOM calendar available
        try:
            previous = self._calendar.previous_session(self.market_date)
            return previous.date()
        except Exception:
            pass  # Fall through to simple logic

    # Fallback: Skip weekends only (Monday-Friday)
    candidate = self.market_date - timedelta(days=1)
    while candidate.weekday() >= 5:  # 5=Saturday, 6=Sunday
        candidate -= timedelta(days=1)
    return candidate
```

**Exchange Calendar Setup:**

```python
try:
    from exchange_calendars import get_calendar
    self._calendar = get_calendar("XBOM")  # Bombay Stock Exchange
except Exception:
    self._calendar = None  # Fallback to weekday-only logic
```

**Trading Day Validation:**

```python
def _is_trading_day(self, value: date) -> bool:
    if self._calendar is not None:
        try:
            return bool(self._calendar.is_session(value))
        except Exception:
            pass
    # Fallback: Monday-Friday
    return value.weekday() < 5
```

**Examples:**

- Market Date: 2025-12-26 (Thursday)
- Previous Date: 2025-12-25 (Christmas, holiday)
- **Previous Trading Day: 2025-12-24 (Tuesday)** ✓

**Why This Matters:**

- Previous trading day's high/low used as breakout reference
- Ensures strategy uses actual market data, not holiday gaps
- Critical for accurate breakout detection

---

### Step 5: Fetch Previous Day High/Low (Reference Range)

**Objective:** Calculate the previous trading day's high and low from 14:45-15:30 IST to establish breakout reference levels.

**Implementation:**

- **Function:** `_fetch_prev_day_high_low()` in strategy engine
- **Time Window:** 14:45-15:30 IST (last 45 minutes of previous trading day)
- **Candle Interval:** 5 minutes (FIVE_MINUTE)

**Configuration:**

```python
@dataclass
class StrategyOneConfig:
    candle_interval: str = "FIVE_MINUTE"
    prev_window_start: time = time(14, 45)  # 14:45 IST
    prev_window_end: time = time(15, 30)    # 15:30 IST
```

**Logic Flow:**

```python
def _fetch_prev_day_high_low(
    self,
    *,
    provider: BaseMarketDataProvider,
    instrument: Instrument,
    contract_symbol: str,
    contract_token: str,
) -> Tuple[Decimal, Decimal]:

    # 1. Get previous trading day
    prev_day = self._previous_trading_day()

    # 2. Build time window (14:45-15:30 on previous day)
    start_dt, end_dt = self._intraday_window(
        ref_date=prev_day,
        start=self.config.prev_window_start,  # 14:45
        end=self.config.prev_window_end,      # 15:30
    )

    # 3. Fetch 5-minute candles for the window
    try:
        candles: List[Candle] = provider.get_intraday_candles(
            symbol=contract_symbol,
            token=contract_token,
            interval=self.config.candle_interval,  # FIVE_MINUTE
            start=start_dt,
            end=end_dt,
        )
    except MarketDataError as exc:
        raise StrategySkip(f"Market data unavailable for {instrument.instrument}: {exc}")

    # 4. Validate candles exist
    if not candles:
        raise StrategySkip(
            f"No previous-day candles in 14:45–15:30 window for {instrument.instrument}."
        )

    # 5. Extract high/low across all candles
    highs = [_as_decimal(c.high) for c in candles]
    lows = [_as_decimal(c.low) for c in candles]

    return max(highs), min(lows)
```

**Expected Candle Data:**

- **Number of Candles:** 9-10 candles (14:45, 14:50, 14:55, ..., 15:25, 15:30)
- **Candle Structure:**
  ```python
  @dataclass
  class Candle:
      timestamp: datetime  # IST timezone-aware
      open: Decimal
      high: Decimal
      low: Decimal
      close: Decimal
      volume: Optional[int]
  ```

**Example:**

```
Previous Trading Day: 2025-12-24
Time Window: 14:45:00 - 15:30:00 IST

Candles:
  14:45 | O:145.50 H:148.25 L:144.00 C:147.80
  14:50 | O:147.80 H:150.10 L:146.50 C:149.30
  ...
  15:30 | O:156.20 H:157.85 L:155.60 C:157.30

Calculated:
  prev_high = 157.85  (max of all highs)
  prev_low  = 144.00  (min of all lows)
```

**Usage:**

- `prev_high`: Breakout threshold - price must close above this
- `prev_low`: Entry filter - used to validate gap distance

**Error Cases:**

- Market data unavailable → `StrategySkip`
- No candles in window → `StrategySkip`
- Both cause strategy to skip this instrument

---

### Step 6: Scan for Breakout Candle

**Objective:** Identify the first 5-minute candle during the current trading session that closes above the previous day's high.

**Implementation:**

- **Function:** `_find_breakout_candle()` in strategy engine
- **Scan Window:** 09:15-15:30 IST (full trading session)
- **Breakout Criteria:** Close price > prev_high

**Logic Flow:**

```python
def _find_breakout_candle(
    self,
    *,
    provider: BaseMarketDataProvider,
    contract_symbol: str,
    contract_token: str,
    prev_high: Decimal,
) -> Optional[Candle]:

    # 1. Build intraday scan window
    start_dt, end_dt = self._intraday_window(
        ref_date=self.market_date,
        start=self.config.session_start,  # 09:15
        end=time(15, 30),                 # 15:30
    )

    # 2. Fetch all 5-minute candles for current day
    try:
        candles: List[Candle] = provider.get_intraday_candles(
            symbol=contract_symbol,
            token=contract_token,
            interval=self.config.candle_interval,  # FIVE_MINUTE
            start=start_dt,
            end=end_dt,
        )
    except MarketDataError:
        return None

    # 3. Scan candles sequentially for breakout
    for candle in candles:
        close_price = _as_decimal(candle.close)
        high_price = _as_decimal(candle.high)
        low_price = _as_decimal(candle.low)

        # Breakout condition: close above previous high
        if close_price > prev_high and high_price >= prev_high and low_price <= close_price:
            return candle  # Return first matching candle

    return None  # No breakout found
```

**Breakout Detection Criteria:**

```python
# Valid breakout conditions (ALL must be true):
1. close_price > prev_high           # Closed above previous high
2. high_price >= prev_high           # Candle touched/exceeded previous high
3. low_price <= close_price          # Valid candle structure (low <= close)
```

**Example Scenarios:**

**Scenario A: Valid Breakout**

```
Previous High: 157.85

Current Day Candles:
  09:15 | O:142.50 H:145.20 L:141.80 C:144.30  ← No breakout
  09:20 | O:144.30 H:146.80 L:143.50 C:145.90  ← No breakout
  09:25 | O:145.90 H:148.40 L:145.10 C:147.60  ← No breakout
  09:30 | O:147.60 H:150.20 L:146.90 C:149.30  ← No breakout
  09:35 | O:149.30 H:152.10 L:148.80 C:151.20  ← No breakout
  09:40 | O:151.20 H:154.60 L:150.70 C:153.80  ← No breakout
  09:45 | O:153.80 H:156.90 L:153.20 C:155.90  ← No breakout
  09:50 | O:155.90 H:159.20 L:155.30 C:158.40  ← BREAKOUT! ✓
          close (158.40) > prev_high (157.85)
```

**Scenario B: No Breakout**

```
Previous High: 157.85

Current Day Candles:
  09:15 | O:142.50 H:145.20 L:141.80 C:144.30  ← Below prev_high
  09:20 | O:144.30 H:146.80 L:143.50 C:145.90  ← Below prev_high
  ...
  15:25 | O:155.00 H:156.50 L:154.20 C:155.80  ← Below prev_high
  15:30 | O:155.80 H:157.20 L:155.10 C:156.50  ← Below prev_high

Result: No breakout detected, strategy skips this instrument
```

**Return Value:**

- `Candle` object if breakout found (first qualifying candle)
- `None` if no breakout during session

**Post-Breakout:**

- If no breakout: Strategy returns with message "No 5-min candle closed above previous high."
- If breakout found: Proceeds to Step 7 (First Candle Check)

---

### Step 7: First Candle of Day Check

**Objective:** Determine if the breakout candle is the first candle of the trading session (09:15-09:20 IST). If yes, adjust reference levels.

**Implementation:**

- **Function:** `_first_session_candle_open()` in strategy engine
- **Purpose:** Special handling for gap-up openings

**Logic Flow:**

```python
def _first_session_candle_open(
    self,
    *,
    provider: BaseMarketDataProvider,
    contract_symbol: str,
    contract_token: str,
) -> Optional[Decimal]:

    # 1. Define first candle window (09:15-09:20)
    start_dt, end_dt = self._intraday_window(
        ref_date=self.market_date,
        start=self.config.session_start,  # 09:15
        end=(datetime.combine(
            self.market_date,
            self.config.session_start
        ) + timedelta(minutes=5)).time(),  # 09:20
    )

    # 2. Fetch first candle
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

    # 3. Return open price of first candle
    if not candles:
        return None
    return _as_decimal(candles[0].open)
```

**First Candle Logic in Main Flow:**

```python
# After finding breakout candle:

# 1. Get first candle open price
first_open = self._first_session_candle_open(
    provider=provider,
    contract_symbol=contract_symbol,
    contract_token=contract_token,
)

if first_open is None:
    raise StrategySkip("Unable to determine first candle of the day for contract.")

# 2. Extract breakout candle prices
breakout_open = _as_decimal(breakout_candle.open)
breakout_high = _as_decimal(breakout_candle.high)
breakout_low = _as_decimal(breakout_candle.low)

# 3. Check if breakout IS the first candle
is_first_candle = (breakout_open == first_open)

# 4. Adjust reference levels if first candle AND gaps above prev_high
if is_first_candle:
    if breakout_open > prev_high:
        # Gap-up opening: Use first candle's range as new reference
        prev_high = breakout_high
        prev_low = breakout_low
```

**Why This Matters:**

**Case 1: Normal Breakout (Not First Candle)**

```
Previous Day: prev_high = 157.85, prev_low = 144.00

Current Day:
  09:15 | O:142.50 H:145.20 L:141.80 C:144.30  ← First candle, no breakout
  09:20 | O:144.30 H:146.80 L:143.50 C:145.90
  ...
  09:50 | O:155.90 H:159.20 L:155.30 C:158.40  ← Breakout candle

is_first_candle = False  (breakout_open 155.90 ≠ first_open 142.50)
prev_high = 157.85  (unchanged)
prev_low = 144.00   (unchanged)
```

**Case 2: Gap-Up Opening (First Candle IS Breakout)**

```
Previous Day: prev_high = 157.85, prev_low = 144.00

Current Day:
  09:15 | O:160.00 H:162.30 L:159.10 C:161.50  ← First candle AND breakout!
                                                  Opens above prev_high (160 > 157.85)

is_first_candle = True  (breakout_open 160.00 == first_open 160.00)
breakout_open (160.00) > prev_high (157.85)

Updated reference levels:
  prev_high = 162.30  (breakout_high) ✓
  prev_low = 159.10   (breakout_low)  ✓
```

**Rationale:**

- Gap-up openings indicate strong momentum
- Using first candle's range prevents immediate entry on gap
- Provides tighter, more relevant reference levels for the day

---

### Step 8: Entry Price Determination

**Objective:** Calculate the entry price for the trade based on the breakout candle.

**Implementation:**

- **Entry Price:** Close price of the breakout candle
- **Represents:** Expected fill price at next candle's open (approximation)

**Logic:**

```python
# After finding and validating breakout candle:

# Entry price = close of breakout candle
next_open = _as_decimal(breakout_candle.close)

# This represents the price at which we expect to enter
# on the next candle after breakout confirmation
```

**Example:**

```
Breakout Candle (09:50):
  Open:  155.90
  High:  159.20
  Low:   155.30
  Close: 158.40  ← Entry Price

Entry Price: ₹158.40
```

**Rationale:**

- Strategy confirms breakout at candle close
- Next candle's open becomes entry point
- Using breakout close approximates next open
- Realistic for 5-minute intervals with momentum

**In Production:**

- Demo mode: Uses this calculated price directly
- Live mode: Places market order, actual fill may vary

---

### Step 9: Entry Filter - Gap Validation (40-Point Rule)

**Objective:** Ensure entry point is within acceptable distance from previous day's low to avoid chasing extended moves.

**Implementation:**

- **Function:** Part of `_process_instrument_contract()` logic
- **Rule:** `(next_open - prev_low) <= 40 points`

**Configuration:**

```python
@dataclass
class StrategyOneConfig:
    max_open_minus_prev_low: Decimal = Decimal("40")
```

**Logic Flow:**

```python
# After determining entry price (next_open)

# Calculate distance from previous low
gap = next_open - prev_low

# Validate 40-point rule
if gap > self.config.max_open_minus_prev_low:  # 40 points
    summary.message = "Entry filter failed: distance from previous low > 40."
    return summary  # Skip trade for this instrument
```

**Examples:**

**Example 1: Valid Entry (Within 40 Points)**

```
Previous Low:  144.00
Entry Price:   158.40
Gap:           158.40 - 144.00 = 14.40 points ✓

14.40 <= 40  → PASS → Trade proceeds
```

**Example 2: Invalid Entry (Exceeds 40 Points)**

```
Previous Low:  144.00
Entry Price:   190.50
Gap:           190.50 - 144.00 = 46.50 points ✗

46.50 > 40  → FAIL → Trade rejected
Message: "Entry filter failed: distance from previous low > 40."
```

**Example 3: Gap-Up Adjusted Reference**

```
Original Previous Low:  144.00
Adjusted Previous Low:  159.10  (from first candle gap-up)
Entry Price:            161.50
Gap:                    161.50 - 159.10 = 2.40 points ✓

2.40 <= 40  → PASS → Trade proceeds
```

**Rationale:**

- Prevents entering overextended moves
- Risk management: Limits distance to logical stop loss
- 40-point threshold balances opportunity vs. risk
- Adjusted for gap-up scenarios (Step 7)

**Risk Implications:**

- Small gap = Tighter stop loss = Better R:R ratio
- Large gap = Potential for bigger loss if reversal
- Filter protects capital during momentum exhaustion

---

### Step 10: Order Execution & Trade Logging

**Objective:** Place entry order and create trade record in database.

**Implementation:**

- **Order Executor:** `OrderExecutor` class in `backend/api/services/strategy_alpha.py`
- **Trade Model:** `Trade` in `backend/api/models.py`

#### 10.1 Order Placement

**Function Call:**

```python
result = order_executor.place_entry_order(
    instrument=instrument,
    direction=direction,                    # BUY or SELL
    quantity=quantity,                      # lots × lot_size
    reference_price=next_open,              # Entry price
    contract_symbol=contract_symbol,        # e.g., "NIFTY02JAN2623850CE"
    contract_token=contract_token,          # e.g., "42501"
)
```

**Quantity Calculation:**

```python
quantity = (instrument.no_of_lots or 1) * (instrument.lot_size or 1)

# Example:
# NIFTY: no_of_lots=1, lot_size=75 → quantity=75
# BANKNIFTY: no_of_lots=3, lot_size=35 → quantity=105
```

**Direction:**

```python
direction = instrument.transaction or Instrument.Transaction.BUY
# Defaults to BUY, can be configured to SELL
```

#### 10.2 Order Executor Logic

**Demo Mode:**

```python
def place_entry_order(self, ...):
    if not self.is_live:  # Demo mode
        # Generate synthetic order ID
        order_id = f"demo-entry-{uuid4().hex}"

        self.logger.info(
            "Demo entry: %s %s x%d @ %s",
            direction, contract_symbol, quantity, reference_price
        )

        return {
            "order_id": order_id,
            "status": "complete",
            "average_price": str(reference_price),
        }
```

**Live Mode:**

```python
def place_entry_order(self, ...):
    if self.is_live:
        # Validate brokerage credentials
        self._ensure_live_ready()

        # Place market order via Angel SmartAPI
        response = place_order(
            api_key=self.profile.api_key,
            jwt_token=self.profile.jwt_token,
            variety="NORMAL",
            trading_symbol=contract_symbol,
            symbol_token=contract_token,
            transaction_type=direction.upper(),  # BUY/SELL
            order_type="MARKET",
            quantity=quantity,
            product_type="INTRADAY",
            price="0",
            duration="DAY",
        )

        return {
            "order_id": response.get("orderid", ""),
            "status": response.get("status", ""),
            "average_price": response.get("averageprice", "0"),
        }
```

#### 10.3 Trade Database Record

**Trade Creation:**

```python
Trade.objects.create(
    # User & Strategy
    user=self.user,
    strategy_code=self.STRATEGY_CODE,  # "strategy_alpha"
    instrument=instrument,              # Foreign key to Instrument

    # Execution Details
    execution_mode=execution_mode,      # "demo" or "live"
    status=Trade.Status.OPEN,           # Initially OPEN

    # Trade Parameters
    direction=direction,                # BUY or SELL
    quantity=quantity,                  # Total contracts
    entry_price=next_open,              # Entry price (Decimal)
    entry_datetime=timezone.now(),      # Entry timestamp (IST)

    # Contract Details
    contract_symbol=contract_symbol,    # Full symbol string
    contract_token=contract_token,      # Token for API calls

    # External References
    external_entry_id=result.get("order_id", ""),  # Broker order ID

    # Optional Fields (initially None)
    exit_price=None,
    exit_datetime=None,
    target_price=None,
    stop_loss_price=None,
    trailing_stop_price=None,
    last_price=None,
    pnl=Decimal("0"),
    external_exit_id="",
    notes="",
)
```

**Trade Model Fields:**

```python
class Trade(models.Model):
    # Identity
    id: int                                    # Auto PK
    user: ForeignKey[User]                     # Owner
    strategy_code: str                         # "strategy_alpha"
    instrument: ForeignKey[Instrument]         # NIFTY/BANKNIFTY/etc

    # Status
    execution_mode: str                        # "demo" | "live"
    status: str                                # "open" | "closed" | "cancelled" | "error"

    # Trade Details
    direction: str                             # "BUY" | "SELL"
    quantity: int                              # Number of contracts
    entry_price: Decimal                       # Entry price
    exit_price: Decimal | None                 # Exit price (when closed)
    entry_datetime: datetime | None            # Entry timestamp
    exit_datetime: datetime | None             # Exit timestamp

    # Risk Management
    target_price: Decimal | None               # Take profit level
    stop_loss_price: Decimal | None            # Stop loss level
    trailing_stop_price: Decimal | None        # Trailing stop level
    last_price: Decimal | None                 # Current market price
    pnl: Decimal                               # Profit/Loss

    # Contract
    contract_symbol: str                       # Full contract symbol
    contract_token: str                        # API token

    # External References
    external_entry_id: str                     # Broker entry order ID
    external_exit_id: str                      # Broker exit order ID

    # Metadata
    notes: str                                 # Additional notes
    created_at: datetime                       # Record creation
    updated_at: datetime                       # Last update
```

#### 10.4 Summary Update

**Instrument Summary:**

```python
summary.opened = 1
summary.price = next_open
summary.message = "Entry order placed by Strategy One."
return summary
```

**Run Summary Aggregation:**

```python
summary = {
    "status": "completed",
    "mode": execution_mode,
    "opened_trades": 0,      # Sum of all instruments
    "closed_trades": 0,      # Sum of all instruments
    "instrument_summaries": [],  # List of per-instrument results
}

for instrument in instruments:
    instrument_summary = self._process_instrument(...)
    summary["opened_trades"] += instrument_summary.opened
    summary["closed_trades"] += instrument_summary.closed
    summary["instrument_summaries"].append(instrument_summary.as_dict())
```

**Example Output:**

```json
{
  "status": "completed",
  "mode": "demo",
  "opened_trades": 2,
  "closed_trades": 0,
  "instrument_summaries": [
    {
      "instrument": "NIFTY",
      "opened": 1,
      "closed": 0,
      "price": "158.40",
      "message": "Entry order placed by Strategy One."
    },
    {
      "instrument": "BANKNIFTY",
      "opened": 1,
      "closed": 0,
      "price": "209.90",
      "message": "Entry order placed by Strategy One."
    }
  ]
}
```

#### 10.5 Strategy Run Log

**Database Record:**

```python
run_log = StrategyRunLog.objects.create(
    user=self.user,
    strategy_code=self.STRATEGY_CODE,
    status=StrategyRunLog.Status.RUNNING,
    message="",
    extra={},
)

# On completion:
run_log.mark_completed(extra=summary)
```

**StrategyRunLog Model:**

```python
class StrategyRunLog(models.Model):
    user: ForeignKey[User]
    strategy_code: str
    status: str  # "running" | "completed" | "failed" | "skipped"
    message: str
    extra: dict  # JSON field with run summary
    created_at: datetime
    completed_at: datetime | None
```

---

## 3. Technical Architecture

### 3.1 File Structure

```
backend/api/
├── services/
│   ├── strategy_one.py          # OpeningRangeBreakoutEngine (main logic)
│   ├── strategy_alpha.py        # OrderExecutor, helpers
│   ├── market_data.py           # Market data providers
│   └── smartapi_market.py       # SmartAPI client
├── management/commands/
│   └── run_strategy_one.py      # CLI command for execution
├── models.py                    # Database models (includes contract metadata)
├── views.py                     # API endpoints
└── urls.py                      # URL routing
```

### 3.2 Database Models

**AlgoConfiguration:**

```python
class AlgoConfiguration(models.Model):
    user: ForeignKey[User]
    algo_active: bool              # Master algo toggle
    market_active: bool            # Live trading permission
```

**StrategyActivation:**

```python
class StrategyActivation(models.Model):
    user: ForeignKey[User]
    strategy_code: str             # "strategy_alpha"
    is_active: bool                # Strategy enable/disable
    execution_mode: str            # Default: "demo" or "live"
    selected_instruments: ManyToMany[Instrument]
```

**Instrument:**

```python
class Instrument(models.Model):
    user: ForeignKey[User]
    instrument: str                # NIFTY/BANKNIFTY/SENSEX
    active: bool

    # Contract Configuration
    contract_expiry_code: str      # e.g., "02JAN2026"
    trading_symbol: str            # Primary CE symbol
    symbol_token: str              # Primary CE token
    alternate_trading_symbol: str  # Primary PE symbol
    alternate_symbol_token: str    # Primary PE token
    daily_ce_symbol: str           # Daily selected CE
    daily_ce_token: str
    daily_pe_symbol: str           # Daily selected PE
    daily_pe_token: str

    # Trading Parameters
    transaction: str               # "BUY" or "SELL"
    lot_size: int
    no_of_lots: int

    # Exchange
    exchange: str                  # "NFO" or "BFO"
```

**Trade:**

```python
class Trade(models.Model):
    # Core
    user: ForeignKey[User]
    strategy_code: str
    instrument: ForeignKey[Instrument]
    execution_mode: str
    status: str

    # Trade Details
    direction: str
    quantity: int
    entry_price: Decimal
    exit_price: Decimal | None
    entry_datetime: datetime | None
    exit_datetime: datetime | None

    # Risk Management
    target_price: Decimal | None
    stop_loss_price: Decimal | None
    trailing_stop_price: Decimal | None
    pnl: Decimal

    # Contract
    contract_symbol: str
    contract_token: str

    # External
    external_entry_id: str
    external_exit_id: str
```

### 3.3 API Endpoints

**Strategy Execution:**

```
POST /api/strategy/alpha/run
POST /api/strategy/one/backtest/
```

**Request Body:**

```json
{
  "username": "chandralingam",
  "mode": "demo",
  "market_date": "2025-12-26"
}
```

**Response:**

```json
{
  "status": "completed",
  "mode": "demo",
  "opened_trades": 2,
  "closed_trades": 0,
  "instrument_summaries": [
    {
      "instrument": "NIFTY",
      "opened": 1,
      "closed": 0,
      "price": "158.40",
      "message": "Entry order placed by Strategy One."
    }
  ]
}
```

### 3.4 CLI Command

**Execution:**

```bash
python manage.py run_strategy_one <username> --mode <demo|live> --market-date <YYYY-MM-DD>
```

**Examples:**

```bash
# Demo backtest for specific date
python manage.py run_strategy_one chandralingam --mode demo --market-date 2025-12-26

# Live trading (today)
python manage.py run_strategy_one chandralingam --mode live

# Multi-day backtest
python manage.py run_strategy_one chandralingam --mode demo \
    --start-date 2025-12-01 --end-date 2025-12-31
```

---

## 4. Data Requirements

### 4.1 SmartAPI Integration

**Primary Data Source:**
All historical and live market data is fetched via Angel SmartAPI in real-time.

**Endpoints Used:**

- `getCandleData` - Historical and intraday candle data
- `ltpData` - Live and historical quotes
- `placeOrder` - Order placement (live mode)

**Authentication:**

- `api_key` - Angel API key
- `jwt_token` - Session token (from login)
- Stored in `UserProfile` model

**Candle Data Request:**

```python
# Fetch 5-minute candles for specific date range
candles = client.get_option_candles(
    exchange="NFO",
    symbol_token="42501",
    interval="FIVE_MINUTE",
    start=datetime(2025, 12, 26, 9, 15),
    end=datetime(2025, 12, 26, 15, 30),
)
```

**Timestamp Format:**

- Send: UTC ISO 8601 with Z designator
- Example: `"2025-12-26T03:45:00Z"` (for 09:15 IST)
- Conversion: IST to UTC (-5:30 hours)

### 4.2 Contract Metadata Storage

**Database Storage:**
All contract metadata is stored in the `Instrument` model in the database.

**Instrument Model Fields:**

```python
class Instrument(models.Model):
    # Contract metadata fields
    trading_symbol: str            # e.g., "NIFTY02JAN2623850CE"
    symbol_token: str              # e.g., "42501"
    alternate_trading_symbol: str  # e.g., "NIFTY02JAN2623850PE"
    alternate_symbol_token: str    # e.g., "42502"
    daily_ce_symbol: str           # Daily CE contract
    daily_ce_token: str
    daily_pe_symbol: str           # Daily PE contract
    daily_pe_token: str
    exchange: str                  # "NFO" or "BFO"
    lot_size: int                  # 75 for NIFTY, 35 for BANKNIFTY
```

**No External Files Required:**

- Contract data managed via Django admin interface
- Updated directly in database through API or admin panel
- No JSON file dependencies

---

## 5. Configuration Parameters

### 5.1 Strategy Constants

```python
@dataclass
class StrategyOneConfig:
    candle_interval: str = "FIVE_MINUTE"
    session_start: time = time(9, 15)           # 09:15 IST
    prev_window_start: time = time(14, 45)      # 14:45 IST
    prev_window_end: time = time(15, 30)        # 15:30 IST
    max_open_minus_prev_low: Decimal = Decimal("40")
```

### 5.2 Per-Instrument Configuration

**Instrument Model Fields:**

- `no_of_lots`: Number of lots to trade (default: 1)
- `lot_size`: Contracts per lot (75 for NIFTY, 35 for BANKNIFTY)
- `transaction`: BUY or SELL direction
- `contract_expiry_code`: Expiry date code (e.g., "02JAN2026")

### 5.3 Exchange Calendar

**Calendar Source:** `exchange_calendars` library
**Exchange Code:** `XBOM` (Bombay Stock Exchange)
**Used For:**

- Previous trading day calculation
- Trading day validation
- Holiday detection

---

## 6. Error Handling

### 6.1 Strategy Skips

**StrategySkip Exception:**

- Raised when conditions prevent trade execution
- Logged in StrategyRunLog with status "skipped"
- Returns summary with skip reason

**Common Skip Reasons:**

- "Algo is currently disabled"
- "Strategy Alpha is not active for this user"
- "Selected date is not a trading day"
- "No instruments available for Strategy Alpha"
- "Instrument missing contract expiry"
- "Market data unavailable for {instrument}"
- "No previous-day candles in 14:45–15:30 window"
- "No 5-min candle closed above previous high"
- "Entry filter failed: distance from previous low > 40"

### 6.2 Market Data Errors

**MarketDataError Exception:**

- Raised when data source unavailable
- Attempts SmartAPI fallback
- Falls back to demo provider if all sources fail

**Fallback Chain:**

1. SmartAPI live fetch
2. Token-specific candle files
3. Date-based quote files
4. Demo provider (synthetic data)

### 6.3 Order Execution Errors

**Demo Mode:**

- Always succeeds (synthetic orders)
- No real API calls

**Live Mode:**

- `AngelAPIError` for API failures
- Validates credentials before order
- Logs error in Trade.notes field
- Sets Trade.status = "error"

---

## 7. Testing & Validation

### 7.1 Backtesting

**Purpose:** Validate strategy logic using historical data

**Usage:**

```bash
python manage.py run_strategy_one chandralingam \
    --mode demo \
    --market-date 2025-12-26
```

**Validation Points:**

1. ✓ Previous trading day correctly identified (Dec 24, not Dec 25 holiday)
2. ✓ Previous day candles (14:45-15:30) loaded successfully
3. ✓ High/low calculated correctly
4. ✓ Breakout candle detected when close > prev_high
5. ✓ First candle check adjusts reference for gap-ups
6. ✓ 40-point filter rejects extended entries
7. ✓ Trade created in database with correct fields
8. ✓ Contract expiry validated (not expired on trade date)

### 7.2 Test Data Requirements

**Minimum Requirements:**

- Valid SmartAPI credentials (api_key and jwt_token)
- Contract metadata with valid tokens
- User with configured instruments
- Active SmartAPI session with data access
- Valid trading dates (not weekends/holidays)

### 7.3 Sample Test Case

**Setup:**

```
User: chandralingam
Instrument: NIFTY (02JAN2026)
Market Date: 2025-12-26
Mode: demo

Previous Day (2025-12-24):
  Candles 14:45-15:30 → prev_high=157.85, prev_low=144.00

Current Day (2025-12-26):
  09:15-09:45: Below prev_high
  09:50: Close=158.40 > prev_high (BREAKOUT!)
  Gap check: 158.40 - 144.00 = 14.40 <= 40 ✓
```

**Expected Result:**

```json
{
  "status": "completed",
  "mode": "demo",
  "opened_trades": 1,
  "instrument_summaries": [
    {
      "instrument": "NIFTY",
      "opened": 1,
      "price": "158.40",
      "message": "Entry order placed by Strategy One."
    }
  ]
}
```

**Database Verification:**

```sql
SELECT * FROM api_trade
WHERE user_id = (SELECT id FROM auth_user WHERE username='chandralingam')
  AND contract_symbol = 'NIFTY02JAN2623850CE'
  AND entry_price = 158.40
  AND status = 'open';
```

---

## 8. Future Enhancements

### 8.1 Planned Features

1. **Exit Strategy:**

   - Target profit levels
   - Stop loss management
   - Trailing stops
   - Time-based exits (15:25 IST)

2. **Risk Management:**

   - Position sizing based on account size
   - Maximum daily loss limits
   - Maximum open positions

3. **Multi-Timeframe Analysis:**

   - Additional confirmation from 15-minute charts
   - Hourly trend alignment

4. **Dynamic Strike Selection:**

   - ATM strike calculation at entry time
   - Dynamic contract selection based on IV

5. **Performance Analytics:**
   - Win rate tracking
   - Average P&L per trade
   - Drawdown analysis
   - Strategy performance dashboard

### 8.2 Known Limitations

1. **Single Entry Per Day:** Currently opens one position per instrument
2. **No Position Management:** Trades are not actively managed post-entry
3. **Fixed Parameters:** 40-point filter is hardcoded
4. **No Correlation Filter:** Doesn't check market-wide conditions
5. **SmartAPI Dependency:** Requires active API credentials and data access
6. **Historical Data Access:** Limited by SmartAPI historical data retention period

---

## 9. Deployment Checklist

### 9.1 Production Setup

- [ ] Configure SmartAPI credentials for all users
- [ ] Validate SmartAPI data access and historical data availability
- [ ] Validate exchange calendar (`exchange_calendars` installed)
- [ ] Configure instrument metadata in database (trading_symbol, symbol_token, lot_size)
- [ ] Test demo mode execution
- [ ] Validate instrument configurations
- [ ] Enable AlgoConfiguration.algo_active
- [ ] Enable StrategyActivation.is_active
- [ ] Set appropriate lot sizes per instrument

### 9.2 Live Trading Prerequisites

- [ ] AlgoConfiguration.market_active = True
- [ ] Valid SmartAPI session (jwt_token refreshed)
- [ ] Test order placement in demo mode first
- [ ] Verify contract expiry dates are valid
- [ ] Confirm lot sizes match broker requirements
- [ ] Monitor initial trades closely
- [ ] Have circuit breaker / kill switch ready

### 9.3 Monitoring

**Key Metrics:**

- Trades opened per day
- Success rate of breakout detection
- Average entry-to-breakout time
- Filter rejection rate (40-point rule)
- Market data availability

**Logs to Monitor:**

- StrategyRunLog entries
- Trade creation/updates
- Market data errors
- Order execution failures

---

## 10. Support & Troubleshooting

### 10.1 Common Issues

**Issue: "No previous-day candles"**

- **Cause:** SmartAPI unavailable or no data access for requested date
- **Solution:** Verify SmartAPI credentials are valid and session is active, check data access permissions

**Issue: "SmartAPI credentials required for historical data"**

- **Cause:** Missing or invalid api_key/jwt_token in UserProfile
- **Solution:** Reconnect brokerage account and refresh tokens

**Issue: "Entry filter failed: distance from previous low > 40"**

- **Cause:** Large gap between entry and previous low
- **Solution:** Normal behavior, indicates extended move. Consider adjusting `max_open_minus_prev_low` config

**Issue: "No 5-min candle closed above previous high"**

- **Cause:** No breakout occurred during session
- **Solution:** Normal behavior, strategy correctly skipped non-opportunity

**Issue: Contract expired error**

- **Cause:** `contract_expiry_code` references past date
- **Solution:** Update instrument's `contract_expiry_code`, `trading_symbol`, and `symbol_token` fields

### 10.2 Debug Mode

**Enable Detailed Logging:**

```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

**Check Strategy Run Logs:**

```python
logs = StrategyRunLog.objects.filter(
    user__username='chandralingam',
    strategy_code='strategy_alpha'
).order_by('-created_at')[:10]

for log in logs:
    print(f"{log.created_at}: {log.status} - {log.message}")
    print(f"Extra: {log.extra}")
```

### 10.3 Data Validation

**Verify SmartAPI Access:**

```python
from api.services.smartapi_market import SmartAPIMarketClient
from datetime import datetime

client = SmartAPIMarketClient(
    api_key="your_api_key",
    jwt_token="your_jwt_token"
)

# Test candle data access
candles = client.get_option_candles(
    exchange="NFO",
    symbol_token="42501",
    interval="FIVE_MINUTE",
    start=datetime(2025, 12, 26, 9, 15),
    end=datetime(2025, 12, 26, 15, 30),
)
print(f"Fetched {len(candles)} candles")
```

**Verify Contract Metadata:**

```python
from api.models import Instrument
from django.contrib.auth.models import User

user = User.objects.get(username='chandralingam')
instruments = Instrument.objects.filter(user=user, active=True)

for inst in instruments:
    print(f"{inst.instrument}: {inst.trading_symbol} (Token: {inst.symbol_token})")
```

---

## Appendix A: Code Examples

### A.1 Running Strategy Manually

```python
from django.contrib.auth.models import User
from api.services.strategy_one import OpeningRangeBreakoutEngine
from datetime import date

user = User.objects.get(username='chandralingam')
engine = OpeningRangeBreakoutEngine(
    user=user,
    execution_mode='demo',
    market_date=date(2025, 12, 26),
)
summary = engine.run()
print(summary)
```

### A.2 Querying Trades

```python
from api.models import Trade
from django.contrib.auth.models import User

user = User.objects.get(username='chandralingam')
trades = Trade.objects.filter(
    user=user,
    strategy_code='strategy_alpha',
    execution_mode='demo',
).order_by('-entry_datetime')[:10]

for trade in trades:
    print(f"{trade.instrument.instrument}: {trade.contract_symbol} @ {trade.entry_price}")
```

---

## Appendix B: Glossary

**ATM (At The Money):** Strike price closest to current underlying price

**Breakout:** Price closing above previous resistance level (prev_high)

**CE:** Call Option (right to buy)

**Contract Symbol:** Full option contract identifier (e.g., NIFTY02JAN2623850CE)

**Contract Token:** Unique numeric identifier for API calls

**Gap-Up:** Opening price significantly above previous close

**IST:** Indian Standard Time (UTC+5:30)

**Lot Size:** Number of contracts per lot (75 for NIFTY, 35 for BANKNIFTY)

**NFO:** National Stock Exchange Futures & Options segment

**ORB:** Opening Range Breakout strategy

**PE:** Put Option (right to sell)

**Previous Trading Day:** Most recent trading session before current date

**SmartAPI:** Angel Broking's trading API

**Strategy Skip:** Intentional non-execution due to conditions not met

**Symbol Token:** Same as Contract Token

**XBOM:** Bombay Stock Exchange calendar code

---

## Document History

| Version | Date       | Author | Changes                           |
| ------- | ---------- | ------ | --------------------------------- |
| 1.0     | 2025-12-27 | System | Initial comprehensive PRD created |

---

**END OF DOCUMENT**
