import type { PickLine, TaskStatus, WmsTask } from '../types'

const storageKey = 'cloud-wms-prototype-tasks'

export function loadTasks(): WmsTask[] {
  try {
    return JSON.parse(localStorage.getItem(storageKey) ?? '[]') as WmsTask[]
  } catch {
    return []
  }
}

export function persistTasks(tasks: WmsTask[]) {
  localStorage.setItem(storageKey, JSON.stringify(tasks))
}

export function taskFromSalesOrder(
  salesOrder: string,
  customer: string,
  itemCode: string,
  itemName: string,
  quantity: number,
): WmsTask {
  const line: PickLine = {
    itemCode,
    itemName,
    location: 'MAIN-A-01-02',
    requestedQty: quantity,
    pickedQty: 0,
  }
  return {
    id: `WMS-${salesOrder}`,
    salesOrder,
    customer,
    createdAt: new Date().toISOString(),
    status: 'available',
    lines: [line],
  }
}

export const statusLabel: Record<TaskStatus, string> = {
  available: 'Available',
  claimed: 'Claimed',
  picking: 'Picking',
  qa_required: 'QA review',
  ready_to_dispatch: 'Ready to ship',
  dispatched: 'Dispatched',
}
