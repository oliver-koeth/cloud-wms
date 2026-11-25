# Cloud WMS

Cloud WMS is a task-oriented warehouse user experience that uses ERPNext as its
inventory and transaction backend. ERPNext remains an unmodified upstream
distribution. This repository owns the product specifications, local orchestration
and—starting in the next implementation phase—the custom dark WMS user interface.

The first specified journey is the external order flow:

`external sales order → ERPNext Pick List → WMS picking UI → Delivery Note → stock update`

Its requirements are in [spec/external-order-flow.md](spec/external-order-flow.md).

## What is here today

- An ERPNext `v16.60.0` source submodule at `vendor/erpnext`, retained unchanged.
- Scripts that run Frappe's unmodified `frappe_docker` disposable local evaluation
  stack at a pinned upstream commit; that compose file is verified to use the
  official `v16.60.0` ERPNext image.
- Architecture and contribution boundaries for the implemented UI and later
  custom WMS API layer.
- A Vue 3/TypeScript WMS UI in `ui/`, using Frappe UI and ERPNext session login.

## Prerequisites

- Git
- Docker Desktop (or Docker Engine) with Docker Compose (`docker compose` or
  `docker-compose`)
- At least 4 GB of Docker memory recommended for ERPNext and its supporting services

## Quick start

```sh
git submodule update --init --recursive
make up
```

The first start downloads the official Frappe Docker support checkout and ERPNext
container image, then creates the local site. It may take a few minutes. Visit
<http://localhost:8080> and use the local evaluation credentials:

```text
User: Administrator
Password: admin
```

Check progress with `make status` or `make logs`; stop the services with
`make down`. Docker volumes are intentionally retained between starts.

Run `make help` for every command and `make verify` for a no-container scaffold
check.

### Custom Frappe app (`apps/cloud_wms`)

`make up` first builds `cloud-wms/erpnext:v16.60.0-wms` (`make image`): the
unmodified upstream ERPNext image plus the `cloud_wms` app. Install it on the
running site, then optionally create the local demo data:

```sh
make install-app   # first time; use `make migrate` after later app changes
make demo-data     # local only: users, warehouse locations, stock
```

If the stack was already running, `make up` recreates the containers with the new
image; site data is kept in Docker volumes.

Demo users (password `admin` for all; log in by username or email):

| Username | Roles | Purpose |
| --- | --- | --- |
| `Sales` | Sales User, WMS Intake | Creates and submits Sales Orders |
| `Supervisor` | WMS Supervisor, Picker, Dispatch | Claims/assigns tasks, cancels, dispatches |
| `Worker` | WMS Picker | Self-claims and picks |

Run the app tests with `make app-test`. They use a separate, disposable stack
(`cloud-wms-test`) and never touch the running site; the first run creates a test
site and takes several minutes. `make app-test-clean` removes it.

## WMS UI prototype

With ERPNext running, start the separate client in a second terminal:

```sh
make ui-install
make ui-dev
```

Open <http://localhost:5173>. Sign in with an existing ERPNext user; the local
evaluation stack initially provides `Administrator` / `admin`. The Vite dev
server proxies `/api` requests to ERPNext, so its normal session cookie and the
user's ERPNext permissions govern data access.

The first UI slice includes:

- Tactical intake that creates a real **draft ERPNext Sales Order**.
- An explicit button to add one local demo Customer and Item if the fresh site
  has no master data.
- Self-claimable pick tasks, a camera-scanner interface with a manual fallback,
  and local task state persisted in the browser.
- Mandatory QA approval for short picks and a mock-only dispatch label/step.

The test-order integration is real. Pick, QA and dispatch states are intentionally
labelled as local prototype workflow data until the custom Frappe API is
implemented. Build and test with `make ui-build` and `make ui-test`.

### Prototype capability boundary

| Available now | Deliberately not implemented yet |
| --- | --- |
| ERPNext session login; master-data reads; opt-in demo Customer/Item creation; draft Sales Order creation | External-order connector; ERPNext Pick List creation/assignment; stock reservation; persistent QA/audit state; Delivery Note submission; stock-ledger posting |
| Local workboard, self-claim, camera/manual scan interaction, short-pick QA and mock dispatch | Production workflow API, idempotency, server-side permissions for WMS operations and carrier integration |

The camera scanner asks the browser for camera permission and uses the browser's
`BarcodeDetector` capability where available. A scanner-input/manual-entry
fallback is intentionally retained for unsupported browsers and dedicated barcode
scanners.

## Deliberate boundaries

- Do not edit `vendor/erpnext` or create commits inside it. Update it only through
  a reviewed submodule pointer change.
- Do not put WMS UI code in ERPNext, Frappe Desk, or the local `frappe_docker`
  checkout. UI code belongs under `ui/`; WMS orchestration belongs under a
  separately created custom Frappe app.
- The bundled local stack is an upstream disposable evaluation setup. It is not a
  production or tenant deployment blueprint.
- ERPNext Desk remains available to administrators. The WMS UI is not a security
  boundary; future backend APIs must enforce role and record permissions.

## Implemented design direction

The WMS prototype uses a dark operational interface: nearly-black surfaces,
high-contrast white text, and a safety/accessibility-tested industrial yellow
accent inspired by Jungheinrich. These are initial design tokens—not a claim of
official brand approval—and need a formal brand review before any external use.

| Token | Proposed value | Intended use |
| --- | --- | --- |
| Canvas | `#080A0C` | Application background |
| Surface 01 | `#101317` | Cards |
| Surface 02 | `#171B20` | Raised and interactive areas |
| Border | `#2A3037` | Structural separation |
| Signal | `#FFD500` | Primary action, active state and focus accent |
| Text | `#F5F7F8` | Primary content |
| Muted | `#949CA5` | Secondary labels and metadata |
| Success | `#35D07F` | Healthy system state |
| Error | `#FF5252` | Fault and destructive state |

See [ARCHITECTURE.md](ARCHITECTURE.md) and [AGENTS.md](AGENTS.md) before changing
the project.
