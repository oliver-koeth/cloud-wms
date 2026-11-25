# Data model

Cloud WMS has almost no data model of its own. ERPNext's documents remain the
source of record. The `cloud_wms` app adds:

- a few **custom fields** on standard ERPNext doctypes;
- two **custom doctypes**, both technical: `WMS Request` (idempotency) and
  `WMS Task Event` (audit).

A WMS *pick task* is not a table. It is a view of an ERPNext `Pick List`, with
its `ToDo` assignment and the `cloud_wms_*` fields on its rows. A *location* is a
leaf `Warehouse` that has a barcode.

This document has two parts:

- **Current model:** the tables the implemented flow reads and writes.
- **Proposed admin screens:** the CRUD screens and the small model changes they
  would need. These are *proposed* and not implemented.

Field lists show only the fields that the WMS uses or that an admin screen
needs. ERPNext doctypes have many more. Fields this app adds are marked
**WMS**.

## Conventions

- Every ERPNext table is `tab<DocType>` (for example `tabSales Order`) and has
  a string primary key, `name`. Child tables (`… Item`, `Item Barcode`) link to
  their parent through `parent`, `parenttype` and `parentfield`, and keep their
  order in `idx`.
- `docstatus` is `0` (draft), `1` (submitted) or `2` (cancelled). Submitted
  documents cannot be edited. They can only be cancelled and then amended into
  a new document.
- Tree doctypes (`Warehouse`, `Item Group`, `Customer Group`, `Territory`) use
  a parent link plus nested-set columns `lft` and `rgt`. Only leaf nodes
  (`is_group = 0`) can hold stock or be selected on transactions.
- Stock quantities are never written directly. `Bin` and `Stock Ledger Entry`
  change only when a stock transaction is submitted.

## Overview

```mermaid
flowchart LR
  subgraph Master["Master data"]
    Company --- Warehouse
    Item --- ItemBarcode["Item Barcode"]
    Customer --- Address
    Customer --- Contact
  end
  subgraph Flow["Order-to-ship flow"]
    SalesOrder["Sales Order"] --> PickList["Pick List"]
    PickList --> DeliveryNote["Delivery Note"]
    PickList -.-> SRE["Stock Reservation Entry"]
    DeliveryNote --> SLE["Stock Ledger Entry"]
    SLE --> Bin
  end
  subgraph WMS["cloud_wms app"]
    WmsRequest["WMS Request"]
    WmsEvent["WMS Task Event"]
  end
  Customer --> SalesOrder
  Item --> SalesOrder
  Warehouse --> PickList
  PickList -. "assignment" .-> ToDo
  WmsEvent -. "soft refs" .-> SalesOrder
  WmsEvent -. "soft refs" .-> PickList
  WmsEvent -. "soft refs" .-> DeliveryNote
```

## Master data

```mermaid
erDiagram
  Company ||--o{ Warehouse : owns
  Warehouse |o--o{ Warehouse : "parent_warehouse"
  ItemGroup |o--o{ ItemGroup : "parent_item_group"
  ItemGroup ||--o{ Item : classifies
  UOM ||--o{ Item : "stock_uom"
  Item ||--o{ ItemBarcode : "barcodes (child)"
  Item ||--o{ ItemDefault : "item_defaults (child)"
  ItemDefault }o--|| Warehouse : "default_warehouse"
  Item ||--o{ ItemPrice : priced
  PriceList ||--o{ ItemPrice : contains
  CustomerGroup ||--o{ Customer : groups
  Territory ||--o{ Customer : "located in"
  Customer ||--o{ DynamicLink : "linked from"
  Address ||--o{ DynamicLink : "links (child)"
  Contact ||--o{ DynamicLink : "links (child)"
  User ||--o{ HasRole : "roles (child)"
  Role ||--o{ HasRole : grants

  Company {
    string name PK "company_name"
    string abbr UK "suffix of warehouse names"
    string default_currency
    string country
  }
  Warehouse {
    string name PK "warehouse_name - abbr"
    string warehouse_name
    string parent_warehouse FK
    int is_group "1 = site/zone/aisle, 0 = bin"
    string company FK
    int disabled
    string cloud_wms_location_barcode UK "WMS"
  }
  Item {
    string name PK "item_code"
    string item_name
    string item_group FK
    string stock_uom FK
    int is_stock_item
    float standard_rate "creates an Item Price on insert"
    int disabled
  }
  ItemBarcode {
    string parent FK "Item"
    string barcode UK "scanned at pick"
    string barcode_type
    string uom
  }
  ItemDefault {
    string parent FK "Item"
    string company FK
    string default_warehouse FK
  }
  ItemGroup {
    string name PK
    string parent_item_group FK
    int is_group
  }
  UOM {
    string name PK
    int must_be_whole_number
  }
  PriceList {
    string name PK "Standard Selling"
    string currency
    int selling
  }
  ItemPrice {
    string name PK
    string item_code FK
    string price_list FK
    float price_list_rate
    string currency
  }
  Customer {
    string name PK
    string customer_name
    string customer_type "Company or Individual"
    string customer_group FK
    string territory FK
    string customer_primary_address FK
    string customer_primary_contact FK
    int disabled
  }
  CustomerGroup {
    string name PK
    string parent_customer_group FK
  }
  Territory {
    string name PK
    string parent_territory FK
  }
  Address {
    string name PK
    string address_type "Billing or Shipping"
    string address_line1
    string city
    string pincode
    string country
  }
  Contact {
    string name PK
    string first_name
    string email_id
    string phone
  }
  DynamicLink {
    string parent FK "Address or Contact"
    string link_doctype "Customer"
    string link_name FK
  }
  User {
    string name PK "email"
    string username
    string full_name
    int enabled
  }
  Role {
    string name PK "WMS Picker, ..."
  }
  HasRole {
    string parent FK "User"
    string role FK
  }
```

### Locations

Locations follow plan decision 4A: **a bin is a leaf `Warehouse`**. The tree is
`site → zone → aisle → bin`. Only bins have a `cloud_wms_location_barcode`, and
that is the value a picker scans. The demo tree is:

```text
MAIN - <abbr>                (group)
└── MAIN-A                   (group, zone)
    └── MAIN-A-01            (group, aisle)
        ├── MAIN-A-01-01     barcode LOC-MAIN-A-01-01
        ├── MAIN-A-01-02     barcode LOC-MAIN-A-01-02
        └── MAIN-A-01-03     barcode LOC-MAIN-A-01-03
```

Item scans resolve through `Item Barcode.barcode → parent`. Location scans
resolve through `Warehouse.cloud_wms_location_barcode`.

## Order-to-ship transactions

```mermaid
erDiagram
  Customer ||--o{ SalesOrder : places
  SalesOrder ||--|{ SalesOrderItem : "items (child)"
  SalesOrderItem }o--|| Item : orders
  PickList ||--|{ PickListItem : "locations (child)"
  PickListItem }o--|| SalesOrderItem : "sales_order_item"
  PickListItem }o--|| Warehouse : "bin to pick from"
  PickList ||--o{ ToDo : "assigned via"
  ToDo }o--|| User : "allocated_to"
  SalesOrderItem ||--o{ StockReservationEntry : reserves
  StockReservationEntry }o--o| PickList : "from_voucher_no"
  DeliveryNote ||--|{ DeliveryNoteItem : "items (child)"
  DeliveryNoteItem }o--|| SalesOrderItem : "so_detail"
  DeliveryNoteItem }o--|| PickListItem : "pick_list_item"
  DeliveryNote ||--|{ StockLedgerEntry : "posts on submit"
  StockEntry ||--|{ StockEntryDetail : "items (child)"
  StockEntry ||--o{ StockLedgerEntry : "posts on submit"
  StockLedgerEntry }o--|| Bin : "updates"
  Bin }o--|| Item : for
  Bin }o--|| Warehouse : at

  SalesOrder {
    string name PK "SAL-ORD-YYYY-#####"
    string customer FK
    string company FK
    date transaction_date
    date delivery_date
    string set_warehouse FK "default source"
    string po_no
    int docstatus
    string status "To Deliver and Bill, Completed, ..."
    float per_picked
    float per_delivered
    string cloud_wms_source "WMS, indexed"
    string cloud_wms_external_order_id "WMS, indexed"
  }
  SalesOrderItem {
    string name PK
    string parent FK "Sales Order"
    string item_code FK
    float qty
    float rate
    string warehouse FK
    float picked_qty
    float delivered_qty
  }
  PickList {
    string name PK "STO-PICK-YYYY-#####"
    string company FK
    string purpose "Delivery"
    string customer FK
    int scan_mode "1"
    int pick_manually "1"
    int docstatus
    string status "Draft, Open, Partly Delivered, Completed, Cancelled"
  }
  PickListItem {
    string name PK "row id used by the UI"
    string parent FK "Pick List"
    string item_code FK
    string warehouse FK "bin"
    float stock_qty "requested"
    float picked_qty
    float delivered_qty
    string sales_order FK
    string sales_order_item FK
    int cloud_wms_location_confirmed "WMS"
    string cloud_wms_shortage_state "WMS: Pending or Approved"
    string cloud_wms_shortage_reason "WMS"
  }
  ToDo {
    string name PK
    string allocated_to FK "picker"
    string reference_type "Pick List"
    string reference_name FK
    string status "Open, Closed, Cancelled"
  }
  StockReservationEntry {
    string name PK
    string item_code FK
    string warehouse FK
    string voucher_type "Sales Order"
    string voucher_no FK
    string voucher_detail_no FK
    string from_voucher_type "Pick List"
    string from_voucher_no FK
    float reserved_qty
    float delivered_qty
    string status
  }
  DeliveryNote {
    string name PK "MAT-DN-YYYY-#####"
    string customer FK
    string company FK
    date posting_date
    time posting_time
    string lr_no "dispatch reference"
    int docstatus
    string status
  }
  DeliveryNoteItem {
    string name PK
    string parent FK "Delivery Note"
    string item_code FK
    float qty
    string warehouse FK
    string against_sales_order FK
    string so_detail FK
    string against_pick_list FK
    string pick_list_item FK
  }
  StockEntry {
    string name PK
    string stock_entry_type "Material Receipt, ..."
    string company FK
    int docstatus
  }
  StockEntryDetail {
    string parent FK "Stock Entry"
    string item_code FK
    string s_warehouse FK
    string t_warehouse FK
    float qty
    float basic_rate
  }
  StockLedgerEntry {
    string name PK
    string item_code FK
    string warehouse FK
    float actual_qty "signed movement"
    float qty_after_transaction
    string voucher_type
    string voucher_no
    date posting_date
    int is_cancelled
  }
  Bin {
    string name PK
    string item_code FK
    string warehouse FK
    float actual_qty "on hand"
    float reserved_qty "ordered, not delivered"
    float reserved_stock "Stock Reservation Entries"
    float projected_qty
  }
```

### Task status (derived, not stored)

`services/tasks.py` derives the WMS task status from the Pick List:

```mermaid
stateDiagram-v2
  [*] --> available: submitted Sales Order with remaining qty and no active Pick List
  available --> claimed: claim creates a draft Pick List + ToDo
  claimed --> available: release deletes the draft
  claimed --> picking: first location/item scan
  picking --> qa_required: row shortage state is Pending
  qa_required --> picking: supervisor approves; the row is reduced
  picking --> ready_to_dispatch: complete submits the Pick List (docstatus 1)
  ready_to_dispatch --> dispatched: dispatch submits the Delivery Note; status Completed
  dispatched --> [*]
```

Any quantity left on the Sales Order after a short pick makes it `available`
again.

## WMS app doctypes

```mermaid
erDiagram
  User ||--o{ WmsRequest : "user"
  User ||--o{ WmsTaskEvent : "actor"
  WmsRequest |o..o{ WmsTaskEvent : "idempotency_key"
  WmsTaskEvent }o..o| SalesOrder : "sales_order (soft)"
  WmsTaskEvent }o..o| PickList : "pick_list (soft)"
  WmsTaskEvent }o..o| DeliveryNote : "delivery_note (soft)"

  WmsRequest {
    string name PK "hash"
    string idempotency_key UK
    string operation "e.g. tasks.claim"
    string user
    string request_hash "rejects key reuse with a new payload"
    string status "Processing, Succeeded, Failed"
    string error_code
    string reference_doctype
    string reference_name
    text response_json "replayed verbatim"
  }
  WmsTaskEvent {
    string name PK "WTE-#####"
    string event_type "see list below"
    string actor FK
    string correlation_id
    string idempotency_key
    string sales_order
    string pick_list
    string pick_list_item
    string delivery_note
    string item_code
    string warehouse
    string scanned_value
    float qty
    text reason
    text details "JSON"
  }
```

The references on `WMS Task Event` are plain `Data` fields, not `Link`
fields. Audit rows therefore never block ERPNext from cancelling or deleting
documents, and they survive when the referenced document is deleted.

Event types: `Order Received`, `Task Released`, `Task Claimed`,
`Task Assigned`, `Task Released To Queue`, `Location Scanned`, `Item Scanned`,
`Pick Confirmed`, `Short Pick`, `Short Pick Approved`, `Task Completed`,
`Task Cancelled`, `Delivery Created`, `Delivery Submitted`,
`Inventory Corrected`.

## Roles and permissions

| Role | Sales Order | Pick List | Stock Reservation Entry | Delivery Note |
| --- | --- | --- | --- | --- |
| WMS Intake | submit | – | – | – |
| WMS Picker | read | submit, delete | submit | – |
| WMS Dispatch | read | read | – | submit |
| WMS Supervisor | read | cancel, delete | cancel | read |

The source is `apps/cloud_wms/cloud_wms/setup/permissions.py`. Endpoints check
roles first. Where ERPNext needs reads outside this matrix (customer and tax
masters while a Delivery Note is mapped, for example), the service runs that
step as the system user.

---

## Proposed: admin screens

The aim is an **Admin** area in the WMS UI for the data that operators and
warehouse admins maintain today in ERPNext Desk. The table also answers "anything
else?" by listing the screens worth adding beyond customers, orders, products and
locations.

| # | Screen | ERPNext doctypes | Operations | Notes and constraints |
| --- | --- | --- | --- | --- |
| 1 | **Customers** | `Customer`, `Address`, `Contact` (via `Dynamic Link`) | Create, read, update, disable | Deletion fails once a customer is used on any transaction, so disable is the normal "delete". Customer Group and Territory are pick-lists. |
| 2 | **Products** | `Item`, `Item Barcode`, `Item Price` (Standard Selling), `Item Default` | Create, read, update, disable | Barcodes are edited inline, because they are what pickers scan. `stock_uom` and `is_stock_item` cannot change once stock exists. |
| 3 | **Locations** | `Warehouse` (tree) | Create, read, update, disable; move within the tree | Tree editor with a barcode field on bins and label printing for bins. A group with children, or a bin with stock or ledger entries, cannot be deleted. |
| 4 | **Sales Orders** | `Sales Order`, `Sales Order Item` | Create (existing intake), read, cancel, amend; close or hold | Submitted orders are immutable. "Edit" means cancel and amend, or ERPNext's "Update Items" for quantity and rate. Cancelling is blocked while a Pick List or Delivery Note is active, so those are cancelled first. |
| 5 | **Stock & adjustments** | `Bin` (read), `Stock Reconciliation`, `Stock Entry` (Material Receipt, Material Transfer) | Read on-hand by item × bin; post receipts, transfers and count corrections | This is the only way to change quantities, and it is never a direct edit of `Bin`. Each posting records an `Inventory Corrected` event. |
| 6 | **Users & roles** | `User`, `Has Role` | Create, read, enable/disable, assign WMS roles | Lets a Supervisor or Admin assign WMS roles without Desk. Needs System Manager-level rights, so the endpoint should allow only the four WMS roles. |
| 7 | **Pick Lists & Delivery Notes** | `Pick List`, `Delivery Note` | Read; cancel (Supervisor) | Exception handling for wrong dispatches. Cancelling a Delivery Note reverses its stock ledger entries and the delivered quantities on the Sales Order and the Pick List. |
| 8 | **Audit log** | `WMS Task Event`, `WMS Request` | Read-only, with filters (order, task, user, date) | Events are immutable, so the screen has no edit or delete. |
| 9 | **Reference lists** | `Customer Group`, `Territory`, `Item Group`, `UOM`, `Price List` | Read, plus create for groups | Low priority. Seeded defaults are usually enough. |
| 10 | **Settings** | `Stock Settings` (reservation flags), `Company` (read) | Read; toggle stock reservation | Mostly Desk-only. Shown here as read-only so admins can see why picking behaves as it does. |

Out of scope for now: suppliers and inbound flows (`Supplier`,
`Purchase Order`, `Purchase Receipt`), invoicing and accounting.

### Model changes the admin screens would need

The admin screens need **no new business doctypes**. They need these:

1. **Role `WMS Admin`.** It gets create, write and delete on `Customer`,
   `Address`, `Contact`, `Item`, `Item Price` and `Warehouse`; submit and
   cancel on `Stock Entry` and `Stock Reconciliation`; and read on everything
   above. Without it, the Supervisor role would become the admin role.
2. **`Warehouse.cloud_wms_location_type`** (Select: `Site`, `Zone`, `Aisle`,
   `Bin`). Optional. Today the level is implied by depth and `is_group`. An
   explicit type lets the tree editor enforce "a bin has a barcode; a group
   has none".
3. **`Item.cloud_wms_pick_note`** (Small Text). Optional handling text shown
   on the pick screen, such as "fragile" or "two-person lift".
4. **A `cloud_wms.api.admin` module.** It would hold one whitelisted endpoint
   set per entity (`list`, `get`, `save`, `disable`, plus `post` for stock
   adjustments) using the existing `@wms_endpoint` decorator, so every write
   is role-checked, idempotent and audited. A generic "save any doctype"
   endpoint is deliberately excluded.

### Open decisions

- Should Supervisors administer master data, or only a separate `WMS Admin`?
- Should the admin area allow Sales Order edits through cancel and amend, or
  stay read-only with intake as the only write?
- Should Users & roles be in the WMS UI, given that it needs elevated
  rights, or stay in Desk?
- Should location labels be printed from the browser (HTML print) or through
  an ERPNext print format?
