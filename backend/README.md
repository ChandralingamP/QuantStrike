# QuantStrike Backend

Django REST API powering the QuantStrike trading strategy dashboard. The API exposes CRUD endpoints to manage strategies stored in PostgreSQL.

## Prerequisites

- Python 3.12+
- PostgreSQL 14+

## Setup

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

### Environment Variables

Create a `.env` file based on `.env.example`:

```
DJANGO_SECRET_KEY=replace-me
DJANGO_DEBUG=True
DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1
POSTGRES_DB=quantstrike
POSTGRES_USER=quantstrike
POSTGRES_PASSWORD=quantstrike
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
CORS_ALLOWED_ORIGINS=http://localhost:5173
```

### Database Preparation

```bash
python manage.py migrate
python manage.py createsuperuser
```

### Run the Development Server

```bash
python manage.py runserver 0.0.0.0:8000
```

The API root will be available at `http://localhost:8000/api/`.

## Instrument Metadata Refresh

Trading instruments (NIFTY, BANKNIFTY, SENSEX) rely on the Angel One scrip
master that lives in `My API/instruments.json` and the derived expiry summary
`My API/instruments_expiries.json`. Refresh both files and roll forward any
expired contracts with:

```bash
python manage.py update_instruments
```

This command invokes the helper in `My API/Data.py`, persists the JSON files,
and updates the database so each instrument always points to the next valid
expiry. To automate the refresh at 07:00 AM IST, add a cron entry similar to:

```
0 1 * * * /path/to/venv/bin/python /path/to/backend/manage.py update_instruments >> /var/log/quantstrike_instruments.log 2>&1
```

(`0 1 * * *` runs at 01:00 UTC which is 07:00 IST.)

## Testing

```bash
python manage.py test
```
