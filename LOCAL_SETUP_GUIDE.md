# QuantStrike — Local Setup Guide

Step-by-step instructions to run the full QuantStrike platform on a new machine.

---

## Prerequisites

Install these before starting:

| Software       | Version | Install Command / Link                          |
|----------------|---------|------------------------------------------------|
| Python         | 3.12+   | `brew install python@3.12` or [python.org](https://www.python.org/downloads/) |
| Node.js        | 18+     | `brew install node` or [nodejs.org](https://nodejs.org/) |
| PostgreSQL     | 15+     | `brew install postgresql@17` or [Postgres.app](https://postgresapp.com/) |
| Git            | any     | `brew install git` or [git-scm.com](https://git-scm.com/) |

> **Mac users**: Install [Homebrew](https://brew.sh/) first if you don't have it:
> ```bash
> /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
> ```

---

## Step 1: Clone the Repository

```bash
git clone https://github.com/ChandralingamP/QuantStrike.git
cd QuantStrike
```

---

## Step 2: Setup PostgreSQL Database

Make sure PostgreSQL is running:
```bash
# If installed via Homebrew:
brew services start postgresql@17

# If installed via Postgres.app:
# Just open the app — it starts automatically
```

Create the database and user:
```bash
psql -U postgres -h localhost
```

In the PostgreSQL prompt, run:
```sql
CREATE USER quantstrike WITH PASSWORD 'quantstrike';
CREATE DATABASE quantstrike OWNER quantstrike;
GRANT ALL PRIVILEGES ON DATABASE quantstrike TO quantstrike;
\q
```

(Optional) Create a `.pgpass` file for passwordless access:
```bash
echo "localhost:5432:*:quantstrike:quantstrike" > ~/.pgpass
chmod 600 ~/.pgpass
```

---

## Step 3: Setup Backend (Django)

```bash
cd backend

# Create Python virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### Create the `.env` file

Create `backend/.env` with the following content:

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
EMAIL_HOST_PASSWORD=dcyttcjlpydifvfz
EMAIL_USE_TLS=true
DEFAULT_FROM_EMAIL=quantstrike.algo@gmail.com
```

### Initialize the Database

**Option A — Fresh start (no existing data):**
```bash
source venv/bin/activate
python manage.py migrate
python manage.py createsuperuser
# Follow the prompts to create an admin user
```

**Option B — Restore from backup (recommended if you have one):**

Copy `quantstrike_backup.sql` to the project root, then:
```bash
psql -U quantstrike -h localhost -d quantstrike < ../quantstrike_backup.sql
```

### Copy Data Files (if available)

If you have the data/logs backup (`qs_data_logs.tar.gz`), extract it:
```bash
cd backend
tar xzf ../qs_data_logs.tar.gz
```

This restores:
- `data/instruments.json` — Angel One scrip master
- `data/instruments_expiries.json` — Expiry dates
- `logs/users/` — Historical strategy execution logs

If you DON'T have the backup, create the directories:
```bash
mkdir -p data logs/users
```
The scrip master will be downloaded automatically by the scheduled job (or manually — see Step 6).

### Verify Backend Works

```bash
source venv/bin/activate
python manage.py check
# Should show: "System check identified no issues"

python manage.py runserver 8000
# Should show: "Starting development server at http://127.0.0.1:8000/"
# Press Ctrl+C to stop
```

---

## Step 4: Setup Frontend (React + Vite)

```bash
cd frontend

# Install dependencies
npm install
```

That's it. The `vite.config.js` already has a proxy configured to forward `/api` requests to `http://localhost:8000`.

---

## Step 5: Run the Application

You need **two terminals** running simultaneously:

**Terminal 1 — Backend:**
```bash
cd backend
source venv/bin/activate
python manage.py runserver 8000
```

When the server starts, you'll see:
```
Scheduler started with 6 jobs: Clear stale daily caches (7:00 AM IST),
Run Strategy Alpha (9:16 AM IST), Refresh scrip master (4:00 PM IST), ...
```

All scheduled tasks run automatically — **no crontab setup needed**.

**Terminal 2 — Frontend:**
```bash
cd frontend
npm run dev
```

Open your browser and go to: **http://localhost:5173**

### Default Login Credentials

| User           | Password          | Role        |
|----------------|-------------------|-------------|
| Admin          | QuantStrike@2026  | Superuser   |
| chandralingam  | (check with admin)| Regular user|

> If you did a fresh setup (Option A), use the superuser credentials you created.

---

## Step 6: Scheduled Jobs (Automatic)

All trading jobs run automatically via the **built-in scheduler** when the backend server is running. No crontab or external setup needed.

> **Important**: Your laptop must be **awake and not sleeping** during trading hours (9:00 AM – 4:30 PM IST) for jobs to fire.

### Schedule

| Time (IST) | Job | Purpose |
|------------|-----|---------|
| 7:00 AM    | update_instruments --skip-refresh | Clears stale daily caches before market opens |
| 9:16 AM    | run_all_strategies | Runs Strategy Alpha for all users, spawns entry scanner & monitor |
| 4:00 PM    | update_scrip_master --force | Downloads latest contract list from Angel One |
| 4:15 PM    | update_instruments | Rolls expired contracts to next expiry |
| 4:20 PM    | load_instrument_metadata | Syncs instrument config from JSON to DB |
| Midnight   | cleanup_old_logs --days 5 | Deletes log files older than 5 days |

The scheduler is defined in `backend/api/scheduler.py` and starts automatically with `runserver`. It does NOT start for management commands (`migrate`, `shell`, etc.).

---

## Step 7: Manual Commands (Optional)

These are useful for initial setup or troubleshooting:

```bash
cd backend
source venv/bin/activate

# Download scrip master (contract list) from Angel One
python manage.py update_scrip_master --force

# Update instruments (sync expiries, roll contracts)
python manage.py update_instruments

# Load instrument metadata from JSON
python manage.py load_instrument_metadata --path data/instruments.json

# Run strategy manually for a specific user
python manage.py run_strategy_alpha chandralingam

# Run strategy for all active users
python manage.py run_all_strategies --strategy strategy_alpha

# Open Django admin
python manage.py runserver 8000
# Then go to http://localhost:8000/admin/
```

---

## Troubleshooting

### "Connection refused" on frontend
- Make sure the backend is running on port 8000 in a separate terminal.

### "Database does not exist"
```bash
psql -U postgres -h localhost -c "CREATE DATABASE quantstrike OWNER quantstrike;"
cd backend && source venv/bin/activate && python manage.py migrate
```

### "No module named 'xxx'"
```bash
cd backend && source venv/bin/activate && pip install -r requirements.txt
```

### "SmartAPI IP address error" (at startup)
```
Exception while retriving IP Address, using local host IP address
```
This is a harmless warning from the Angel One SDK. It doesn't affect functionality.

### Cron jobs not running
- Verify cron is set: `crontab -l`
- Check Mac System Settings → Privacy & Security → Full Disk Access → add `/usr/sbin/cron`
- Make sure laptop is not sleeping during scheduled times
- Check logs: `cat backend/logs/strategies.log`

### Strategy shows "Previous session levels not available"
- This means the previous trading day had no candle data (likely a market holiday).
- The system retries up to 5 previous days automatically. If it still fails, the scrip master may be outdated — run `python manage.py update_scrip_master --force`.

---

## Project Structure

```
QuantStrike/
├── backend/                 # Django REST API
│   ├── .env                 # Environment variables (NOT in git)
│   ├── manage.py            # Django management
│   ├── requirements.txt     # Python dependencies
│   ├── venv/                # Python virtual environment (NOT in git)
│   ├── data/                # Scrip master JSON files
│   ├── logs/                # Strategy execution logs
│   │   └── users/           # Per-user strategy logs
│   ├── api/                 # Main Django app
│   │   ├── models.py        # Database models
│   │   ├── views.py         # API endpoints
│   │   ├── services/        # Strategy engines
│   │   │   └── strategy_alpha.py  # Core trading logic
│   │   └── management/commands/   # CLI commands
│   └── quantstrike_backend/ # Django settings
├── frontend/                # React + Vite
│   ├── package.json         # Node dependencies
│   ├── vite.config.js       # Dev server config (proxy to backend)
│   └── src/                 # React source code
└── quantstrike_backup.sql   # Database backup (NOT in git)
```

---

## Files NOT in Git (must be copied manually)

| File/Folder | Purpose | Required? |
|-------------|---------|-----------|
| `backend/.env` | Database credentials, email config, secrets | **Yes** |
| `backend/venv/` | Python virtual environment | No — recreate with `python3 -m venv venv` |
| `backend/data/instruments.json` | Angel One scrip master | No — downloaded by `update_scrip_master` |
| `backend/logs/` | Strategy execution logs | No — created automatically |
| `quantstrike_backup.sql` | Database dump with all users/trades | Only if restoring existing data |
| `frontend/node_modules/` | Node packages | No — recreate with `npm install` |
