<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { Button, FrappeUIProvider } from 'frappe-ui'
import CameraScanner from './components/CameraScanner.vue'
import LoginPanel from './components/LoginPanel.vue'
import OrderForm from './components/OrderForm.vue'
import { logout } from './lib/erpnext'
import { loadTasks, persistTasks, statusLabel } from './lib/tasks'
import type { Screen, SessionUser, TaskStatus, WmsTask } from './types'

const user = ref<SessionUser | null>(null)
const activeScreen = ref<Screen>('operations')
const tasks = ref<WmsTask[]>(loadTasks())
const selectedTaskId = ref<string>()
const scannerOpen = ref(false)
const pickedQuantity = ref(0)
const shortageReason = ref('')
const scanMessage = ref('')

watch(tasks, persistTasks, { deep: true })

const selectedTask = computed(() => tasks.value.find((task) => task.id === selectedTaskId.value) ?? tasks.value[0])
const activeTasks = computed(() => tasks.value.filter((task) => !['dispatched'].includes(task.status)))
const qaTasks = computed(() => tasks.value.filter((task) => task.status === 'qa_required'))
const dispatchTasks = computed(() => tasks.value.filter((task) => task.status === 'ready_to_dispatch'))

function setScreen(screen: Screen) {
  activeScreen.value = screen
  scanMessage.value = ''
}

function selectTask(task: WmsTask, screen: Screen) {
  selectedTaskId.value = task.id
  pickedQuantity.value = task.lines[0]?.pickedQty ?? 0
  shortageReason.value = task.lines[0]?.shortageReason ?? ''
  setScreen(screen)
}

function updateTask(taskId: string, patch: Partial<WmsTask>) {
  const index = tasks.value.findIndex((task) => task.id === taskId)
  if (index >= 0) tasks.value[index] = { ...tasks.value[index], ...patch }
}

function claim(task: WmsTask) {
  updateTask(task.id, { status: 'claimed', claimedBy: user.value?.fullName })
  selectTask(task, 'pick')
}

function scan(value: string) {
  const task = selectedTask.value
  if (!task) return
  const line = task.lines[0]
  if (value === line.itemCode) {
    scanMessage.value = `Item ${value} confirmed at ${line.location}.`
    updateTask(task.id, { status: 'picking' })
  } else {
    scanMessage.value = `Mismatch: expected ${line.itemCode}; scanned ${value}. No quantity was changed.`
  }
  scannerOpen.value = false
}

function completePick() {
  const task = selectedTask.value
  if (!task) return
  const line = task.lines[0]
  const quantity = Number(pickedQuantity.value)
  if (!Number.isFinite(quantity) || quantity < 0 || quantity > line.requestedQty) {
    scanMessage.value = `Enter a quantity from 0 to ${line.requestedQty}.`
    return
  }
  const isShort = quantity < line.requestedQty
  if (isShort && !shortageReason.value.trim()) {
    scanMessage.value = 'A shortage reason is required before QA review.'
    return
  }
  const lines = task.lines.map((entry) => ({ ...entry, pickedQty: quantity, shortageReason: isShort ? shortageReason.value.trim() : undefined }))
  updateTask(task.id, { lines, status: isShort ? 'qa_required' : 'ready_to_dispatch' })
  scanMessage.value = isShort ? 'Short pick recorded. QA approval is now required before shipping.' : 'Pick complete. The task is ready for mock dispatch.'
}

function approveQa(task: WmsTask) {
  updateTask(task.id, { status: 'ready_to_dispatch', qaApproved: true })
}

function mockDispatch(task: WmsTask) {
  updateTask(task.id, { status: 'dispatched' })
}

function created(task: WmsTask) {
  tasks.value = [task, ...tasks.value]
  selectTask(task, 'operations')
}

async function signOut() {
  try { await logout() } catch { /* The local browser state still needs clearing. */ }
  user.value = null
  activeScreen.value = 'operations'
}

function statusClass(status: TaskStatus) {
  return `status-${status.replaceAll('_', '-')}`
}
</script>

<template>
  <FrappeUIProvider>
    <LoginPanel v-if="!user" @authenticated="user = $event" />
    <div v-else class="app-shell">
      <header class="topbar">
        <button class="brand-lockup brand-button" @click="setScreen('operations')"><span class="brand-mark">›</span> CLOUD WMS</button>
        <div class="topbar-status"><span class="status-dot"></span> ERPNext session active</div>
        <div class="user-chip"><span>{{ user.fullName.slice(0, 1).toUpperCase() }}</span><div><strong>{{ user.fullName }}</strong><small>Warehouse operator</small></div><button @click="signOut">Sign out</button></div>
      </header>

      <aside class="sidebar">
        <p class="sidebar-label">OPERATIONS</p>
        <button :class="{ active: activeScreen === 'operations' }" @click="setScreen('operations')"><i>01</i>Workboard <b>{{ activeTasks.length }}</b></button>
        <button :class="{ active: activeScreen === 'create-order' }" @click="setScreen('create-order')"><i>02</i>Test order</button>
        <button :class="{ active: activeScreen === 'pick' }" :disabled="!selectedTask" @click="setScreen('pick')"><i>03</i>Pick</button>
        <button :class="{ active: activeScreen === 'qa' }" @click="setScreen('qa')"><i>04</i>QA review <b v-if="qaTasks.length">{{ qaTasks.length }}</b></button>
        <button :class="{ active: activeScreen === 'dispatch' }" @click="setScreen('dispatch')"><i>05</i>Dispatch</button>
        <div class="prototype-notice"><span>PROTOTYPE</span><p>Pick, QA and dispatch states are local WMS workflow data. Sales Orders are real ERPNext drafts.</p></div>
      </aside>

      <main class="workspace">
        <section v-if="activeScreen === 'operations'" class="screen-grid">
          <div class="screen-header">
            <div><p class="eyebrow">Warehouse / Main</p><h1>Today’s flow</h1><p>Claim the next task, scan its shelf and confirm the item.</p></div>
            <Button class="primary-button" variant="solid" @click="setScreen('create-order')">New test order</Button>
          </div>
          <div class="metric-grid"><div class="metric-card"><span>AVAILABLE</span><strong>{{ tasks.filter(t => t.status === 'available').length }}</strong><small>Ready to claim</small></div><div class="metric-card"><span>IN PROGRESS</span><strong>{{ tasks.filter(t => ['claimed', 'picking'].includes(t.status)).length }}</strong><small>Picker-owned work</small></div><div class="metric-card warning"><span>QA HOLD</span><strong>{{ qaTasks.length }}</strong><small>Short picks to approve</small></div><div class="metric-card success"><span>READY TO SHIP</span><strong>{{ dispatchTasks.length }}</strong><small>Mock dispatch queue</small></div></div>
          <section class="surface-card task-list"><div class="section-heading"><div><p class="eyebrow">Live work</p><h2>Pick queue</h2></div><span>{{ activeTasks.length }} active</span></div>
            <div v-if="!tasks.length" class="empty-state"><strong>No prototype tasks yet.</strong><p>Create a test Sales Order to add a task to this workboard.</p><Button variant="outline" @click="setScreen('create-order')">Create test order</Button></div>
            <article v-for="task in activeTasks" :key="task.id" class="task-row"><div class="task-route"><span class="route-dot"></span><div><strong>{{ task.salesOrder }}</strong><small>{{ task.customer }} · {{ task.lines[0].location }}</small></div></div><div class="task-item"><strong>{{ task.lines[0].itemName }}</strong><small>{{ task.lines[0].pickedQty }} / {{ task.lines[0].requestedQty }} confirmed</small></div><span class="status-chip" :class="statusClass(task.status)">{{ statusLabel[task.status] }}</span><Button v-if="task.status === 'available'" variant="solid" class="row-action" @click="claim(task)">Claim</Button><Button v-else-if="['claimed', 'picking'].includes(task.status)" variant="outline" class="row-action" @click="selectTask(task, 'pick')">Continue</Button><Button v-else-if="task.status === 'qa_required'" variant="outline" class="row-action" @click="selectTask(task, 'qa')">Review</Button><Button v-else variant="outline" class="row-action" @click="selectTask(task, 'dispatch')">Ship</Button></article>
          </section>
        </section>

        <OrderForm v-else-if="activeScreen === 'create-order'" @created="created" />

        <section v-else-if="activeScreen === 'pick'" class="screen-grid">
          <div class="screen-header"><div><p class="eyebrow">Picker workflow</p><h1>{{ selectedTask?.salesOrder || 'Select a task' }}</h1><p>Confirm the shelf, scan the item and record the actual quantity.</p></div><span v-if="selectedTask" class="status-chip" :class="statusClass(selectedTask.status)">{{ statusLabel[selectedTask.status] }}</span></div>
          <div v-if="selectedTask" class="pick-layout"><section class="surface-card pick-card"><div class="location-label"><span>NEXT LOCATION</span><strong>{{ selectedTask.lines[0].location }}</strong><small>Warehouse / Aisle A / Bay 01 / Shelf 02</small></div><div class="item-summary"><p>EXPECTED ITEM</p><h2>{{ selectedTask.lines[0].itemName }}</h2><code>{{ selectedTask.lines[0].itemCode }}</code><strong>{{ selectedTask.lines[0].requestedQty }} units</strong></div><Button class="scan-button" variant="solid" @click="scannerOpen = true">Open camera scanner</Button><p class="scan-feedback" :class="{ error: scanMessage.startsWith('Mismatch') || scanMessage.startsWith('Enter') || scanMessage.startsWith('A shortage') }">{{ scanMessage || 'Awaiting a barcode confirmation.' }}</p></section><section class="surface-card confirm-card"><p class="eyebrow">Quantity confirmation</p><h2>What was picked?</h2><label>Actual quantity<input v-model.number="pickedQuantity" type="number" min="0" :max="selectedTask.lines[0].requestedQty" /></label><label>Shortage reason <textarea v-model="shortageReason" placeholder="Required when quantity is lower than expected"></textarea></label><div class="shortage-callout"><span>QA GATE</span><p>Short picks are highlighted and cannot reach dispatch until a QA operator approves them.</p></div><Button class="primary-button" variant="solid" @click="completePick">Confirm pick</Button></section></div>
          <div v-else class="empty-state"><strong>Select a task first.</strong><Button variant="outline" @click="setScreen('operations')">Open workboard</Button></div>
        </section>

        <section v-else-if="activeScreen === 'qa'" class="screen-grid">
          <div class="screen-header"><div><p class="eyebrow">Controlled exception</p><h1>Short-pick QA</h1><p>Review the variance before it can proceed to mock dispatch.</p></div><span class="system-pill">Human approval required</span></div>
          <section class="surface-card qa-list"><div v-if="!qaTasks.length" class="empty-state"><strong>Nothing is awaiting QA.</strong><p>Short picks will appear here with their reason and requested quantity.</p></div><article v-for="task in qaTasks" :key="task.id" class="qa-row"><div><span class="warning-stripe"></span><p class="eyebrow">{{ task.salesOrder }} · {{ task.customer }}</p><h2>{{ task.lines[0].itemName }}</h2><p>{{ task.lines[0].pickedQty }} of {{ task.lines[0].requestedQty }} picked · reason: <strong>{{ task.lines[0].shortageReason }}</strong></p></div><Button class="primary-button" variant="solid" @click="approveQa(task)">Approve to ship</Button></article></section>
        </section>

        <section v-else-if="activeScreen === 'dispatch'" class="screen-grid">
          <div class="screen-header"><div><p class="eyebrow">Dispatch station</p><h1>Ready to leave</h1><p>Carrier labels are intentionally mocked in this first slice.</p></div><span class="system-pill">Mock shipping label</span></div>
          <section class="surface-card dispatch-list"><div v-if="!dispatchTasks.length" class="empty-state"><strong>No task is ready to ship.</strong><p>Complete a pick, or approve a short pick in QA first.</p></div><article v-for="task in dispatchTasks" :key="task.id" class="dispatch-row"><div><p class="eyebrow">{{ task.salesOrder }} · {{ task.customer }}</p><h2>{{ task.lines[0].itemName }} · {{ task.lines[0].pickedQty }} units</h2><p v-if="task.qaApproved" class="approved-note">QA-approved short pick</p></div><div class="label-mock"><small>MOCK LABEL</small><strong>JH-{{ task.salesOrder.replaceAll('-', '') }}</strong><span>Dock 02 → External delivery</span></div><Button class="primary-button" variant="solid" @click="mockDispatch(task)">Confirm mock dispatch</Button></article></section>
        </section>
      </main>
    </div>
    <CameraScanner v-if="scannerOpen" @detected="scan" @close="scannerOpen = false" />
  </FrappeUIProvider>
</template>
