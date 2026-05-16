# QuantStrike Frontend

React UI for the QuantStrike automated trading platform. Built with Vite, React 19, Redux Toolkit, and Tailwind CSS.

## Requirements

- Node.js 18+
- npm 9+

## Setup

```bash
cd frontend
npm install
npm run dev
```

The dev server runs at [http://localhost:5173](http://localhost:5173). API requests to `/api` are proxied to `http://localhost:8000` via `vite.config.js` — no environment variables needed for local development.

## Available Scripts

- `npm run dev` – start the Vite dev server with API proxy
- `npm run build` – create a production build
- `npm run preview` – serve the production build locally
- `npm test` – run unit tests with Vitest + Testing Library
- `npm run lint` – run ESLint with the flat config

## Pages

- **Home** — Dashboard with brokerage connection, API key management, strategy status
- **Trades** — Active and closed trades with P&L
- **Instruments** — Manage trading instruments (NIFTY, BANKNIFTY, SENSEX)
- **Logs** — Strategy execution logs with Summary/Raw toggle
- **Backtest** — Run historical backtests

## Technology

- React 19 with Vite + SWC-based fast refresh
- Redux Toolkit + React Redux for state management
- Axios for API requests
- Tailwind CSS for styling
