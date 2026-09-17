# Frontend

Next.js App Router app for Permission-Aware Customer Commitment Intelligence, wired to the real FastAPI backend as of Milestone 7.

## Run

Requires the backend running with `ENABLE_DEMO_MODE=true` and a seeded demo org (`python -m app.demo.seed` from `backend/`; see the repo root `CLAUDE.md`). Copy `.env.example` to `.env.local` (server-only `BACKEND_URL`, defaults to `http://localhost:8000`).

From the repository root:

```bash
npm install
npm run dev
```

Routes:

- `/` — real account list for the currently selected demo persona (`GET /accounts`).
- `/accounts/[slug]` — the primary product surface: real commitments/evidence, plus an "Ask about this account" panel backed by `POST /answer`.
- `/search` — real permission-aware evidence search (`POST /search`), independent of the account-page Ask panel.
- `/audit` — an honest placeholder. The backend computes a real permission-safe trace per request, but nothing is persisted, so there's no history to browse; this page was deliberately not built out to fake one.

## Identity

There is no real authentication. A demo-persona switcher in the header lets you pick one of the seeded demo users; the choice is validated server-side against `GET /dev/demo-users` before being written to an `httpOnly` session cookie, and every backend call derives its `X-User-Id` from that cookie server-side — the browser never asserts an identity directly. See `src/lib/api/session.ts` and `src/app/actions.ts`.

## Important

`src/lib/api/` is the only place this app talks to the backend (`server-only`, `cache: "no-store"` throughout) — see the repo root `CLAUDE.md`'s "Milestone 7" section for the full identity/network design. There is no client-side permission filtering anywhere in this app; every authorization decision is made by the backend.
