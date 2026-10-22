# PromiseLoop - frontend

React 19 + TypeScript + Vite + Tailwind v4 UI for PromiseLoop.

See the [root README](../README.md) for the full setup: install the API in `../backend`
first, then

```bash
npm install
cp .env.example .env.local   # put your SEED_API_KEY in VITE_API_KEY
npm run dev                  # http://localhost:5173
```

The dev server proxies `/api` to `http://127.0.0.1:8000`.

```bash
npm test        # vitest
npm run build   # type-check + production build
```
