import type { TaskStatus } from '../types'

export const statusLabel: Record<TaskStatus, string> = {
  available: 'Available',
  claimed: 'Claimed',
  picking: 'Picking',
  qa_required: 'QA review',
  ready_to_dispatch: 'Ready to ship',
  dispatched: 'Dispatched',
}
