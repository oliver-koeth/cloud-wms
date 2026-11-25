export type Screen = 'operations' | 'create-order' | 'pick' | 'qa' | 'dispatch'

export type TaskStatus = 'available' | 'claimed' | 'picking' | 'qa_required' | 'ready_to_dispatch' | 'dispatched'

export interface PickLine {
  itemCode: string
  itemName: string
  location: string
  requestedQty: number
  pickedQty: number
  shortageReason?: string
}

export interface WmsTask {
  id: string
  salesOrder: string
  customer: string
  createdAt: string
  status: TaskStatus
  claimedBy?: string
  lines: PickLine[]
  qaApproved?: boolean
}

export interface SessionUser {
  fullName: string
  email: string
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
