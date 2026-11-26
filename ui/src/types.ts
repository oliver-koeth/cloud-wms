export type AdminScreen =
  | 'admin-orders'
  | 'admin-customers'
  | 'admin-products'
  | 'admin-locations'
  | 'admin-stock'
  | 'admin-documents'
  | 'admin-audit'
  | 'admin-reference'
  | 'admin-settings'

export type Screen = 'operations' | 'create-order' | 'pick' | 'qa' | 'dispatch' | AdminScreen

export type TaskStatus = 'available' | 'claimed' | 'picking' | 'qa_required' | 'ready_to_dispatch' | 'dispatched'

export interface TaskLine {
  row: string
  item_code: string
  item_name: string | null
  location: string
  location_barcode: string | null
  uom: string | null
  requested_qty: number
  picked_qty: number
  location_confirmed: boolean
  shortage_state: 'Pending' | 'Approved' | null
  shortage_reason: string | null
}

export interface PickTask {
  pick_list: string
  sales_order: string | null
  customer: string | null
  status: TaskStatus
  docstatus: number
  assignees: string[]
  mine: boolean
  lines: TaskLine[]
}

export interface ClaimableOrder {
  sales_order: string
  customer: string
  delivery_date: string | null
  warehouse: string | null
  status: 'available'
  remaining_qty: number
  lines: number
}

export interface TaskListing {
  claimable: ClaimableOrder[]
  active: PickTask[]
}

export interface SessionUser {
  fullName: string
  email: string
  roles?: string[]
}

export interface FormOptions {
  customers: Array<{ name: string; customer_name?: string }>
  items: Array<{ name: string; item_name?: string; standard_rate?: number }>
  warehouses: Array<{ name: string; warehouse_name?: string }>
  company?: string
}

export interface OrderLineInput {
  itemCode: string
  quantity: number
  rate?: number
}

export interface IngestOrderInput {
  source: string
  externalOrderId?: string
  customer: string
  company: string
  deliveryDate: string
  warehouse?: string
  lines: OrderLineInput[]
}

export interface IngestedOrder {
  sales_order: string
  customer: string
  docstatus: number
  status: string
  pick_list: string | null
  duplicate: boolean
}

export interface DispatchReceipt {
  pick_list: string
  sales_order: string | null
  pick_list_status: string
  already_dispatched: boolean
  delivery_note: {
    name: string
    docstatus: number
    status: string
    posting_date: string
    posting_time: string
    reference: string | null
    units: number
  }
}

export interface AdminOptions {
  companies: string[]
  default_company: string | null
  customer_groups: string[]
  territories: string[]
  item_groups: string[]
  uoms: string[]
  countries: string[]
  selling_price_list: string | null
}

export interface AddressInput {
  address_line1: string | null
  address_line2: string | null
  city: string | null
  pincode: string | null
  country: string | null
}

export interface CustomerSummary {
  name: string
  customer_name: string
  customer_type: string
  customer_group: string | null
  territory: string | null
  disabled: number
  email_id: string | null
}

export interface CustomerDetail extends CustomerSummary {
  mobile_no: string | null
  customer_primary_address: string | null
  customer_primary_contact: string | null
  address: AddressInput
  open_orders: number
  modified: string
}

export interface CustomerInput {
  name?: string
  customer_name: string
  customer_type?: string
  customer_group?: string
  territory?: string
  disabled: number
  email_id?: string
  mobile_no?: string
  address?: AddressInput
  modified?: string
}

export interface ItemSummary {
  name: string
  item_name: string
  item_group: string
  stock_uom: string
  is_stock_item: number
  disabled: number
  barcodes: string[]
  on_hand: number
}

export interface ItemDetail extends Omit<ItemSummary, 'on_hand'> {
  description: string | null
  selling_price_list: string | null
  selling_rate: number | null
  stock: Array<{ warehouse: string; actual_qty: number; reserved_stock: number }>
  modified: string
}

export interface ItemInput {
  name?: string
  item_code?: string
  item_name: string
  item_group?: string
  stock_uom?: string
  is_stock_item?: number
  description?: string
  disabled: number
  barcodes: string[]
  selling_rate?: number | null
  modified?: string
}

export interface LocationRow {
  name: string
  warehouse_name: string
  parent_warehouse: string | null
  is_group: number
  disabled: number
  company: string
  barcode: string | null
  depth: number
  lft: number
  rgt: number
  on_hand: number
  modified: string
}

export interface LocationInput {
  name?: string
  warehouse_name: string
  parent_warehouse?: string | null
  is_group: number
  barcode?: string | null
  disabled: number
  company?: string
  modified?: string
}

export interface OrderSummary {
  name: string
  customer: string
  customer_name: string | null
  company: string
  transaction_date: string
  delivery_date: string | null
  status: string
  docstatus: number
  grand_total: number
  currency: string
  per_picked: number
  per_delivered: number
  amended_from: string | null
  cloud_wms_source: string | null
  cloud_wms_external_order_id: string | null
}

export interface OrderDetail extends OrderSummary {
  set_warehouse: string | null
  modified: string
  items: Array<{
    name: string
    item_code: string
    item_name: string | null
    qty: number
    uom: string | null
    rate: number
    amount: number
    picked_qty: number
    delivered_qty: number
  }>
  pick_lists: Array<{ name: string; docstatus: number; status: string }>
  delivery_notes: Array<{ name: string; docstatus: number; status: string }>
  amended_to: string | null
  cancel_blocker: { message: string; next_action: string | null } | null
}

export interface AmendOrderInput {
  sales_order: string
  customer?: string
  delivery_date: string
  lines: Array<{ item_code: string; qty: number; rate?: number }>
  modified?: string
}

export interface StockLevel {
  item_code: string
  item_name: string | null
  warehouse: string
  barcode: string | null
  actual_qty: number
  reserved_stock: number
  projected_qty: number
  stock_uom: string | null
  valuation_rate: number
}

export type StockPurpose = 'receipt' | 'transfer' | 'count'

export interface StockPosting {
  doctype: 'Stock Entry' | 'Stock Reconciliation'
  name: string
  purpose: string
  posting_date: string
  posting_time: string
  docstatus: number
  owner: string
  remarks: string | null
  modified: string
  item_code: string
  qty: number
  from_warehouse: string | null
  to_warehouse: string | null
}

export interface StockPostingInput {
  purpose: StockPurpose
  item_code: string
  qty: number
  to_warehouse: string
  from_warehouse?: string
  rate?: number
  reason?: string
}

export interface Blocker {
  message: string
  next_action: string | null
}

export interface DocumentRef {
  name: string
  docstatus: number
  status: string
}

export interface PickListSummary {
  name: string
  status: string
  docstatus: number
  customer: string | null
  company: string
  owner: string
  creation: string
  modified: string
  sales_orders: string[]
}

export interface PickListDetail extends PickListSummary {
  assignees: string[]
  lines: Array<{
    row: number
    item_code: string
    item_name: string | null
    warehouse: string
    qty: number
    picked_qty: number
    uom: string | null
    sales_order: string | null
    shortage_state: string | null
  }>
  delivery_notes: DocumentRef[]
  cancel_blocker: Blocker | null
}

export interface DeliveryNoteSummary {
  name: string
  status: string
  docstatus: number
  customer: string
  customer_name: string | null
  company: string
  posting_date: string
  total_qty: number
  is_return: number
  owner: string
  creation: string
  modified: string
  sales_orders: string[]
  pick_lists: string[]
}

export interface DeliveryNoteDetail extends DeliveryNoteSummary {
  lines: Array<{
    row: number
    item_code: string
    item_name: string | null
    warehouse: string
    qty: number
    uom: string | null
    sales_order: string | null
    pick_list: string | null
  }>
  reference: string | null
  cancel_blocker: Blocker | null
}

export interface TaskEvent {
  name: string
  creation: string
  event_type: string
  actor: string
  correlation_id: string | null
  idempotency_key: string | null
  sales_order: string | null
  pick_list: string | null
  pick_list_item: string | null
  delivery_note: string | null
  item_code: string | null
  warehouse: string | null
  scanned_value: string | null
  qty: number | null
  reason: string | null
  details: string | null
}

export interface EventFilters {
  event_type?: string
  actor?: string
  sales_order?: string
  pick_list?: string
  delivery_note?: string
  correlation_id?: string
  from_date?: string
  to_date?: string
}

export interface EventLog {
  events: TaskEvent[]
  event_types: string[]
  limit: number
}

export type TreeReference = 'Customer Group' | 'Territory' | 'Item Group'
export type ReferenceDoctype = TreeReference | 'UOM' | 'Price List'

export interface ReferenceList {
  doctype: ReferenceDoctype
  tree: boolean
  rows: Array<Record<string, string | number | null> & { name: string }>
}

export interface WmsSettings {
  stock: Record<string, string | number | null>
  selling: Record<string, string | number | null>
  enforced: Record<string, number>
  companies: Array<{ name: string; abbr: string; default_currency: string | null; country: string | null }>
  default_company: string | null
  versions: Record<string, string | null>
}
