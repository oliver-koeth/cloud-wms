import { afterEach, describe, expect, it, vi } from 'vitest'
import { ingestOrder } from './erpnext'

const input = {
  source: 'manual',
  externalOrderId: 'PO-1',
  customer: 'Acme',
  company: 'Demo Co',
  deliveryDate: '2026-12-01',
  lines: [{ itemCode: 'TOTE', quantity: 2, rate: 25 }],
}

function stubFetch(status: number, body: unknown) {
  const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify(body), { status }))
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
