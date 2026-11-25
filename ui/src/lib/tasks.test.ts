import { describe, expect, it } from 'vitest'
import { statusLabel, taskFromSalesOrder } from './tasks'

describe('taskFromSalesOrder', () => {
  it('creates an unclaimed local workflow task without changing the ERPNext order reference', () => {
    const task = taskFromSalesOrder('SAL-ORD-2026-00001', 'WMS Demo Customer', 'WMS-DEMO-TOTE', 'WMS Demo Tote', 2)

    expect(task).toMatchObject({
      id: 'WMS-SAL-ORD-2026-00001',
      salesOrder: 'SAL-ORD-2026-00001',
      customer: 'WMS Demo Customer',
      status: 'available',
      lines: [{ itemCode: 'WMS-DEMO-TOTE', requestedQty: 2, pickedQty: 0, location: 'MAIN-A-01-02' }],
    })
    expect(statusLabel.qa_required).toBe('QA review')
  })
})
