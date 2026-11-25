export type Screen = 'operations' | 'create-order' | 'pick' | 'qa' | 'dispatch'

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
