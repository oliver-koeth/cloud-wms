<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { Button } from 'frappe-ui'
import { amendOrder, cancelOrder, getOrder, listCustomers, listItems, listOrders } from '../lib/erpnext'
import type { CustomerSummary, ItemSummary, OrderDetail, OrderSummary } from '../types'

const STATUSES = ['Draft', 'On Hold', 'To Deliver and Bill', 'To Bill', 'To Deliver', 'Completed', 'Cancelled', 'Closed']

interface LineDraft { item_code: string; qty: number; rate: number | null }

const rows = ref<OrderSummary[]>([])
const search = ref('')
const status = ref('')
const current = ref<OrderDetail>()
const editing = ref(false)
const customers = ref<CustomerSummary[]>([])
const items = ref<ItemSummary[]>([])
const draft = ref({ customer: '', delivery_date: '', lines: [] as LineDraft[] })
const busy = ref(false)
const error = ref('')
const success = ref('')

const canChange = computed(() => current.value?.docstatus === 1 && !current.value.amended_to)

async function guard(action: () => Promise<void>, done: string | (() => string) = '') {
  busy.value = true
  error.value = ''
  success.value = ''
  try {
    await action()
    success.value = typeof done === 'function' ? done() : done
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : 'The request failed.'
  } finally {
    busy.value = false
  }
}

const reload = async () => { rows.value = await listOrders(search.value.trim(), status.value) }
const load = () => guard(reload)

const open = (name: string) =>
  guard(async () => {
    current.value = await getOrder(name)
    editing.value = false
  })

async function cancel() {
  const order = current.value
  if (!order || !confirm(`Cancel ${order.name} in ERPNext? This cannot be undone; use Edit to replace it instead.`)) return
  await guard(async () => {
    current.value = await cancelOrder(order.name, order.modified)
    await reload()
  }, `${order.name} cancelled.`)
}

async function startEdit() {
  const order = current.value
  if (!order) return
  await guard(async () => {
    if (!customers.value.length) [customers.value, items.value] = await Promise.all([listCustomers(), listItems()])
    draft.value = {
      customer: order.customer,
      delivery_date: order.delivery_date ?? new Date().toISOString().slice(0, 10),
      lines: order.items.map((line) => ({ item_code: line.item_code, qty: line.qty, rate: line.rate })),
    }
    editing.value = true
  })
}

async function amend() {
  const order = current.value
  if (!order) return
  if (!draft.value.lines.length || draft.value.lines.some((line) => !line.item_code || !(line.qty > 0))) {
    error.value = 'Every line needs an item and a quantity above zero.'
    return
  }
  await guard(async () => {
    const amended = await amendOrder({
      sales_order: order.name,
      customer: draft.value.customer,
      delivery_date: draft.value.delivery_date,
      lines: draft.value.lines.map((line) => ({ item_code: line.item_code, qty: Number(line.qty), rate: typeof line.rate === 'number' ? line.rate : undefined })),
      modified: order.modified,
    })
    current.value = amended
    editing.value = false
    await reload()
  }, () => `${order.name} was cancelled and replaced by ${current.value?.name}.`)
}

onMounted(load)
</script>

<template>
  <section class="screen-grid">
    <div class="screen-header">
      <div><p class="eyebrow">Admin / Orders</p><h1>Sales Orders</h1><p>Submitted ERPNext orders cannot be edited in place. Edit cancels the order and submits an amended copy.</p></div>
      <span class="system-pill">Cancel &amp; amend</span>
    </div>
    <div class="admin-layout">
      <section class="surface-card admin-list">
        <form class="admin-search" @submit.prevent="load">
          <input v-model="search" type="search" placeholder="Search order, customer, reference…" />
          <select v-model="status" @change="load"><option value="">Any status</option><option v-for="option in STATUSES" :key="option">{{ option }}</option></select>
        </form>
        <button v-for="row in rows" :key="row.name" class="admin-row" :class="{ active: current?.name === row.name, disabled: row.docstatus === 2 }" @click="open(row.name)">
          <strong>{{ row.name }} <span class="status-chip">{{ row.status }}</span></strong>
          <small>{{ row.customer_name || row.customer }} · due {{ row.delivery_date || '—' }} · {{ row.grand_total }} {{ row.currency }}</small>
        </button>
        <p v-if="!rows.length" class="muted admin-empty">No orders found.</p>
      </section>

      <section class="surface-card admin-form">
        <template v-if="current">
          <p class="eyebrow">{{ current.status }} · {{ current.cloud_wms_source || 'ERPNext' }}<template v-if="current.cloud_wms_external_order_id"> · {{ current.cloud_wms_external_order_id }}</template></p>
          <h2>{{ current.name }}</h2>
          <p class="muted">{{ current.customer_name || current.customer }} · due {{ current.delivery_date || '—' }} · {{ current.per_picked }}% picked · {{ current.per_delivered }}% delivered</p>
          <p v-if="current.amended_from" class="muted">Amends {{ current.amended_from }}.</p>
          <p v-if="current.amended_to" class="muted">Replaced by <button class="link-button" @click="open(current.amended_to)">{{ current.amended_to }}</button>.</p>

          <template v-if="!editing">
            <div class="admin-lines">
              <p v-for="line in current.items" :key="line.name"><span>{{ line.item_name || line.item_code }} <code>{{ line.item_code }}</code></span><strong>{{ line.qty }} {{ line.uom }}</strong><small>@ {{ line.rate }} · {{ line.picked_qty }} picked · {{ line.delivered_qty }} delivered</small></p>
            </div>
            <p v-if="current.pick_lists.length || current.delivery_notes.length" class="muted">
              <template v-for="doc in current.pick_lists" :key="doc.name">Pick List {{ doc.name }} ({{ doc.status }}). </template>
              <template v-for="doc in current.delivery_notes" :key="doc.name">Delivery Note {{ doc.name }} ({{ doc.status }}). </template>
            </p>
            <div v-if="canChange && current.cancel_blocker" class="shortage-callout"><span>CANNOT CHANGE YET</span><p>{{ current.cancel_blocker.message }} {{ current.cancel_blocker.next_action }}</p></div>
          </template>

          <form v-else class="admin-amend" @submit.prevent="amend">
            <label>Customer<select v-model="draft.customer"><option v-for="customer in customers" :key="customer.name" :value="customer.name">{{ customer.customer_name }}</option></select></label>
            <label>Delivery date<input v-model="draft.delivery_date" type="date" required /></label>
            <div v-for="(line, index) in draft.lines" :key="index" class="order-line">
              <label>Item<select v-model="line.item_code" required><option disabled value="">Select item</option><option v-for="item in items" :key="item.name" :value="item.name">{{ item.item_name }} · {{ item.name }}</option></select></label>
              <div class="inline-fields">
                <label>Quantity<input v-model.number="line.qty" type="number" min="1" step="1" required /></label>
                <label>Rate<input v-model.number="line.rate" type="number" min="0" step="0.01" /></label>
              </div>
              <Button v-if="draft.lines.length > 1" type="button" variant="outline" @click="draft.lines.splice(index, 1)">Remove line</Button>
            </div>
            <Button type="button" variant="outline" @click="draft.lines.push({ item_code: '', qty: 1, rate: null })">Add line</Button>
          </form>

          <p v-if="error" class="form-error" role="alert">{{ error }}</p>
          <p v-if="success" class="form-success" role="status">{{ success }}</p>
          <div v-if="canChange" class="admin-actions">
            <template v-if="editing">
              <Button class="primary-button" variant="solid" :loading="busy" @click="amend">Cancel &amp; submit amended order</Button>
              <Button variant="outline" :disabled="busy" @click="editing = false">Discard</Button>
            </template>
            <template v-else>
              <Button class="primary-button" variant="solid" :disabled="busy || !!current.cancel_blocker" @click="startEdit">Edit</Button>
              <Button variant="outline" :disabled="busy || !!current.cancel_blocker" @click="cancel">Cancel order</Button>
            </template>
          </div>
        </template>
        <div v-else class="empty-state"><strong>Select an order.</strong><p>Pick a Sales Order to see its lines, pick lists and delivery notes.</p></div>
      </section>
    </div>
  </section>
</template>
