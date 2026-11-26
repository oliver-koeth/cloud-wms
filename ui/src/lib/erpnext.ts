import type {
  AdminOptions,
  AmendOrderInput,
  CustomerDetail,
  CustomerInput,
  CustomerSummary,
  DeliveryNoteDetail,
  DeliveryNoteSummary,
  DispatchReceipt,
  EventFilters,
  EventLog,
  FormOptions,
  IngestOrderInput,
  IngestedOrder,
  ItemDetail,
  ItemInput,
  ItemSummary,
  LocationInput,
  LocationRow,
  OrderDetail,
  OrderSummary,
  PickListDetail,
  PickListSummary,
  PickTask,
  ReferenceDoctype,
  ReferenceList,
  SessionUser,
  StockLevel,
  StockPosting,
  StockPostingInput,
  TaskListing,
  TreeReference,
  WmsSettings,
} from '../types'

interface WmsError {
  code?: string
  message?: string
  next_action?: string | null
  correlation_id?: string
}

interface FrappeErrorResponse {
  error?: WmsError
  message?: string | { error?: WmsError }
  exception?: string
  exc?: string
  _server_messages?: string
}

const resourcePath = (doctype: string) => `/api/resource/${encodeURIComponent(doctype)}`

function errorMessage(payload: FrappeErrorResponse, fallback: string) {
  const wmsError = payload.error ?? (typeof payload.message === 'object' ? payload.message?.error : undefined)
  if (wmsError?.message) {
    const { message, next_action: nextAction, correlation_id: correlationId } = wmsError
    return [message, nextAction, correlationId ? `(ref ${correlationId})` : ''].filter(Boolean).join(' ')
  }
  if (typeof payload.message === 'string' && payload.message) return payload.message
  if (payload.exception) return payload.exception
  if (payload.exc) return payload.exc
  if (payload._server_messages) {
    try {
      const messages = JSON.parse(payload._server_messages) as string[]
      return messages
        .map((entry) => {
          try {
            return JSON.parse(entry).message as string
          } catch {
            return entry
          }
        })
        .join(' ')
    } catch {
      return payload._server_messages
    }
  }
  return fallback
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(path, {
    credentials: 'include',
    headers: { Accept: 'application/json', ...(init.headers ?? {}) },
    ...init,
  })
  const payload = (await response.json().catch(() => ({}))) as T & FrappeErrorResponse
  if (!response.ok) throw new Error(errorMessage(payload, `ERPNext request failed (${response.status})`))
  return payload
}

export async function login(usr: string, pwd: string): Promise<SessionUser> {
  const result = await request<{ full_name?: string; message?: string }>('/api/method/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: new URLSearchParams({ usr, pwd }),
  })
  return { fullName: result.full_name || usr, email: usr }
}

export async function logout() {
  await request('/api/method/logout', { method: 'POST' })
}

async function list<T>(doctype: string, fields: string[], filters?: unknown[][]): Promise<T[]> {
  const params = new URLSearchParams({
    fields: JSON.stringify(fields),
    limit_page_length: '100',
    order_by: 'modified desc',
  })
  if (filters) params.set('filters', JSON.stringify(filters))
  const response = await request<{ data: T[] }>(`${resourcePath(doctype)}?${params.toString()}`)
  return response.data
}

export async function getFormOptions(): Promise<FormOptions> {
  const [customers, items, warehouses, companies] = await Promise.all([
    list<FormOptions['customers'][number]>('Customer', ['name', 'customer_name']),
    list<FormOptions['items'][number]>('Item', ['name', 'item_name', 'standard_rate'], [['disabled', '=', 0]]),
    list<FormOptions['warehouses'][number]>('Warehouse', ['name', 'warehouse_name'], [['is_group', '=', 0]]),
    list<{ name: string }>('Company', ['name']),
  ])
  return { customers, items, warehouses, company: companies[0]?.name }
}

export async function ingestOrder(input: IngestOrderInput, idempotencyKey: string): Promise<IngestedOrder> {
  const result = await request<{ message: { data: IngestedOrder } }>('/api/method/cloud_wms.api.orders.ingest', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      idempotency_key: idempotencyKey,
      source: input.source,
      external_order_id: input.externalOrderId || undefined,
      customer: input.customer,
      company: input.company,
      delivery_date: input.deliveryDate,
      set_warehouse: input.warehouse || undefined,
      lines: input.lines.map((line) => ({ item_code: line.itemCode, qty: line.quantity, rate: line.rate })),
    }),
  })
  return result.message.data
}

const taskMethod = (name: string) => `/api/method/cloud_wms.api.tasks.${name}`

async function readTasks<T>(name: string, params: Record<string, string> = {}): Promise<T> {
  const query = new URLSearchParams(params).toString()
  const result = await request<{ message: { data: T } }>(`${taskMethod(name)}${query ? `?${query}` : ''}`)
  return result.message.data
}

async function actOnTask<T = PickTask>(name: string, body: Record<string, unknown>): Promise<T> {
  const result = await request<{ message: { data: T } }>(taskMethod(name), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ idempotency_key: crypto.randomUUID(), ...body }),
  })
  return result.message.data
}

export async function getRoles(): Promise<string[]> {
  const result = await request<{ message: { data: { roles: string[] } } }>('/api/method/cloud_wms.api.session.context')
  return result.message.data.roles
}

export const listTasks = () => readTasks<TaskListing>('list_tasks')

export const claimTask = (salesOrder: string) => actOnTask('claim', { sales_order: salesOrder })

export async function dispatchTask(pickList: string, reference?: string): Promise<DispatchReceipt> {
  const result = await request<{ message: { data: DispatchReceipt } }>('/api/method/cloud_wms.api.dispatch.confirm', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ idempotency_key: crypto.randomUUID(), pick_list: pickList, reference: reference || undefined }),
  })
  return result.message.data
}

export const releaseTask = (pickList: string) => actOnTask<{ released: boolean }>('release', { pick_list: pickList })

export const confirmLocation = (pickList: string, row: string, barcode: string) =>
  actOnTask('confirm_location', { pick_list: pickList, row, barcode })

export const confirmPick = (pickList: string, row: string, itemBarcode: string, qty = 1) =>
  actOnTask('confirm_pick', { pick_list: pickList, row, item_barcode: itemBarcode, qty })

export const recordShortage = (pickList: string, row: string, reason: string) =>
  actOnTask('record_shortage', { pick_list: pickList, row, reason })

export const approveShortage = (pickList: string, row: string) =>
  actOnTask<PickTask | { status: 'cancelled' }>('approve_shortage', { pick_list: pickList, row })

export const completeTask = (pickList: string) => actOnTask('complete', { pick_list: pickList })

const adminMethod = (name: string) => `/api/method/cloud_wms.api.admin.${name}`

async function adminRead<T>(name: string, params: Record<string, string | number | undefined> = {}): Promise<T> {
  const query = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) if (value !== undefined && value !== '') query.set(key, String(value))
  const suffix = query.toString()
  const result = await request<{ message: { data: T } }>(`${adminMethod(name)}${suffix ? `?${suffix}` : ''}`)
  return result.message.data
}

async function adminWrite<T>(name: string, body: object): Promise<T> {
  const result = await request<{ message: { data: T } }>(adminMethod(name), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ idempotency_key: crypto.randomUUID(), ...body }),
  })
  return result.message.data
}

export const getAdminOptions = () => adminRead<AdminOptions>('options')

export const listCustomers = (search?: string, includeDisabled = false) =>
  adminRead<CustomerSummary[]>('list_customers', { search, include_disabled: Number(includeDisabled) })
export const getCustomer = (name: string) => adminRead<CustomerDetail>('get_customer', { name })
export const saveCustomer = (input: CustomerInput) => adminWrite<CustomerDetail>('save_customer', input)

export const listItems = (search?: string, includeDisabled = false) =>
  adminRead<ItemSummary[]>('list_items', { search, include_disabled: Number(includeDisabled) })
export const getItem = (name: string) => adminRead<ItemDetail>('get_item', { name })
export const saveItem = (input: ItemInput) => adminWrite<ItemDetail>('save_item', input)

export const listLocations = () => adminRead<LocationRow[]>('list_locations')
export const saveLocation = (input: LocationInput) => adminWrite<LocationRow>('save_location', input)

export const deleteRecord = (doctype: 'Customer' | 'Item' | 'Warehouse', name: string) =>
  adminWrite<{ deleted: boolean }>('delete_record', { doctype, name })

export const listOrders = (search?: string, status?: string) => adminRead<OrderSummary[]>('list_orders', { search, status })
export const getOrder = (name: string) => adminRead<OrderDetail>('get_order', { name })
export const cancelOrder = (salesOrder: string, modified?: string) =>
  adminWrite<OrderDetail>('cancel_order', { sales_order: salesOrder, modified })
export const amendOrder = (input: AmendOrderInput) => adminWrite<OrderDetail>('amend_order', input)

export const listStock = (search?: string, warehouse?: string) => adminRead<StockLevel[]>('list_stock', { search, warehouse })
export const listPostings = (search?: string) => adminRead<StockPosting[]>('list_postings', { search })
export const postStock = (input: StockPostingInput) => adminWrite<StockPosting>('post_stock', input)
export const cancelPosting = (posting: Pick<StockPosting, 'doctype' | 'name' | 'modified'>, reason?: string) =>
  adminWrite<StockPosting>('cancel_posting', { doctype: posting.doctype, name: posting.name, modified: posting.modified, reason })

export const listPickLists = (search?: string, status?: string) => adminRead<PickListSummary[]>('list_pick_lists', { search, status })
export const getPickList = (name: string) => adminRead<PickListDetail>('get_pick_list', { name })
export const cancelPickList = (pickList: string, modified?: string, reason?: string) =>
  adminWrite<PickListDetail>('cancel_pick_list', { pick_list: pickList, modified, reason })
export const listDeliveryNotes = (search?: string, status?: string) =>
  adminRead<DeliveryNoteSummary[]>('list_delivery_notes', { search, status })
export const getDeliveryNote = (name: string) => adminRead<DeliveryNoteDetail>('get_delivery_note', { name })
export const cancelDeliveryNote = (deliveryNote: string, modified?: string, reason?: string) =>
  adminWrite<DeliveryNoteDetail>('cancel_delivery_note', { delivery_note: deliveryNote, modified, reason })

export const listEvents = (filters: EventFilters = {}) => adminRead<EventLog>('list_events', { ...filters })
export const listReference = (doctype: ReferenceDoctype) => adminRead<ReferenceList>('list_reference', { doctype })
export const createReference = (input: { doctype: TreeReference; name: string; parent?: string; is_group: number }) =>
  adminWrite<{ name: string; parent: string; is_group: number }>('create_reference', input)
export const getSettings = () => adminRead<WmsSettings>('settings')
