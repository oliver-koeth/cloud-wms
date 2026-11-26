export type AdminScreen = 'admin-orders' | 'admin-customers' | 'admin-products' | 'admin-locations'

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
