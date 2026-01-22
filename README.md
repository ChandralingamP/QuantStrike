# QuantStrike

QuantStrike is a full-stack trading strategy management platform featuring a modern React frontend and a Django backend backed by PostgreSQL.

## Project Structure

- `frontend/` – React + Redux Toolkit + Tailwind CSS UI
- `backend/` – Django REST API exposing strategy endpoints
- `docs/` – Product documentation and notes

## Quick Start with Docker

```bash
docker compose up --build
```

The command launches:

- PostgreSQL on `localhost:5432`
- Django API on `http://localhost:8000`
- React dev server on `http://localhost:5173`

## Manual Setup

### Backend

```bash
cd backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python3 manage.py migrate
python3 manage.py runserver
```

### Frontend

```bash
cd frontend
rm -rf node_modules package-lock.json # if migrating from CRA
npm install
npm run dev
```

Set `VITE_API_BASE_URL` in `.env` if the backend runs on a non-default host or port.

## Testing

- Backend: `python manage.py test`
- Frontend unit tests: `npm test`
- Frontend linting: `npm run lint`

## Next Steps

- Harden authentication and authorization flows
- Add WebSocket streaming for live trading metrics
- Integrate CI/CD pipelines for automated testing and deployments
