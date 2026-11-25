<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { Button, FrappeUIProvider } from 'frappe-ui'
import CameraScanner from './components/CameraScanner.vue'
import LoginPanel from './components/LoginPanel.vue'
import OrderForm from './components/OrderForm.vue'
import {
  approveShortage,
  claimTask,
  completeTask,
  confirmLocation,
  confirmPick,
  getRoles,
  listTasks,
  logout,
  recordShortage,
  releaseTask,
} from './lib/erpnext'
import { statusLabel } from './lib/status'
import type { IngestedOrder, PickTask, Screen, SessionUser, TaskLine, TaskListing, TaskStatus } from './types'

type ScanTarget = { kind: 'location' | 'item'; row: string }

const user = ref<SessionUser | null>(null)
const activeScreen = ref<Screen>('operations')
const listing = ref<TaskListing>({ claimable: [], active: [] })
const selectedPickList = ref<string>()
const scanTarget = ref<ScanTarget | null>(null)
const quantities = ref<Record<string, number>>({})
const reasons = ref<Record<string, string>>({})
const busy = ref(false)
const message = ref('')
const messageIsError = ref(false)
const submittedOrder = ref<IngestedOrder>()

const canSeeTasks = computed(() =>
  !!user.value?.roles?.some((role) => ['WMS Picker', 'WMS Supervisor', 'WMS Dispatch', 'System Manager'].includes(role)),
)
const isSupervisor = computed(() => !!user.value?.roles?.some((role) => ['WMS Supervisor', 'System Manager'].includes(role)))
const activeTasks = computed(() => listing.value.active.filter((task) => task.status !== 'dispatched'))
const selectedTask = computed(() => listing.value.active.find((task) => task.pick_list === selectedPickList.value))
const qaTasks = computed(() => listing.value.active.filter((task) => task.status === 'qa_required'))
const dispatchTasks = computed(() => listing.value.active.filter((task) => task.status === 'ready_to_dispatch'))
const inProgress = computed(() => listing.value.active.filter((task) => ['claimed', 'picking'].includes(task.status)))
const canCompleteSelected = computed(() => {
  const task = selectedTask.value
  return !!task && task.lines.length > 0 && task.lines.every((line) => line.picked_qty >= line.requested_qty && line.shortage_state !== 'Pending')
})

function notify(text: string, isError = false) {
  message.value = text
  messageIsError.value = isError
}

async function refresh() {
  if (!canSeeTasks.value) {
    listing.value = { claimable: [], active: [] }
    return
  }
  try {
    listing.value = await listTasks()
  } catch (error) {
    notify(error instanceof Error ? error.message : 'Could not load tasks.', true)
  }
}

async function run<T>(action: () => Promise<T>, success?: string): Promise<T | undefined> {
  busy.value = true
  try {
    const result = await action()
    notify(success ?? '')
    await refresh()
    return result
  } catch (error) {
    notify(error instanceof Error ? error.message : 'The request failed.', true)
    await refresh()
  } finally {
    busy.value = false
  }
}

function setScreen(screen: Screen) {
  activeScreen.value = screen
  notify('')
  if (screen !== 'create-order') void refresh()
}

function openTask(task: PickTask, screen: Screen) {
  selectedPickList.value = task.pick_list
  setScreen(screen)
}

async function authenticated(session: SessionUser) {
  notify('')
  user.value = { ...session, roles: await getRoles().catch(() => []) }
  await refresh()
}

async function claim(salesOrder: string) {
  const task = await run(() => claimTask(salesOrder), `${salesOrder} claimed.`)
  if (task) openTask(task, 'pick')
}

async function release(task: PickTask) {
  const done = await run(() => releaseTask(task.pick_list), `${task.sales_order} returned to the queue.`)
  if (done) setScreen('operations')
}

function lineQty(line: TaskLine) {
  return quantities.value[line.row] ?? Math.max(line.requested_qty - line.picked_qty, 0)
}

async function scanned(value: string) {
  const target = scanTarget.value
  const task = selectedTask.value
  scanTarget.value = null
  if (!target || !task) return
  const line = task.lines.find((entry) => entry.row === target.row)
  if (!line) return
  if (target.kind === 'location') {
    await run(() => confirmLocation(task.pick_list, line.row, value), `Location ${line.location} confirmed.`)
  } else {
    const qty = lineQty(line)
    await run(() => confirmPick(task.pick_list, line.row, value, qty), `${qty} × ${line.item_code} confirmed.`)
  }
}

async function reportShortage(task: PickTask, line: TaskLine) {
  const reason = (reasons.value[line.row] ?? '').trim()
  if (!reason) return notify('A shortage reason is required.', true)
  await run(() => recordShortage(task.pick_list, line.row, reason), 'Short pick recorded. A supervisor must approve it.')
}

async function approve(task: PickTask, line: TaskLine) {
  await run(() => approveShortage(task.pick_list, line.row), `Short pick on ${line.item_code} approved.`)
}

async function complete(task: PickTask) {
  const done = await run(() => completeTask(task.pick_list), `${task.sales_order} picked and submitted in ERPNext.`)
  if (done) setScreen('operations')
}

function created(order: IngestedOrder) {
  submittedOrder.value = order
  setScreen('operations')
}

async function signOut() {
  try { await logout() } catch { /* The local browser state still needs clearing. */ }
  user.value = null
  notify('')
  listing.value = { claimable: [], active: [] }
  activeScreen.value = 'operations'
}

function statusClass(status: TaskStatus) {
  return `status-${status.replaceAll('_', '-')}`
}

function lineState(line: TaskLine): 'locate' | 'pick' | 'pending' | 'done' {
  if (line.shortage_state === 'Pending') return 'pending'
  if (line.picked_qty >= line.requested_qty) return 'done'
  return line.location_confirmed ? 'pick' : 'locate'
}

watch(selectedTask, (task) => {
  if (!task && activeScreen.value === 'pick' && selectedPickList.value) selectedPickList.value = undefined
})
</script>

<template>
  <FrappeUIProvider>
    <LoginPanel v-if="!user" @authenticated="authenticated" />
    <div v-else class="app-shell">
      <header class="topbar">
        <button class="brand-lockup brand-button" @click="setScreen('operations')"><span class="brand-mark">›</span> CLOUD WMS</button>
        <div class="topbar-status"><span class="status-dot"></span> ERPNext session active</div>
        <div class="user-chip"><span>{{ user.fullName.slice(0, 1).toUpperCase() }}</span><div><strong>{{ user.fullName }}</strong><small>{{ isSupervisor ? 'Supervisor' : 'Warehouse operator' }}</small></div><button @click="signOut">Sign out</button></div>
      </header>

      <aside class="sidebar">
        <p class="sidebar-label">OPERATIONS</p>
        <button :class="{ active: activeScreen === 'operations' }" @click="setScreen('operations')"><i>01</i>Workboard <b>{{ activeTasks.length + listing.claimable.length }}</b></button>
        <button :class="{ active: activeScreen === 'create-order' }" @click="setScreen('create-order')"><i>02</i>Test order</button>
        <button :class="{ active: activeScreen === 'pick' }" :disabled="!selectedTask" @click="setScreen('pick')"><i>03</i>Pick</button>
        <button :class="{ active: activeScreen === 'qa' }" @click="setScreen('qa')"><i>04</i>QA review <b v-if="qaTasks.length">{{ qaTasks.length }}</b></button>
        <button :class="{ active: activeScreen === 'dispatch' }" @click="setScreen('dispatch')"><i>05</i>Dispatch</button>
        <div class="prototype-notice"><span>PROTOTYPE</span><p>Sales Orders and Pick Lists are real ERPNext documents. Dispatch is not wired to a Delivery Note yet.</p></div>
      </aside>

      <main class="workspace">
        <section v-if="activeScreen === 'operations'" class="screen-grid">
          <div class="screen-header">
            <div><p class="eyebrow">Warehouse / Main</p><h1>Today’s flow</h1><p>Claim the next order, scan its shelf and confirm the item.</p></div>
            <Button class="primary-button" variant="solid" @click="setScreen('create-order')">New test order</Button>
          </div>
          <p v-if="submittedOrder" class="form-success" role="status">{{ submittedOrder.sales_order }} is submitted in ERPNext and is in the pick queue below.</p>
          <p v-if="message" :class="messageIsError ? 'form-error' : 'form-success'" role="status">{{ message }}</p>
          <div class="metric-grid"><div class="metric-card"><span>AVAILABLE</span><strong>{{ listing.claimable.length }}</strong><small>Ready to claim</small></div><div class="metric-card"><span>IN PROGRESS</span><strong>{{ inProgress.length }}</strong><small>Picker-owned work</small></div><div class="metric-card warning"><span>QA HOLD</span><strong>{{ qaTasks.length }}</strong><small>Short picks to approve</small></div><div class="metric-card success"><span>READY TO SHIP</span><strong>{{ dispatchTasks.length }}</strong><small>Submitted Pick Lists</small></div></div>
          <section class="surface-card task-list"><div class="section-heading"><div><p class="eyebrow">Live work</p><h2>Pick queue</h2></div><span>{{ activeTasks.length + listing.claimable.length }} open</span></div>
            <div v-if="!activeTasks.length && !listing.claimable.length" class="empty-state"><strong>No open work.</strong><p>Submitted Sales Orders with stock to pick appear here, ready to claim.</p><Button variant="outline" @click="setScreen('create-order')">Create test order</Button></div>
            <article v-for="task in activeTasks" :key="task.pick_list" class="task-row"><div class="task-route"><span class="route-dot"></span><div><strong>{{ task.sales_order }}</strong><small>{{ task.customer }} · {{ task.lines[0]?.location }}</small></div></div><div class="task-item"><strong>{{ task.lines.length }} line{{ task.lines.length === 1 ? '' : 's' }}</strong><small>{{ task.mine ? 'Assigned to you' : task.assignees.join(', ') || 'Unassigned' }}</small></div><span class="status-chip" :class="statusClass(task.status)">{{ statusLabel[task.status] }}</span><Button v-if="['claimed', 'picking'].includes(task.status) && (task.mine || isSupervisor)" variant="outline" class="row-action" @click="openTask(task, 'pick')">Continue</Button><Button v-else-if="task.status === 'qa_required' && isSupervisor" variant="outline" class="row-action" @click="openTask(task, 'qa')">Review</Button><Button v-else-if="task.status === 'ready_to_dispatch'" variant="outline" class="row-action" @click="openTask(task, 'dispatch')">View</Button><span v-else></span></article>
            <article v-for="order in listing.claimable" :key="order.sales_order" class="task-row"><div class="task-route"><span class="route-dot"></span><div><strong>{{ order.sales_order }}</strong><small>{{ order.customer }}<template v-if="order.delivery_date"> · due {{ order.delivery_date }}</template></small></div></div><div class="task-item"><strong>{{ order.lines }} line{{ order.lines === 1 ? '' : 's' }}</strong><small>{{ order.remaining_qty }} units to pick</small></div><span class="status-chip status-available">{{ statusLabel.available }}</span><Button variant="solid" class="row-action" :disabled="busy" @click="claim(order.sales_order)">Claim</Button></article>
          </section>
        </section>

        <OrderForm v-else-if="activeScreen === 'create-order'" @created="created" />

        <section v-else-if="activeScreen === 'pick'" class="screen-grid">
          <div class="screen-header"><div><p class="eyebrow">Picker workflow</p><h1>{{ selectedTask?.sales_order || 'Select a task' }}</h1><p>Scan each shelf, scan the item, and confirm the quantity. Report a shortage if the shelf is short.</p></div><span v-if="selectedTask" class="status-chip" :class="statusClass(selectedTask.status)">{{ statusLabel[selectedTask.status] }}</span></div>
          <p v-if="message" class="scan-feedback" :class="{ error: messageIsError }" role="status">{{ message }}</p>
          <div v-if="selectedTask" class="pick-lines">
            <section v-for="line in selectedTask.lines" :key="line.row" class="surface-card pick-card">
              <div class="location-label"><span>LOCATION</span><strong>{{ line.location_barcode || line.location }}</strong><small>{{ line.location }}</small></div>
              <div class="item-summary"><p>EXPECTED ITEM</p><h2>{{ line.item_name || line.item_code }}</h2><code>{{ line.item_code }}</code><strong>{{ line.picked_qty }} / {{ line.requested_qty }} {{ line.uom }} picked</strong></div>
              <template v-if="lineState(line) === 'locate'"><Button class="scan-button" variant="solid" :disabled="busy" @click="scanTarget = { kind: 'location', row: line.row }">Scan location</Button></template>
              <template v-else-if="lineState(line) === 'pick'">
                <label>Quantity for this scan<input v-model.number="quantities[line.row]" type="number" min="1" :max="line.requested_qty - line.picked_qty" :placeholder="String(line.requested_qty - line.picked_qty)" /></label>
                <Button class="scan-button" variant="solid" :disabled="busy" @click="scanTarget = { kind: 'item', row: line.row }">Scan item</Button>
                <label>Shelf is short? Reason <textarea v-model="reasons[line.row]" placeholder="Required to report a shortage"></textarea></label>
                <Button variant="outline" :disabled="busy" @click="reportShortage(selectedTask, line)">Report shortage</Button>
              </template>
              <p v-else-if="lineState(line) === 'pending'" class="form-error">Short by {{ line.requested_qty - line.picked_qty }}: “{{ line.shortage_reason }}”. Waiting for supervisor approval.</p>
              <p v-else class="form-success">Line complete<template v-if="line.shortage_state === 'Approved'"> (short pick approved: “{{ line.shortage_reason }}”)</template>.</p>
            </section>
            <section class="surface-card confirm-card"><p class="eyebrow">Finish</p><h2>Complete the pick</h2><div class="shortage-callout"><span>QA GATE</span><p>A short pick must be approved by a supervisor before the Pick List can be submitted.</p></div><Button class="primary-button" variant="solid" :disabled="busy || !canCompleteSelected" @click="complete(selectedTask)">Submit Pick List</Button> <Button variant="outline" :disabled="busy" @click="release(selectedTask)">Release to queue</Button></section>
          </div>
          <div v-else class="empty-state"><strong>Select a task first.</strong><Button variant="outline" @click="setScreen('operations')">Open workboard</Button></div>
        </section>

        <section v-else-if="activeScreen === 'qa'" class="screen-grid">
          <div class="screen-header"><div><p class="eyebrow">Controlled exception</p><h1>Short-pick QA</h1><p>Approving reduces the Pick List to what was actually picked before it is submitted.</p></div><span class="system-pill">Supervisor approval required</span></div>
          <p v-if="message" :class="messageIsError ? 'form-error' : 'form-success'" role="status">{{ message }}</p>
          <section class="surface-card qa-list"><div v-if="!isSupervisor" class="empty-state"><strong>Supervisors only.</strong><p>Ask a supervisor to approve short picks.</p></div><div v-else-if="!qaTasks.length" class="empty-state"><strong>Nothing is awaiting QA.</strong><p>Short picks will appear here with their reason and requested quantity.</p></div><template v-else><template v-for="task in qaTasks" :key="task.pick_list"><article v-for="line in task.lines.filter((entry) => entry.shortage_state === 'Pending')" :key="line.row" class="qa-row"><div><span class="warning-stripe"></span><p class="eyebrow">{{ task.sales_order }} · {{ task.customer }}</p><h2>{{ line.item_name || line.item_code }}</h2><p>{{ line.picked_qty }} of {{ line.requested_qty }} picked · reason: <strong>{{ line.shortage_reason }}</strong></p></div><Button class="primary-button" variant="solid" :disabled="busy" @click="approve(task, line)">Approve short pick</Button></article></template></template></section>
        </section>

        <section v-else-if="activeScreen === 'dispatch'" class="screen-grid">
          <div class="screen-header"><div><p class="eyebrow">Dispatch station</p><h1>Ready to leave</h1><p>Picked and submitted. Delivery Note creation is the next phase.</p></div><span class="system-pill">Delivery Note: not yet wired</span></div>
          <section class="surface-card dispatch-list"><div v-if="!dispatchTasks.length" class="empty-state"><strong>No task is ready to ship.</strong><p>Complete a pick, or approve a short pick first.</p></div><article v-for="task in dispatchTasks" :key="task.pick_list" class="dispatch-row"><div><p class="eyebrow">{{ task.sales_order }} · {{ task.customer }}</p><h2>{{ task.pick_list }} · {{ task.lines.reduce((sum, line) => sum + line.picked_qty, 0) }} units</h2><p v-if="task.lines.some((line) => line.shortage_state === 'Approved')" class="approved-note">Includes an approved short pick</p></div></article></section>
        </section>
      </main>
    </div>
    <CameraScanner v-if="scanTarget" @detected="scanned" @close="scanTarget = null" />
  </FrappeUIProvider>
</template>
