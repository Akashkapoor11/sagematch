# SageMatch React frontend

React + Vite UI for the Zoftware Hireathon SageMatch application.

## Local development

```bash
npm install
npm run dev
```

Vite proxies `/api` to `http://127.0.0.1:8000`.

## Production build

```bash
npm install
npm run build
```

The FastAPI container copies `dist/` into its static serving directory during the Docker build.

For separate hosting such as Vercel, configure:

```text
VITE_API_BASE_URL=https://YOUR-BACKEND.example.com
```

The backend must allow that origin through `CORS_ALLOWED_ORIGINS`.
