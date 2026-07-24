# Frontend

Next.js app (App Router, static export via `output: "export"`). `next build`
writes a static site to `out/`, which the FastAPI backend serves at the root.

## Pages

- `/signin`, `/signup` - auth forms calling `/auth/signin` and `/auth/signup`;
  the `{user, token}` response is stored in `localStorage` and the token is sent
  as `Authorization: Bearer` on API calls (`lib/auth.ts`).
- `/dashboard` - client-gated studio placeholder; redirects to `/signin` when no
  valid session is present.

Auth is entirely client-side (no server middleware), per the static-export
design in `docs/PLAN.md`.

## Develop

```bash
npm install
npm run build          # produces out/, served by the backend
npm run dev            # localhost:3000; set NEXT_PUBLIC_API_BASE to the backend
```

For the full app, run the backend (which serves the built `out/`) or the Docker
container - see the repo README.
