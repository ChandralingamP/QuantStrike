# QuantStrike Platform PRD

## 1. Product Summary

- **Product name:** QuantStrike – Algorithmic Trading Control Center
- **Audience:** Proprietary trading desks and advanced traders who automate breakout strategies through Angel One SmartAPI.
- **Release scope:** Current Django + React implementation shipped in December 2025.

## 2. Objectives

- Provide a secure web console for configuring brokerage connectivity, eligible instruments, and deployment state of Strategy Alpha.
- Offer realtime visibility into trade lifecycle, margin costs (via export), and run history so operators can audit every automated action.
- Minimise day-to-day operational friction: cached market metadata, guarded toggles, sandbox simulation runs, and downloadable reports.

## 3. Success Metrics

- Operators can connect brokerage credentials and obtain a "Connected" status without database edits.
- Strategy Alpha runs (demo or live) always find at least one configured instrument or clearly state why the run was skipped.
- P&L exports reconcile with trades stored in PostgreSQL tables `api_trade` and `api_strategyrunlog`.
- Zero critical regression bugs in UI flows (login → configure instruments → run strategy → review trades).

## 4. Users & Permissions

- **Trader (standard account):**
  - Signs up with email OTP and completes CAPTCHA-protected login.
  - Maintains own brokerage credentials and algo configuration.
  - Views trade history, instruments, and run status.
- **Admin (flagged via `is_staff`):**
  - Uses `/admin` panel and dedicated admin React page to inspect users, activate/deactivate accounts, and reset strategies.
  - Currently shares same API surface; future versions can extend serializers for admin-only mutations.

## 5. System Overview

- **Frontend:** React SPA (Vite build) with TailwindCSS styling. Redux Toolkit slices manage auth, instruments, home status, P&L, algo configuration, and strategy runs.
- **Backend:** Django + Django REST Framework. Key services include SmartAPI wrappers, Strategy Alpha execution engine, OTP delivery, Excel exports, and instrument bootstrapping.
- **Database:** PostgreSQL with migrations captured under `backend/api/migrations`.
- **Integrations:**
  - Angel One SmartAPI (market data, order placement).
  - Email OTP (Django email backend).
  - openpyxl for Excel generation.

## 6. Functional Requirements

### 6.1 Authentication & Account Lifecycle

- Sign-up requires name, phone, brokerage account id, API key, email, password, and OTP verification (`POST /auth/signup`).
- Login enforces CAPTCHA and issues JWT-based session cookies (`POST /auth/login`).
- Password reset uses email OTP with `/auth/password-reset/request`, `/auth/password-reset/verify`, `/auth/password-reset/confirm`.
- Session state persisted via secure HTTP-only cookies; username cached client-side for API calls.

### 6.2 Brokerage Connectivity (Home Page)

- `GET /home/status?username=` displays masked API key, connection status, and timestamps.
- `POST /home/connect` accepts MPIN + TOTP, attempts Angel SmartAPI login, and updates `UserProfile.jwt_token` fields.
- UI caches previous fetch for two minutes to avoid redundant API hits while still refreshing after credential changes.

### 6.3 Instruments Management

- `GET /instruments?username=` returns per-user instruments. If none exist, `initialize_user_instruments` seeds NIFTY, BANKNIFTY, and SENSEX defaults.
- Columns exposed client-side: index scrip, expiry, transaction side, lot counts, premium/PL/SL/trailing points.
- `PUT /instruments/{id}?username=` updates one record; numeric sanitisation performed in frontend.
- Instruments carry dynamic strike metadata (`strike_selection`, offsets, cached daily CE/PE symbols) to support ATM selection by Strategy Alpha.

### 6.4 Algo Configuration Dashboard

- `GET /algo-configuration?username=` fetches `AlgoConfiguration` and `StrategyActivation` state.
- Controls:
  - `algo_active` toggle enables run loop globally.
  - `market_active` gate stops live order placement when false.
  - `strategy_alpha_active` toggle (StrategyActivation.is_active) plus instrument multi-select.
  - Mode selector (Demo vs Live) disabled unless admin has whitelisted user for live trading.
- Status card surfaces runtime metadata: last updated timestamps, currently selected instruments, and primitive extra fields (post #[object Object] fix).

### 6.5 Strategy Operations

- `/strategy-alpha/run` endpoint triggers `StrategyAlphaEngine`. Validates algo and strategy toggles, ensures instrument assignments, and coordinates SmartAPI data provider.
- Management command `python manage.py run_strategy_alpha <username> --mode demo|live --market-date YYYY-MM-DD --sandbox` mirrors API execution and supports fixture replay.
- Run output summarises opened/closed trades, per-instrument notes, and net P&L. Failures or skips are persisted to `StrategyRunLog`.

### 6.6 Profit & Loss Reporting

- `GET /pnl?username=&mode=` returns paginated trades (open + closed) with totals for gross P&L, brokerage, margin, and net P&L. Margin is no longer displayed in UI; still provided by API and Excel export.
- `GET /pnl/export` streams XLSX with enriched columns (brokerage, margin, net P&L) and final totals row.
- Frontend table highlights positive vs negative P&L, supports mode filters (all/demo/live), and exposes "Download Excel" button.

### 6.7 Admin Console (React `AdminPage`)

- Restricted to staff accounts (checked via auth slice).
- Lists users, toggles account activation, and allows manual reset of strategy state.
- Reuses DRF serializers `AdminUserSerializer`, `AdminUserToggleSerializer`, `AdminAccessSerializer`.

## 7. Data Model Snapshot

- `UserProfile` stores SmartAPI credentials, tokens, and audit timestamps.
- `Instrument` captures trading parameters, dynamic strike cache (`daily_*` fields), and activation flags.
- `AlgoConfiguration` holds global toggles per user.
- `StrategyActivation` manages per-strategy activation, mode (demo/live), and instrument through table `StrategyActivationInstrument`.
- `Trade` persists lifecycle data: prices, timestamps, calculated targets/stops, contract symbol/token, brokerage sync ids.
- `StrategyRunLog` records each engine invocation with status and extra JSON summary.
- `EmailOTP` supports enroll/reset workflows with hashed OTP and TTL metadata.

## 8. API Surface (Implemented Endpoints)

- Authentication: `/auth/login`, `/auth/signup`, `/auth/request-otp`, `/auth/password-reset/*`, `/auth/logout`.
- User & Admin: `/admin/users`, `/admin/users/{id}/toggle`, `/admin/users/{id}/delete`, `/admin/access`.
- Home: `/home/status`, `/home/connect`.
- Instruments: `/instruments`, `/instruments/{id}`.
- Algo configuration: `/algo-configuration`, `/algo-configuration/history`, `/strategy-activation` actions.
- Strategy execution: `/strategy-alpha/run`.
- Profit & Loss: `/pnl`, `/pnl/export`.

## 9. Frontend UX Requirements

- Dark themed dashboard with consistent typography, rounded cards, and hover states.
- Navigation bar with routes: Home, Instruments, Profit & Loss, Algo Configuration; Login/Signup/Logout flows on the right.
- Loading states for each page, skeleton placeholders for empty datasets, and inline error banners for API failures.
- Pagination controls on P&L, confirm dialogs before instrument updates, and modal for detailed errors.
- Responsive layout: cards stack vertically under 1024px.

## 10. Operational Considerations

- **Sandbox support:** `ANGEL_SANDBOX_ENABLED=1` allows SmartAPI fixtures to drive runs without hitting live endpoints.
- **Caching:** Frontend caches Home and Instruments responses in localStorage keyed by username with TTL defined in `utils/dataCache.js`.
- **Logging:** `StrategyAlphaEngine` writes detail-level logs (`logger.info`, `logger.debug`, `logger.warning`) aiding post-run audits.
- **Error handling:** Strategy runs raise `StrategySkip` for controlled exits (missing configuration, stale metadata) and mark run logs as `skipped` instead of `failed`.

## 11. Security & Compliance

- Mask API keys in UI and API responses (`mask_api_key`).
- Require CAPTCHA on login to mitigate brute force.
- Email OTP hashed at rest; TTL defaults to 10 minutes.
- All SmartAPI credentials stored server-side, never sent back to frontend.
- Enforce HTTPS in production deployments (infrastructure requirement).

## 12. Reporting & Audit

- XLSX exports include per-trade margin, brokerage, and net P&L totals.
- Selected instruments and daily ATM cache fields (`daily_*`) provide traceability for strike selection decisions.
- Staff users can inspect `StrategyRunLog` and `Trade` tables via Django admin for compliance or reconciliation.

## 13. Future Enhancements (Backlog)

- Multi-strategy support beyond Strategy Alpha.
- Role-based access control for read-only auditors.
- Intraday performance charts on P&L page.
- WebSocket push for live order updates.
- Automated health checks for SmartAPI connectivity and token expiry reminders.
