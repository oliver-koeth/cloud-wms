# Architecture

## Decision

Use ERPNext as the inventory transaction engine and build a separate Cloud WMS
experience over it. ERPNext and the Frappe Framework remain upstream software;
the WMS does not fork, patch or replace their stock, accounting or document
lifecycle logic.

```text
Warehouse operator
        │
        ▼
Current Cloud WMS UI (this repo: ui/)
ERPNext session login • Sales Order intake • Pick List workboard
        │ standard ERPNext REST API today
        ▼
ERPNext (upstream, unchanged)
Company • Customer • Item • Warehouse • Sales Order

Future production path
Warehouse operator → WMS UI → custom Frappe app (this repo: apps/)
                                  │ permission checks • idempotency • audit
                                  ▼
                         ERPNext Pick List • Delivery Note • stock ledger
        │
        ▼
MariaDB / Redis / background workers
```

## Local evaluation environment

`make up` performs two distinct actions:

1. It initialises the `vendor/erpnext` Git submodule at the upstream
   `v16.60.0` release commit. The checkout is a source reference and must remain
   clean.
2. It runs Frappe's unmodified `pwd.yml` local evaluation stack from the pinned
   `frappe_docker` commit `f5c32e532c6b3d1549ad4a530f7e5a7d4d2d76e9` in ignored
   `.runtime/`. The launcher verifies that it uses the official ERPNext
   `v16.60.0` image.

The runtime contains Frappe, ERPNext, MariaDB, Redis, workers, scheduler,
websocket and nginx frontend. It creates one disposable local site at
`http://localhost:8080`.

The stack runs `cloud-wms/erpnext:v16.60.0-wms`, built from
`docker/Containerfile`: the upstream `frappe/erpnext:v16.60.0` image with
`apps/cloud_wms` copied in and pip-installed. `docker/compose.cloud-wms.yml`
overrides only the `image:` of the upstream services, so `pwd.yml` stays
unmodified. `make install-app` / `make migrate` then apply the app to the site.

### `cloud_wms` app (Phase 1 foundation)

- WMS roles (`WMS Intake`, `WMS Picker`, `WMS Dispatch`, `WMS Supervisor`) and a
  `Custom DocPerm` matrix for Sales Order, Pick List, Stock Reservation Entry and
  Delivery Note. Adding the first custom rule to a doctype freezes ERPNext's
  standard permissions for it into `Custom DocPerm`; later ERPNext permission
  changes for those doctypes no longer apply automatically.
- Custom fields: `Sales Order.cloud_wms_source` / `cloud_wms_external_order_id`
  and `Warehouse.cloud_wms_location_barcode` (each leaf bin is a Warehouse).
- Stock Settings: stock reservation enabled, auto-reserve off (reservation is
  created from the Pick List at completion).
- `WMS Request` (idempotency keys with stored responses) and `WMS Task Event`
  (append-only audit; plain Data references so draft Pick Lists can be deleted).
- `@wms_endpoint` decorator: role guard, correlation id, error envelope
  (`{"error": {code, message, next_action, correlation_id}}` with a matching HTTP
  status) and idempotent replay.
- `cloud_wms.api.session.context` returns the caller's WMS roles and warehouses.
- `cloud_wms.setup.demo` creates local-only demo users, locations and stock.

The order, task and dispatch endpoints (`cloud_wms.api.orders`, `tasks`,
`dispatch`) are described below; the UI calls only these for workflow writes.

`make app-test` runs the app's tests on a separate disposable stack because the
idempotency service commits mid-request.

## Responsibilities

| Layer | Owns | Must not own |
| --- | --- | --- |
| WMS UI | Scanner-led task screens, accessible feedback, local interaction state | Stock posting, administrative credentials, ERPNext business rules |
| WMS app/API | Authentication/authorization, request validation, idempotency, workflow translation | Direct stock-ledger writes or client-trusted permissions |
| ERPNext | Pick lists, delivery notes, reservations, validation, stock ledger and accounting integration | WMS-specific interaction design |
| Desk | Administrator setup and exception handling | Everyday operator workflow |

## Data and security boundaries

- A browser session or OAuth-style mechanism will authenticate operators; no
  administrator API credential may be delivered to the UI.
- API operations must verify both warehouse/data permission and document state at
  the moment of action. Hiding Desk modules is not access control.
- Actions that may be retried by a scanner or network client need an idempotency
  key recorded server-side.
- Keep ERPNext canonical. Do not create a parallel inventory ledger in the UI or
  WMS app. [DATAMODEL.md](DATAMODEL.md) lists the ERPNext tables, the WMS custom
  fields and doctypes, and the proposed admin screens.
- One tenant should eventually map to an isolated Frappe site/database. ERPNext
  `Company` is not a replacement for SaaS tenant isolation.

## First vertical slice

The external order flow is deliberately selected to validate the boundary:

```text
External sales order → ERPNext Sales Order / Pick List → WMS scan-and-confirm
→ Delivery Note submission → ERPNext stock ledger update
```

The full behavioural contract, outstanding decisions and acceptance criteria are
in [spec/external-order-flow.md](spec/external-order-flow.md). The flow is
implemented end to end for manually entered orders; the boundary below records
what the UI does and may call.

## UI boundary

`ui/` is a standalone Vue 3 + TypeScript client using Frappe UI. Its development
server proxies ERPNext's `/api` route. Orders are submitted through the
`cloud_wms.api.orders.ingest` endpoint, which creates and submits the
`Sales Order` under the user's own session and permissions. The UI can also read
Customer, Item, Warehouse and Company records needed for the order form. Demo
master data comes from `make demo-data`, never from the browser. The UI has a camera-scanner interaction using
`BarcodeDetector` when the browser supports it, plus a manual-entry fallback.

The browser holds only the ERPNext session cookie; it never receives an
Administrator API key. Pick tasks are real ERPNext `Pick List` documents managed
by `cloud_wms.api.tasks.*` (see below). Dispatch is `cloud_wms.api.dispatch.confirm` (see below); the UI shows a
Delivery Note as submitted only after that call returns it.

### Direct ERPNext calls allowed from the browser

| Purpose | Standard ERPNext API | Restriction |
| --- | --- | --- |
| Sign in/out | `POST /api/method/login`, `POST /api/method/logout` | User session only; no embedded credentials |
| Populate tactical order form | Read `Company`, `Customer`, `Item`, `Warehouse` resources | ERPNext permission controlled |

Orders enter only through `POST /api/method/cloud_wms.api.orders.ingest` (role
`WMS Intake`; requires an `idempotency_key`; duplicate `source` + `external_order_id`
returns the existing order). No browser call may create a Pick List, Delivery Note, stock transaction or
workflow/audit record directly; those operations go through the custom Frappe API.

### Pick task API (`cloud_wms.api.tasks`)

A pick task *is* a Pick List. A Sales Order is claimable while it is submitted,
has remaining quantity and no active Pick List. All endpoints are role-checked
(Picker or Supervisor unless noted), and mutations require an `idempotency_key`.

| Endpoint | Effect |
| --- | --- |
| `list_tasks` (GET; Picker, Supervisor, Dispatch) | `{claimable, active}`; pickers see only their own claims |
| `get` (GET) | One task |
| `claim` | Creates a draft Pick List (scan mode, manual picking), assigns it via ToDo; only a Supervisor may assign someone else |
| `release` | Deletes the draft; a picker may release only before any scan |
| `confirm_location`, `confirm_pick` | Validate location barcode, item barcode and quantity (no overpick) |
| `record_shortage` | Marks a line Pending; blocks completion until approved |
| `approve_shortage` (Supervisor) | Reduces the line to the picked quantity, or removes it; an empty Pick List is deleted |
| `complete` | Requires every line fully picked or approved short; submits the Pick List and creates stock reservations when enabled |

### Dispatch API (`cloud_wms.api.dispatch`)

| Endpoint | Effect |
| --- | --- |
| `confirm(pick_list, reference?)` (Dispatch; idempotent) | Requires a submitted Pick List. Finds or creates the Delivery Note with ERPNext's `create_delivery_note` (picked quantities only), stores `reference` in `lr_no`, submits it and returns the Delivery Note with posting date and time. A repeat call returns the existing submitted note (`already_dispatched`) and never creates a second one |

The mapper and submission run as the system user because they read customer,
address and tax masters the Dispatch role cannot; the endpoint checks the role
first and the note's owner is set to the dispatcher. Partial delivery works
through approved short picks: only picked quantities are delivered, and the
Sales Order becomes claimable again for the remainder. Product bundles are not
handled.

Per-line state lives in custom fields on `Pick List Item`
(`cloud_wms_location_confirmed`, `cloud_wms_shortage_state`,
`cloud_wms_shortage_reason`). Every step records an immutable `WMS Task Event`.
