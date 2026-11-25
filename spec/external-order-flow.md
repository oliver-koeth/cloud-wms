# External order flow specification

**Status:** Production workflow proposed; prototype UI partially implemented  
**Scope:** The first end-to-end WMS vertical slice  
**Primary users:** Warehouse picker, packing/dispatch operator, warehouse
administrator

## Implementation status

The repository contains a deliberately constrained UI prototype, not a completed
external-order workflow.

| Implemented in `ui/` | Still proposed / not implemented |
| --- | --- |
| ERPNext session login; reads of Company, Customer, Item and Warehouse; explicit local demo Customer/Item setup; draft Sales Order creation | External-order source ingestion and idempotency; Pick List creation/allocation; reservation; server-side task/QA audit records; Delivery Note submission; stock-ledger update |
| Browser-local self-claim, pick quantity, short-pick QA and mock dispatch state | Custom Frappe API, role/warehouse enforcement for WMS operations, retry-safe workflow commands and carrier integration |
| Camera-scanner interface with manual-entry fallback | Guaranteed camera availability or barcode decoding in every browser/device |

The prototype uses standard ERPNext REST resources only for tactical order intake.
Its local workboard state is not ERPNext workflow state and must never be treated
as a submitted Pick List or Delivery Note.

## 1. Goal

Enable a warehouse operator to fulfil an order that originated outside the WMS
without exposing ERPNext Desk documents as the operational user experience.

The happy path is:

```text
External order accepted
  → order is represented in ERPNext
  → ERPNext Pick List is created and assigned
  → operator scans locations and items, confirms quantities
  → dispatch operator confirms shipment
  → ERPNext Delivery Note is submitted
  → ERPNext updates the stock ledger
```

ERPNext remains the system of record for stock and delivery posting. The WMS UI
does not calculate or post inventory itself.

## 2. In scope

- Import or creation of an ERPNext Sales Order from a validated external order.
- Selecting and assigning an ERPNext `Pick List`.
- Location-directed, barcode-supported picking against that list.
- Short-pick and exception capture without silently overpicking.
- Packing/dispatch confirmation that creates and submits an ERPNext `Delivery Note`.
- Clear task status, audit trail, error recovery and retry-safe server actions.

## 3. Out of scope for the first slice

- Building the integration connector for a particular external ERP, shop or
  marketplace.
- Carrier-label generation, manifesting, customs, returns and wave optimisation.
- Offline-first operation.
- Automated replenishment, cycle count, lot/serial-specific UX and multi-order
  batch picking. These must be designed separately even if ERPNext supports their
  underlying records.
- A custom physical-location data model. Use the configured `Warehouse` hierarchy
  for the slice.

## 4. Actors and permissions

| Actor | Permitted actions | Not permitted |
| --- | --- | --- |
| Picker | View assigned pick tasks; scan and confirm lines; record shortages | Access unassigned orders; submit deliveries; change item master data |
| Dispatch operator | Review picked order; pack and dispatch; resolve approved dispatch exceptions | Alter stock directly; administer roles/configuration |
| Warehouse supervisor | Assign/reassign tasks; approve controlled exceptions; view operational audit history | Circumvent ERPNext posting controls |
| ERPNext administrator | Configure masters, roles and integrations; use Desk for exceptional maintenance | Routine mobile picking as an operator workflow |
| External order source | Submit an authenticated, idempotent external order message | Directly create stock ledger entries or Delivery Notes |

Every server operation must re-check ERPNext/Frappe permissions and warehouse
scope; a hidden UI control is never an authorization mechanism.

## 5. Canonical objects and ownership

| Business concern | Canonical ERPNext object | WMS responsibility |
| --- | --- | --- |
| External demand | `Sales Order` (or a documented equivalent) | Show a task-oriented summary, preserve source reference |
| Work to pick | `Pick List` and its locations/items | Guide scan/quantity confirmation; do not replace allocation logic |
| Product and barcode | `Item` / item barcode | Resolve a scan within the allowed pick line |
| Physical position | Leaf in `Warehouse` hierarchy | Render the route/location label and verify scan |
| Dispatch transaction | `Delivery Note` | Create from fulfilled source document and submit only after controls pass |
| Inventory truth | Stock Ledger and ERPNext stock transaction lifecycle | Never write directly |

`Bin` is not a physical storage position; it is ERPNext's aggregate stock record
for an item and warehouse. The WMS should not present it as a rack/bin scan target.

## 6. States and transition rules

The WMS expresses task state while retaining ERPNext document status as canonical.

| WMS task state | ERPNext condition | Entry | Allowed next state |
| --- | --- | --- | --- |
| `ready` | Eligible Pick List exists and is unassigned | Import/allocation completes | `assigned`, `blocked`, `cancelled` |
| `assigned` | Pick List is assigned to a picker | Supervisor assignment or self-claim (if enabled) | `in_progress`, `ready`, `blocked` |
| `in_progress` | Picker has started one or more lines | First successful scan/confirmation | `picked`, `exception`, `blocked` |
| `exception` | Mismatch, shortage or stale allocation requires decision | Controlled exception action | `in_progress`, `blocked`, `cancelled` |
| `picked` | All required lines confirmed or approved short-pick resolution recorded | Last line completes | `ready_to_dispatch`, `blocked` |
| `ready_to_dispatch` | Packing review passes | Dispatch handoff | `dispatched`, `exception`, `blocked` |
| `dispatched` | Delivery Note submitted successfully | ERPNext submission succeeds | terminal |
| `blocked` | Backend/permission/source state prevents safe work | Validation or integration failure | Prior valid state after resolution, `cancelled` |
| `cancelled` | Source order or pick document cancelled | Cancellation sync | terminal |

The WMS must not call a transition successful until the corresponding ERPNext
operation has completed and its resulting document state is re-read.

## 7. Happy path

1. **Accept external order.** A future integration validates the source, captures
   a stable external order ID and submits an idempotent request. It creates or
   updates the agreed ERPNext source document and stores the source reference.
2. **Allocate work.** ERPNext creates a Pick List according to agreed allocation
   rules. A supervisor assigns it, or a permitted picker claims it. The WMS shows
   customer-facing references only where their role requires them.
3. **Start picking.** The picker opens a single task. The UI displays the next
   approved physical location, product identifier, target quantity and relevant
   lot/serial requirement only when configured.
4. **Confirm location.** The picker scans the location. The server validates that
   it matches an allowed open Pick List location. A mismatch never advances the
   task.
5. **Confirm item and quantity.** The picker scans the item barcode and confirms
   quantity. The server validates item, location, open quantity, UOM and task
   state. Duplicate delivery of the same request is harmless through an
   idempotency key.
6. **Complete picking.** After every line is confirmed, the server verifies the
   current Pick List and source order are still eligible, then marks the task
   ready for dispatch. If ERPNext data changed, it blocks the task and explains
   the recovery owner/action.
7. **Dispatch.** A dispatch operator reviews packed quantities and confirms the
   required reference. The backend creates the Delivery Note from the designated
   ERPNext source context, validates it, then submits it through ERPNext's normal
   lifecycle.
8. **Confirm result.** The backend re-reads the submitted Delivery Note and
   returns its immutable ERPNext identifier, timestamp and final state. ERPNext's
   own transaction processing updates the stock ledger.

## 8. Barcode and quantity behaviours

| Event | Required response |
| --- | --- |
| Correct location scan | Show/enable expected item confirmation |
| Wrong location scan | Reject without changing line progress; show expected and scanned labels |
| Correct item scan | Add one configured scan unit only when it resolves to the active line |
| Wrong item scan | Reject; do not substitute based only on a similar SKU |
| Quantity lower than expected | Require a shortage reason and configured supervisor decision where necessary |
| Quantity higher than expected | Reject by default; any allowed overpick requires an explicit approved rule |
| Same request retried | Return the already-recorded result; do not double-confirm or double-post |
| Item/location data changed mid-pick | Stop the affected task and require refresh/reallocation |

## 9. Exception handling

- **No stock at expected location:** record a shortage against the line; do not
  invent an alternative location. A supervisor may direct a controlled retry once
  allocation is updated.
- **Damaged goods:** record quantity and reason; the actual inventory disposition
  follows a separately approved ERPNext transaction, not a UI-only adjustment.
- **Pick List cancelled or reassigned:** stop the task immediately and remove the
  action controls after server confirmation.
- **External order amended/cancelled:** retain source/audit references, reconcile
  the ERPNext source document, then recompute WMS eligibility.
- **Delivery Note validation failure:** preserve the packed/picked task state,
  expose a human-readable error and ERPNext document identifier, and do not claim
  shipment completion.
- **Network failure:** the client retries only with the original idempotency key;
  the server returns the persisted outcome or safe next action.

## 10. Future custom WMS API boundary (contract only)

No custom WMS endpoints are implemented in this project. The UI prototype does
use standard ERPNext login and document-resource endpoints for session handling
and draft Sales Order intake, as described in `ARCHITECTURE.md`. The later WMS
app/API should offer task-oriented operations rather than generic browser access
to ERPNext doctypes.

| Operation | Inputs | Success result | Safety requirement |
| --- | --- | --- | --- |
| Ingest external order | Source, external ID, line payload, idempotency key | ERPNext source-document reference | Authenticate source; deduplicate external ID/key |
| List/claim task | Operator identity, warehouse scope | Eligible task summaries | Enforce assignment and warehouse permissions |
| Confirm location | Task ID, location barcode, idempotency key | Current line state | Re-read active assignment and location eligibility |
| Confirm pick | Task ID, item barcode, quantity, UOM, idempotency key | Updated line/task state | Validate ERPNext-derived expected quantity and state |
| Record exception | Task/line ID, reason, optional evidence, idempotency key | Exception record/state | Reason permissions and immutable audit record |
| Dispatch | Task ID, package/dispatch refs, idempotency key | Submitted Delivery Note reference | Submit through ERPNext document lifecycle only |

Responses must provide a user-safe error code, a recoverable next action and a
correlation ID. Avoid leaking administration, accounting or unrelated customer
data into a warehouse-operator response.

## 11. Acceptance criteria

1. An authorized picker can see only work assigned to them (or claimable work in
   their warehouse when explicitly enabled).
2. A location must be successfully confirmed before an item confirmation can
   advance its line.
3. Wrong location, item, UOM and quantity are rejected without changing ERPNext
   stock or falsely completing a line.
4. Replaying any scan or dispatch request with the same idempotency key does not
   duplicate a confirmation or create a second Delivery Note.
5. A dispatch creates and submits exactly one valid ERPNext Delivery Note via
   supported document operations; no direct stock-ledger write exists in WMS code.
6. A successfully submitted Delivery Note is re-read and displayed with its
   ERPNext reference before the WMS calls the task dispatched.
7. Source amendment, cancellation, lost permission and stale allocation block
   unsafe continuation and preserve an audit trail.
8. The picker/dispatch experience is mobile-friendly, keyboard/scanner operable,
   high-contrast and uses the semantic dark/yellow design tokens defined in the
   project README.

## 12. Decisions required before implementation

1. Which external systems are the first order sources, and what authentication,
   replay and amendment contract does each provide?
2. Is ERPNext `Sales Order` always the canonical source document, or are some
   external orders fulfilled via a different ERPNext transaction?
3. Who owns Pick List creation/allocation: automatic rule, supervisor, or
   integration? Is self-claim allowed?
4. Which warehouse hierarchy level is scannable and authoritative as a physical
   location for the first tenant?
5. Are partial shipment and short-pick allowed? Which roles/reasons approve them?
6. Which item UOM conversions, batches, serial numbers and expiry restrictions
   must be supported in the first release?
7. What operational event legally/contractually constitutes dispatch: packing
   complete, carrier handover, label generation or manifest close?
8. What retention, audit-export and tenant-isolation requirements apply?
