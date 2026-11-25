import type { FormOptions, SessionUser } from '../types'

interface FrappeErrorResponse {
  message?: string
  exception?: string
  exc?: string
  _server_messages?: string
}

const resourcePath = (doctype: string) => `/api/resource/${encodeURIComponent(doctype)}`

function errorMessage(payload: FrappeErrorResponse, fallback: string) {
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

export interface SalesOrderInput {
  customer: string
  company: string
  deliveryDate: string
  itemCode: string
  quantity: number
  rate: number
  warehouse?: string
}

export async function createSalesOrder(input: SalesOrderInput): Promise<string> {
  const document = {
    doctype: 'Sales Order',
    customer: input.customer,
    company: input.company,
    delivery_date: input.deliveryDate,
    items: [
      {
        item_code: input.itemCode,
        qty: input.quantity,
        rate: input.rate,
        delivery_date: input.deliveryDate,
        warehouse: input.warehouse || undefined,
      },
    ],
  }
  const result = await request<{ data: { name: string } }>(resourcePath('Sales Order'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(document),
  })
  return result.data.name
}

async function createDocument<T>(doctype: string, document: Record<string, unknown>): Promise<T> {
  const result = await request<{ data: T }>(resourcePath(doctype), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ doctype, ...document }),
  })
  return result.data
}

/**
 * Seeds only the empty local evaluation site. This is intentionally an explicit
 * operator action, not a hidden side effect of loading the order form.
 */
export async function prepareDemoMasterData(company: string) {
  const customer = 'WMS Demo Customer'
  const item = 'WMS-DEMO-TOTE'
  const [existingCustomers, existingItems] = await Promise.all([
    list<{ name: string }>('Customer', ['name'], [['name', '=', customer]]),
    list<{ name: string }>('Item', ['name'], [['name', '=', item]]),
  ])

  if (!existingCustomers.length) {
    const [customerGroups, territories] = await Promise.all([
      list<{ name: string }>('Customer Group', ['name'], [['is_group', '=', 0]]),
      list<{ name: string }>('Territory', ['name'], [['is_group', '=', 0]]),
    ])
    if (!customerGroups[0]?.name || !territories[0]?.name) {
      throw new Error('ERPNext needs at least one leaf Customer Group and Territory before a demo Customer can be created.')
    }
    await createDocument('Customer', {
      customer_name: customer,
      customer_type: 'Company',
      customer_group: customerGroups[0].name,
      territory: territories[0].name,
    })
  }
  if (!existingItems.length) {
    await createDocument('Item', {
      item_code: item,
      item_name: 'WMS Demo Tote',
      item_group: 'All Item Groups',
      stock_uom: 'Nos',
      is_stock_item: 1,
      standard_rate: 25,
      default_company: company,
    })
  }
  return { customer, item }
}
