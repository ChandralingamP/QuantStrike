# Strategy Alpha PRD

## 1. Strategy Overview

- **Strategy code:** `strategy_alpha`
- **Type:** Intraday breakout on NIFTY/BANKNIFTY/SENSEX weekly options (5-minute cadence).
- **Execution modes:** Demo (default) and Live via Angel SmartAPI.
- **Objective:** Capture upside momentum after previous-session high breaks for CE contracts (or configured SELL legs for static strikes) while enforcing strict gap and trailing controls.

## 2. Preconditions & Dependencies

- Algo and strategy toggles must be active (`AlgoConfiguration.algo_active`, `StrategyActivation.is_active`).
- User must assign at least one active instrument via Algo Configuration (the instrument automatically links to `StrategyActivation`).
- For live mode: `AlgoConfiguration.market_active = True`, user profile holds valid SmartAPI session (`UserProfile.jwt_token`).
- Instruments require:
  - `instrument` code (NIFTY/BANKNIFTY/SENSEX).
  - Contract expiry (date or code) and strike selection configuration.
  - Lot size, lot counts, PL/SL/trailing parameters.
  - Active flag enabled.
- SmartAPI credentials available for market data and order placement, unless sandbox fixture mode is engaged.

## 3. Daily Lifecycle

1. **Market open (09:15 IST):** Strategy fetches entry snapshot per instrument (price, previous low, next open).
2. **ATM contract caching:**
   - If `strike_selection = atm`, compute CE/PE symbols using current underlying price rounded to `strike_step`.
   - Persist daily CE/PE symbol + token and underlying price for reuse during the day.
3. **Previous session levels:**
   - For ATM BUY legs, pull previous day (14:45-15:29) five-minute candles to determine `daily_*_prev_high/low`.
   - Persist to instrument to avoid redundant fetches.
4. **Intraday monitoring:**
   - Retrieve five-minute candles for the day.
   - Search for breakout of previous high; enforce gap limit (`<= 40`) between breakout candle and reference low.
   - If breakout occurs:
     - Plan entry at next candle open.
     - Record stop anchored to previous low (or fallback to SL points if unavailable).
5. **Order execution:**
   - Demo mode creates synthetic order IDs and uses reference price.
   - Live mode sends market orders via SmartAPI with validated tokens and lot sizes.
6. **Trade management:**
   - Track target (`pl_points`), stop loss (`sl_points` or cached previous low), and trailing stop (`trailing_points`).
   - Update trailing stop whenever price advances in trade direction.
7. **Exit conditions:**
   - Target hit, stop loss, trailing stop, or end-of-day deadline (15:25 IST) – whichever occurs first.
   - Force close any remaining open trades at 15:25 or earlier if backtesting a historical date.
8. **Logging & persistence:**
   - Store trade in `api_trade` with entry/exit metadata, contract symbol/token, and P&L.
   - Append run summary to `StrategyRunLog` with opened/closed counts and per-instrument messages.

## 4. Instrument Configuration Details

- **Static mode:** Uses manually provided `trading_symbol` and optional alternate leg.
- **ATM mode:**
  - `strike_step` (e.g., 50 for NIFTY, 100 for BANKNIFTY) sets rounding granularity.
  - `ce_strike_offset` / `pe_strike_offset` allow shifting from ATM (0) by multiples of step.
  - Daily selection persisted only when `market_date` matches current local date to prevent backtest pollution.
- **Risk parameters:**
  - `premium_price` optional reference to validate affordability. BUY entries require price <= premium, SELL entries require price >= premium.
  - `pl_exit_lots` reserved for partial exit future extension (currently informational).
  - `trailing_points` > 0 enables trailing stop update rules.

## 5. Market Data Strategy

- Primary provider: `SmartAPIMarketClient` retrieving option candles and underlying quotes.
- Sandbox mode: falls back to fixture JSON (docs/historical-data) loaded via `SmartAPIMarketClient` stub.
- Entry snapshot attempts `provider.get_entry_snapshot()`; falls back to `provider.get_price` and optional `previous_low` data.
- Intraday candles cached in-memory per symbol to avoid repeated SmartAPI calls within single run.

## 6. Execution Logic Summary

```
for instrument in active_strategy_instruments:
    snapshot = provider.get_entry_snapshot()
    contracts = contract_specs(instrument)
    for contract in contracts:
        open_trade = fetch_open_trade(contract)
        if open_trade:
            maybe_update_trailing_stop()
            if should_close(open_trade, snapshot.price):
                place exit order => close trade
        else:
            plan = plan_entry(instrument, contract, snapshot)
            if plan.should_enter:
                price = quantize(plan.entry_price)
                submit entry order (demo or live)
                create Trade with targets/stops
```

- `should_close` returns rationale string (`target`, `stop_loss`, `trailing_stop`, `end_of_day`).
- `plan_entry` handles ATM breakout logic, gap checks, and reference level persistence.
- Trades always quantized to `0.05` price steps to match exchange tick size.

## 7. Error & Skip Handling

- Controlled skips raise `StrategySkip` with user-facing message:
  - Algo disabled (`algo_active` false).
  - Strategy inactive or instrument list empty.
  - Missing contract tokens for live orders.
  - No previous session levels / intraday candles.
  - Gap beyond threshold.
- Skips mark run log status `skipped` with reason; no trades are altered.
- Exceptions bubble up, mark run log `failed`, and re-raise for monitoring.

## 8. Outputs & Reporting

- Run summary contains:
  - `status` (`completed`, `skipped`).
  - `mode` (`demo`, `live`).
  - Counts of opened/closed trades, net P&L (string).
  - `instrument_summaries`: instrument name, price snapshot, counts, optional message, and P&L.
- Trades appear in Profit & Loss API/UI with execution mode, direction, targets stops, and entry/exit times.

## 9. Operational Controls

- Live execution requires market toggle and valid session tokens checked at runtime.
- Demo runs (`--sandbox`) rely on fixtures to simulate price action; ensures deterministic tests for historical dates (e.g., 2025-12-04, 2025-12-05).
- End-of-day auto-close ensures flat book; when backtesting via `--market-date`, exits align with historic EOD even if command runs at off-hours.

## 10. Future Enhancements

- Support SELL-based breakout (PE leg) mirroring CE logic with configurable parameters.
- Partial profit booking guided by `pl_exit_lots`.
- Multi-timeframe confirmation (e.g., previous day VWAP filter).
- Risk overlays: daily loss cap per user, max concurrent trades.
- Visual run log timeline in frontend, highlighting skip reasons and contract selections.
