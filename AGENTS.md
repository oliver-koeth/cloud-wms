# Working agreement

## Product boundary

Cloud WMS is a separate task-oriented interface over ERPNext. Preserve ERPNext as
an unchanged upstream distribution. Do not modify `vendor/erpnext`, copy ERPNext
logic into the UI, or bypass ERPNext document validation and posting.

## Repository layout

| Path | Ownership | Purpose |
| --- | --- | --- |
| `vendor/erpnext` | Upstream Git submodule | Read-only ERPNext source reference |
| `.runtime/frappe_docker` | Generated, ignored | Unmodified upstream local runtime support |
| `spec/` | This repository | Product and workflow specifications |
| `ui/` | This repository | Standalone Vue 3/TypeScript WMS client using Frappe UI |
| `apps/cloud_wms` | This repository | Custom Frappe app: roles, permissions, idempotency, audit, workflow API (built into `docker/Containerfile`) |

## Implementation rules

- Keep warehouse-worker workflows separate from ERPNext Desk forms.
- Server-side code owns permission enforcement, idempotency, document lifecycle,
  and ERPNext adapters. The UI never holds an Administrator password or API key.
- Use ERPNext APIs and the normal `Pick List` / `Delivery Note` lifecycle. Never
  write stock ledger records directly.
- Represent physical locations through ERPNext's `Warehouse` hierarchy unless a
  later, approved model explicitly changes that decision. ERPNext `Bin` is an
  aggregate stock record, not a physical location.
- Keep UI colours as semantic tokens; do not scatter raw brand colours.
- Add tests alongside implementation. For external-order actions, test retries,
  stale data, duplicate scans, permissions and document submission failures.

## Current UI

`ui/` is implemented and runs through Vite at `http://localhost:5173` during
local development. Use `make ui-install`, `make ui-dev`, `make ui-test` and
`make ui-build` from the repository root.

- Authentication uses the signed-in ERPNext user's normal session through the
  Vite `/api` proxy. Never put an ERPNext Administrator password or API key in
  frontend code.
- The implemented ERPNext integration is deliberately limited to session login,
  read access to `Company`, `Customer`, `Item` and `Warehouse`, and order intake
  through `cloud_wms.api.orders.ingest` (submitted `Sales Order`; the UI generates
  one idempotency key per distinct submission).
- The workboard, claim, pick confirmation and short-pick approval use
  `cloud_wms.api.tasks.*`, which manage real ERPNext Pick Lists. Dispatch uses
  `cloud_wms.api.dispatch.confirm`, which submits a real ERPNext Delivery Note;
  never mark a task dispatched in the UI before that call returns.
- Do not extend direct browser calls to ERPNext for operational workflow writes.
  Add the custom Frappe API under `apps/` first, with permission checks,
  idempotency and audit records.
- Camera scanning relies on browser camera permission and `BarcodeDetector` when
  available. Preserve the manual/scanner-input fallback.

### Current visual tokens

Use semantic CSS variables/tokens rather than raw values in components. The
implemented UI uses Canvas `#080A0C`, Surface 01 `#101317`, Surface 02
`#171B20`, Border `#2A3037`, Signal `#FFD500`, Text `#F5F7F8`, Muted `#949CA5`,
Success `#35D07F` and Error `#FF5252`. These are a proposed digital extension
inspired by Jungheinrich, not official brand tokens.

## Code discovery

This project uses `codebase-memory-mcp` to maintain a knowledge graph. Prefer its
tools for code discovery in this order:

1. `search_graph`
2. `trace_path`
3. `get_code_snippet`
4. `query_graph`
5. `get_architecture`

Use `rg` only for string literals, configuration and non-code files, or when the
graph has insufficient coverage.

## Local runtime

Use `make up`, `make status`, `make logs`, and `make down`. After changing `apps/cloud_wms`, run `make image` (or `make up`), `make migrate`, and `make app-test`; app tests must run on the isolated test stack, never the live site. Do not commit `.env`,
`.runtime/`, container data, or generated frontend dependencies. The current
Frappe Docker stack is for local evaluation only; do not describe it as production
ready.
