# QuantStrike Frontend

Modern React UI for the QuantStrike platform built with Vite, React 19, Redux Toolkit, and Tailwind CSS.

## Requirements

- Node.js 18+ (recommended for full Tailwind/Vite ecosystem compatibility)
- npm 9+

## Setup

```bash
cd frontend
rm -rf node_modules package-lock.json # if migrating from CRA
npm install
npm run dev
```

The Vite dev server runs at [http://localhost:5173](http://localhost:5173) and expects the Django API at `VITE_API_BASE_URL`.

### Environment Variables

Create a `.env` file next to `package.json` when you need to override defaults:

```
VITE_API_BASE_URL=http://localhost:8000/api
```

## Available Scripts

- `npm run dev` – start the Vite development server
- `npm run build` – create a production build
- `npm run preview` – serve the production build locally
- `npm test` – run unit tests with Vitest + Testing Library
- `npm run lint` – run ESLint with the flat config

## Technology

- React 19 with Vite + SWC-based fast refresh
- Redux Toolkit + React Redux for state management
- Axios for API requests
- Tailwind CSS for styling, configured in `tailwind.config.js`

The UI surfaces the trading strategy dashboard, providing live strategy listings and creation flows aligned with the backend REST API.
