import { afterEach, describe, expect, it, vi } from 'vitest'
import { claimTask, dispatchTask, ingestOrder, listTasks } from './erpnext'

const input = {
  source: 'manual',
  externalOrderId: 'PO-1',
  customer: 'Acme',
  company: 'Demo Co',
  deliveryDate: '2026-12-01',
  lines: [{ itemCode: 'TOTE', quantity: 2, rate: 25 }],
}

function stubFetch(status: number, body: unknown) {
  const fetchMock = vi.fn().mockImplementation(async () => new Response(JSON.stringify(body), { status }))
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

afterEach(() => vi.unstubAllGlobals())

describe('ingestOrder', () => {
  it('posts the order with the idempotency key and returns the unwrapped result', async () => {
    const order = { sales_order: 'SAL-ORD-1', customer: 'Acme', docstatus: 1, status: 'To Deliver and Bill', pick_list: null, duplicate: false }
    const fetchMock = stubFetch(200, { message: { data: order, replayed: false, correlation_id: 'c1' } })

    await expect(ingestOrder(input, 'key-12345678')).resolves.toEqual(order)

    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toBe('/api/method/cloud_wms.api.orders.ingest')
    expect(JSON.parse(init.body)).toMatchObject({
      idempotency_key: 'key-12345678',
      source: 'manual',
      external_order_id: 'PO-1',
      lines: [{ item_code: 'TOTE', qty: 2, rate: 25 }],
    })
  })

  it('surfaces the structured WMS error message and correlation id', async () => {
    stubFetch(422, { message: { error: { code: 'VALIDATION_FAILED', message: 'Item not found.', next_action: null, correlation_id: 'abc123' } } })

    await expect(ingestOrder(input, 'key-12345678')).rejects.toThrow('Item not found. (ref abc123)')
  })
})

describe('pick task calls', () => {
  it('lists tasks through the GET endpoint and unwraps the data', async () => {
    const listing = { claimable: [], active: [] }
    const fetchMock = stubFetch(200, { message: { data: listing, replayed: false, correlation_id: 'c1' } })

    await expect(listTasks()).resolves.toEqual(listing)
    expect(fetchMock.mock.calls[0][0]).toBe('/api/method/cloud_wms.api.tasks.list_tasks')
  })

  it('sends a fresh idempotency key with each mutation', async () => {
    const fetchMock = stubFetch(200, { message: { data: { pick_list: 'STO-PICK-1' } } })

    await claimTask('SAL-ORD-1')
    await claimTask('SAL-ORD-1')

    const keys = fetchMock.mock.calls.map(([, init]) => JSON.parse(init.body).idempotency_key)
    expect(keys[0]).not.toBe(keys[1])
    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toMatchObject({ sales_order: 'SAL-ORD-1' })
  })

  it('surfaces a conflict from a competing claim', async () => {
    stubFetch(409, { message: { error: { code: 'CONFLICT', message: 'Already claimed by Worker.', next_action: 'Refresh the task list.', correlation_id: 'z9' } } })

    await expect(claimTask('SAL-ORD-1')).rejects.toThrow('Already claimed by Worker. Refresh the task list. (ref z9)')
  })
})

describe('dispatchTask', () => {
  it('posts the pick list and reference and returns the Delivery Note receipt', async () => {
    const receipt = { pick_list: 'STO-PICK-1', delivery_note: { name: 'MAT-DN-1', docstatus: 1, units: 3 } }
    const fetchMock = stubFetch(200, { message: { data: receipt, replayed: false, correlation_id: 'c1' } })

    await expect(dispatchTask('STO-PICK-1', 'PKG-42')).resolves.toEqual(receipt)

    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toBe('/api/method/cloud_wms.api.dispatch.confirm')
    expect(JSON.parse(init.body)).toMatchObject({ pick_list: 'STO-PICK-1', reference: 'PKG-42' })
  })

  it('surfaces a not-ready conflict', async () => {
    stubFetch(409, { message: { error: { code: 'NOT_READY', message: 'Pick List is not submitted.', next_action: null, correlation_id: 'd1' } } })

    await expect(dispatchTask('STO-PICK-1')).rejects.toThrow('Pick List is not submitted. (ref d1)')
  })
})
