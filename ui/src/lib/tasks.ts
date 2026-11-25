import type { TaskStatus, WmsTask } from '../types'

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

export const statusLabel: Record<TaskStatus, string> = {
  available: 'Available',
  claimed: 'Claimed',
  picking: 'Picking',
  qa_required: 'QA review',
  ready_to_dispatch: 'Ready to ship',
  dispatched: 'Dispatched',
}
