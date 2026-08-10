# `origo-platform`

The operator dashboard. React + TypeScript + Vite, talking to `origo-edge` over plain
REST (`shared/api/client.ts`). Design reference: [`PQC-HSM-Design.md`](PQC-HSM-Design.md) §6.

## Structure

```
origo-platform/
├── src/
│   ├── main.tsx
│   ├── app/
│   │   ├── App.tsx              # shell: sidebar + topbar + routed views
│   │   ├── providers.tsx        # QueryClientProvider
│   │   ├── queryClient.ts
│   │   └── router.tsx
│   ├── features/
│   │   ├── overview/OverviewView.tsx
│   │   ├── devices/{DevicesView,NewDeviceDialog}.tsx
│   │   ├── passes/PassesView.tsx
│   │   ├── jobs/{JobsView,NewJobDialog,JobResultPanel}.tsx
│   │   ├── keys/KeysView.tsx
│   │   ├── telemetry/TelemetryView.tsx
│   │   ├── policies/PoliciesView.tsx
│   │   ├── alerts/AlertsView.tsx
│   │   └── audit/AuditView.tsx
│   └── shared/
│       ├── api/client.ts        # typed fetch wrapper
│       └── lib/time.ts          # relative + absolute-UTC formatting
```

## What's wired to real data vs. still fixture-backed

Views call `origo-edge` directly (`request<T>('/devices')` etc.) — nothing in this
repo hardcodes data itself. What each view actually returns depends entirely on
whether the matching `origo-edge` route is DB-backed yet: `DevicesView`, `KeysView`,
`JobsView`, `OverviewView` show real Postgres data. `PassesView`, `TelemetryView`,
`PoliciesView`, `AlertsView`, `AuditView` show whatever `origo-edge`'s `platform.py`
still hardcodes — see [`origo-edge.md`](origo-edge.md)'s fixture table. If a view looks
wrong, check which side of that line its backing route is on before assuming a
frontend bug.

## The two request flows this repo adds

**Registering a device** (`NewDeviceDialog.tsx`) — `POST /devices`, invalidates the
devices query on success. This is what replaced curl-only seeding.

**Creating a job** (`NewJobDialog.tsx`) — `POST /jobs`, with a job-type toggle that
switches the form between a KEM-parameter-set selector (key exchange) and a priority
selector (data delivery). Both dialogs use plain `useState`, not `react-hook-form`/
`zod` — deliberately, to match the rest of the codebase's dependency footprint rather
than introducing a validation library used nowhere else.

**Viewing a result** (`JobResultPanel.tsx`) — polls `GET /jobs/{id}` every 5s while
the job is non-terminal, stops once it reaches `active`/`failed`/`timed_out`. For a
completed data-delivery job, renders `result_preview` (frame count, byte size) plus a
download link to `GET /jobs/{id}/result`. For key exchange, deliberately shows nothing
about the key itself beyond its state — key material never crosses this boundary by
design, and the panel should not create a UI affordance implying it might.

## Running it

```bash
npm ci
npm run dev            # http://localhost:5173, proxies /v1 to localhost:8000 in dev
# or: make dev-ui, from repo root
```

## Tests

```bash
npm test
```

| File | Proves |
|---|---|
| `shared/lib/time.test.ts` | Relative-time formatting across seconds/minutes/hours/days, both past and future |
| `features/jobs/NewJobDialog.test.tsx` (see `docs/use-cases.md` for the scenario) | Submitting the form sends the right body; a 400 response shows an inline error and leaves the dialog open |

The MSW-based tests above prove the *component* behaves correctly against a mocked
network layer — they do not prove `origo-edge` is actually reachable at the paths
called. That's the manual smoke test in the root `README.md`: register two devices
through the running UI, create a job, confirm the row appears. Worth re-running by hand
after any change to `shared/api/client.ts` or to a route path on the `origo-edge` side,
since it's the one thing no automated test here exercises end to end.

## Known gaps

- **Duplicate files:** both `src/App.tsx` and `src/app/App.tsx` exist, and both
  `vite.config.ts` and `vite.config.js`/`vite.config.d.ts` exist. The `app/` and
  `.ts` versions are the ones actually referenced by `main.tsx` and the build —
  the flat `src/App.tsx` and the `.js`/`.d.ts` config files look like leftovers from
  before the `app/` restructure and a stray build output, respectively. Worth deleting
  once confirmed unreferenced (`grep -r "from '.*[^/]App'" src/main.tsx` and a
  `git log` on the `.js`/`.d.ts` pair to check whether they're actually gitignored
  build artifacts that got committed by accident) rather than leaving both around for
  someone to import the wrong one later.
- No e2e/Playwright layer — the manual smoke test above is currently the only thing
  that exercises the real network path.