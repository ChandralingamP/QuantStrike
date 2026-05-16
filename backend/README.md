# QuantStrike Backend

Django REST API and strategy execution engine for the QuantStrike automated trading platform. Manages user accounts, instruments, trade execution, and scheduled jobs.

## Prerequisites

- Python 3.12+
- PostgreSQL 15+

## Setup

```bash
cd backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### Environment Variables

Create a `.env` file:

```env
DJANGO_SECRET_KEY=replace-this-with-a-secure-value
DJANGO_DEBUG=True
DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1
POSTGRES_DB=quantstrike
POSTGRES_USER=quantstrike
POSTGRES_PASSWORD=quantstrike
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
CORS_ALLOWED_ORIGIN_REGEXES=http://localhost:5173
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_HOST_USER=quantstrike.algo@gmail.com
EMAIL_HOST_PASSWORD=<app-password>
EMAIL_USE_TLS=true
DEFAULT_FROM_EMAIL=quantstrike.algo@gmail.com
```

### Database

```bash
python manage.py migrate
python manage.py createsuperuser
```

Or restore from a backup:

```bash
psql -U quantstrike -h localhost -d quantstrike < ../quantstrike_backup.sql
```

### Run the Server

```bash
python manage.py runserver 8000
```

The API is at `http://localhost:8000/api/`. The **built-in scheduler** starts automatically with all trading jobs — no crontab needed.

## Built-in Scheduler

Defined in `api/scheduler.py`, starts on server boot via `api/apps.py`:

| Time (IST) | Command                                        | Purpose                               |
| ---------- | ---------------------------------------------- | ------------------------------------- |
| 7:00 AM    | `update_instruments --skip-refresh`            | Clear stale daily caches              |
| 9:16 AM    | `run_all_strategies --strategy strategy_alpha` | Run strategy for all users            |
| 4:00 PM    | `update_scrip_master --force`                  | Download contract list from Angel One |
| 4:15 PM    | `update_instruments`                           | Roll expired contracts                |
| 4:20 PM    | `load_instrument_metadata`                     | Sync instrument metadata from JSON    |
| Midnight   | `cleanup_old_logs --days 5`                    | Delete old log files                  |

The scheduler only runs with `runserver`, not with management commands like `migrate` or `shell`.

## Key Management Commands

```bash
# Download scrip master from Angel One
python manage.py update_scrip_master --force

# Update instruments (sync expiries, roll contracts)
python manage.py update_instruments

# Load instrument metadata
python manage.py load_instrument_metadata --path data/instruments.json

# Run strategy for a specific user
python manage.py run_strategy_alpha chandralingam

# Run strategy for all active users
python manage.py run_all_strategies --strategy strategy_alpha
```

## Project Layout

```
backend/
├── api/
│   ├── models.py              # User, Instrument, Trade, Strategy models
│   ├── views.py               # REST API endpoints
│   ├── scheduler.py           # APScheduler job definitions
│   ├── services/
│   │   ├── strategy_alpha.py  # Core breakout strategy engine
│   │   ├── smartapi_market.py # Angel One SmartAPI client
│   │   └── market_data.py     # Market data provider
│   ├── management/commands/   # CLI commands (run_strategy_alpha, monitor_trades, etc.)
│   └── migrations/
├── data/                      # instruments.json, instruments_expiries.json
├── logs/                      # Execution logs
│   └── users/                 # Per-user strategy logs
└── quantstrike_backend/       # Django settings
```

## Testing

```bash
python manage.py test
```
