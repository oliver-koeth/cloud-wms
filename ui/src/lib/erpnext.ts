import type { FormOptions, IngestOrderInput, IngestedOrder, SessionUser } from '../types'

interface FrappeErrorResponse {
  error?: { code?: string; message?: string; next_action?: string | null; correlation_id?: string }
  message?: string
  exception?: string
  exc?: string
  _server_messages?: string
}

const resourcePath = (doctype: string) => `/api/resource/${encodeURIComponent(doctype)}`

function errorMessage(payload: FrappeErrorResponse, fallback: string) {
  if (payload.error?.message) {
    const { message, next_action: nextAction, correlation_id: correlationId } = payload.error
    return [message, nextAction, correlationId ? `(ref ${correlationId})` : ''].filter(Boolean).join(' ')
  }
  if (payload.message && typeof payload.message === 'string') return payload.message
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
  const result = await request<{ data: IngestedOrder }>('/api/method/cloud_wms.api.orders.ingest', {
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
  return result.data
}
