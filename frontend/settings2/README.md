# Settings 2 Frontend

A dedicated Next.js (TypeScript) UI that modernizes the legacy `/settings` template. It consumes the existing FastAPI backend without any backend changes and surfaces the controls at `/settings2` on the Next dev server.

> **⚠️ IMPORTANT**: `/settings` is **DEPRECATED**. All new features and changes should be made to `/settings2`. The legacy `/settings` endpoint (Jinja2 template) is maintained for backwards compatibility only.

## Stack
- Next.js App Router, React 18, and TypeScript
- Tailwind CSS, Radix Switch (shadcn-style atoms), lucide-react icons, and Framer Motion animations
- Session cookies are forwarded via `fetch` with `credentials: 'include'`

## Getting Started

```bash
cd frontend/settings2
npm install
npm run dev
```

By default the app expects the backend at `http://localhost:8444`. Override via:

```bash
export NEXT_PUBLIC_API_BASE_URL="https://your-domain.com"
```

Then visit [http://localhost:3000/settings2](http://localhost:3000/settings2). Every toggle calls the same API endpoints used by `/settings`, so feature parity is maintained.

## Available Scripts
- `npm run dev` – Next.js dev server with hot reload
- `npm run build` – Production build output
- `npm run start` – Runs the compiled app
- `npm run lint` – ESLint using `eslint-config-next`

## Notes
- Auth/session checks use `/api/v1/auth/check` and redirect to `/login` when the backend reports 401.
- Toggle mutations annotate updates with `"updated_by": "Next Settings"` for audit parity.
- UI primitives live under `components/ui/` so additional shadcn components can be dropped in later without refactors.
