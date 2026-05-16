# QuantStrike

QuantStrike is an automated options trading platform that executes breakout strategies on NSE/BSE indices (NIFTY, BANKNIFTY, SENSEX) via the Angel One SmartAPI. Built with a Django REST backend and a React frontend.

## Project Structure

```
QuantStrike/
├── backend/          # Django REST API + strategy engine + scheduler
│   ├── api/          # Models, views, services, management commands
│   │   ├── services/ # Strategy Alpha engine, market data clients
│   │   └── scheduler.py  # Built-in APScheduler (replaces crontab)
│   ├── data/         # Scrip master JSON files
│   └── logs/         # Execution logs (per-user strategy logs)
├── frontend/         # React + Vite + Redux Toolkit + Tailwind CSS
└── LOCAL_SETUP_GUIDE.md  # Detailed setup instructions
```

## Quick Start

### Prerequisites

- Python 3.12+
- Node.js 18+
- PostgreSQL 15+

### 1. Database

```bash
psql -U postgres -h localhost
CREATE USER quantstrike WITH PASSWORD 'quantstrike';
CREATE DATABASE quantstrike OWNER quantstrike;
\q
```

### 2. Backend

```bash
cd backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
# Create backend/.env (see LOCAL_SETUP_GUIDE.md for full template)
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver 8000
```

The server starts with a **built-in scheduler** that runs all trading jobs automatically (strategy execution at 9:16 AM, scrip master refresh at 4:00 PM, etc.). No crontab needed.

### 3. Frontend

```bash
cd frontend
npm install
npm run dev
```

Open **http://localhost:5173** — the Vite dev server proxies `/api` requests to the backend.

## Strategy Alpha — How It Works

1. **Contract Selection** — Picks ATM CE and PE option contracts for each instrument
2. **Previous Session Levels** — Fetches last 45 min candle data from previous trading day (high/low)
3. **Breakout Detection** — Scans 5-min candles for price breaking above previous session high
4. **Entry** — Enters on the next candle's open after breakout confirmation
5. **Risk Management** — Stop loss at previous session low, target at configured points
6. **Monitoring** — Polls every 15 seconds for SL/TP/EOD exits

## Scheduled Jobs

| Time (IST) | Job                                 | Purpose                              |
| ---------- | ----------------------------------- | ------------------------------------ |
| 7:00 AM    | `update_instruments --skip-refresh` | Clear stale daily caches             |
| 9:16 AM    | `run_all_strategies`                | Execute Strategy Alpha for all users |
| 4:00 PM    | `update_scrip_master --force`       | Refresh contract list from Angel One |
| 4:15 PM    | `update_instruments`                | Roll expired contracts               |
| 4:20 PM    | `load_instrument_metadata`          | Sync instrument config from JSON     |
| Midnight   | `cleanup_old_logs --days 5`         | Delete old log files                 |

## Testing

- Backend: `python manage.py test`
- Frontend: `npm test`
- Linting: `npm run lint`

## Full Setup Guide

See [LOCAL_SETUP_GUIDE.md](LOCAL_SETUP_GUIDE.md) for detailed instructions including database restore, environment variables, and troubleshooting.
