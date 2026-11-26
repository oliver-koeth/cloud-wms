<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { Button } from 'frappe-ui'
import { cancelPosting, listItems, listLocations, listPostings, listStock, postStock } from '../lib/erpnext'
import { useGuard } from '../lib/useGuard'
import type { ItemSummary, LocationRow, StockLevel, StockPosting, StockPurpose } from '../types'

const purposes: Array<{ value: StockPurpose; label: string; hint: string }> = [
  { value: 'receipt', label: 'Receipt', hint: 'Goods arrive at a bin (Stock Entry: Material Receipt).' },
  { value: 'transfer', label: 'Transfer', hint: 'Move stock from one bin to another (Stock Entry: Material Transfer).' },
  { value: 'count', label: 'Count', hint: 'Set the counted quantity of a bin (Stock Reconciliation).' },
]

const blank = (purpose: StockPurpose = 'receipt') => ({ purpose, item_code: '', qty: '' as number | '', to_warehouse: '', from_warehouse: '', rate: '' as number | '', reason: '' })

const { busy, error, success, guard } = useGuard()
const stock = ref<StockLevel[]>([])
const postings = ref<StockPosting[]>([])
const items = ref<ItemSummary[]>([])
const locations = ref<LocationRow[]>([])
const search = ref('')
const warehouse = ref('')
const form = ref(blank())

const bins = computed(() => locations.value.filter((row) => !row.is_group && !row.disabled))
const stockItems = computed(() => items.value.filter((item) => item.is_stock_item && !item.disabled))
const hint = computed(() => purposes.find((entry) => entry.value === form.value.purpose)?.hint)

const reload = async () => {
  ;[stock.value, postings.value] = await Promise.all([listStock(search.value.trim(), warehouse.value), listPostings()])
}

function fillFrom(row: StockLevel) {
  form.value = { ...blank(form.value.purpose), item_code: row.item_code, to_warehouse: row.warehouse }
  if (form.value.purpose === 'transfer') form.value = { ...form.value, from_warehouse: row.warehouse, to_warehouse: '' }
  if (form.value.purpose === 'count') form.value.qty = row.actual_qty
}

async function post() {
  let posted = ''
  await guard(
    async () => {
      const { purpose, item_code, qty, to_warehouse, from_warehouse, rate, reason } = form.value
      const posting = await postStock({
        purpose,
        item_code,
        qty: Number(qty),
        to_warehouse,
        from_warehouse: purpose === 'transfer' ? from_warehouse : undefined,
        rate: purpose !== 'transfer' && rate !== '' ? Number(rate) : undefined,
        reason: reason.trim() || undefined,
      })
      posted = posting.name
      form.value = blank(purpose)
      await reload()
    },
    () => `${posted} submitted in ERPNext.`,
  )
}

async function cancel(posting: StockPosting) {
  const reason = prompt(`Cancel ${posting.name}? ERPNext reverses its stock ledger entries. Reason:`)
  if (reason === null) return
  await guard(async () => {
    await cancelPosting(posting, reason.trim() || undefined)
    await reload()
  }, `${posting.name} cancelled.`)
}

const place = (posting: StockPosting) =>
  posting.from_warehouse ? `${posting.from_warehouse} → ${posting.to_warehouse}` : posting.to_warehouse

onMounted(() =>
  guard(async () => {
    ;[items.value, locations.value] = await Promise.all([listItems(), listLocations()])
    await reload()
  }),
)
</script>

<template>
  <section class="screen-grid">
    <div class="screen-header">
      <div><p class="eyebrow">Admin / Inventory</p><h1>Stock</h1><p>Bin quantities from ERPNext. Receipts, transfers and counts post real stock documents; cancelling one reverses its ledger entries.</p></div>
    </div>
    <div class="admin-layout">
      <section class="surface-card admin-list">
        <form class="admin-search admin-search-wide" @submit.prevent="guard(reload)">
          <input v-model="search" placeholder="Item code, name or barcode" />
          <select v-model="warehouse" @change="guard(reload)"><option value="">All locations</option><option v-for="row in locations" :key="row.name" :value="row.name">{{ '— '.repeat(row.depth) }}{{ row.warehouse_name }}</option></select>
          <Button variant="outline" type="submit" :disabled="busy">Search</Button>
        </form>
        <button v-for="row in stock" :key="`${row.item_code}@${row.warehouse}`" class="admin-row" @click="fillFrom(row)">
          <strong>{{ row.item_code }}<code v-if="row.barcode">{{ row.barcode }}</code><span class="status-chip" :class="row.actual_qty > 0 ? 'chip-ok' : 'chip-warn'">{{ row.actual_qty }} {{ row.stock_uom }}</span></strong>
          <small>{{ row.item_name }} · {{ row.warehouse }}</small>
          <small>{{ row.reserved_stock }} reserved · {{ row.projected_qty }} projected<template v-if="row.valuation_rate"> · rate {{ row.valuation_rate }}</template></small>
        </button>
        <p v-if="!stock.length" class="muted admin-empty">No stock matches. Post a receipt to put stock on a bin.</p>
      </section>

      <div class="admin-stack">
        <form class="surface-card admin-form" @submit.prevent="post">
          <p class="eyebrow">New stock posting</p>
          <div class="admin-tabs" role="tablist">
            <button v-for="entry in purposes" :key="entry.value" type="button" role="tab" :aria-selected="form.purpose === entry.value" :class="{ active: form.purpose === entry.value }" @click="form = blank(entry.value)">{{ entry.label }}</button>
          </div>
          <p class="muted">{{ hint }}</p>
          <label>Item<select v-model="form.item_code" required><option value="" disabled>Choose an item</option><option v-for="item in stockItems" :key="item.name" :value="item.name">{{ item.name }} · {{ item.item_name }}</option></select></label>
          <label v-if="form.purpose === 'transfer'">From bin<select v-model="form.from_warehouse" required><option value="" disabled>Choose a bin</option><option v-for="bin in bins" :key="bin.name" :value="bin.name">{{ bin.name }}</option></select></label>
          <label>{{ form.purpose === 'transfer' ? 'To bin' : 'Bin' }}<select v-model="form.to_warehouse" required><option value="" disabled>Choose a bin</option><option v-for="bin in bins" :key="bin.name" :value="bin.name">{{ bin.name }}</option></select></label>
          <label>{{ form.purpose === 'count' ? 'Counted quantity' : 'Quantity' }}<input v-model.number="form.qty" type="number" :min="form.purpose === 'count' ? 0 : 0.001" step="any" required /></label>
          <label v-if="form.purpose !== 'transfer'">Valuation rate (optional)<input v-model.number="form.rate" type="number" min="0" step="any" placeholder="ERPNext default" /></label>
          <label>Reason<textarea v-model="form.reason" maxlength="500" placeholder="Why the stock changes; kept in the audit log"></textarea></label>
          <p v-if="error" class="form-error" role="alert">{{ error }}</p>
          <p v-if="success" class="form-success" role="status">{{ success }}</p>
          <div class="admin-actions"><Button class="primary-button" variant="solid" type="submit" :loading="busy">Submit posting</Button></div>
        </form>

        <section class="surface-card admin-form">
          <p class="eyebrow">Recent postings</p>
          <div v-if="postings.length" class="admin-lines">
            <p v-for="posting in postings" :key="`${posting.doctype}:${posting.name}`">
              <span><code>{{ posting.name }}</code> {{ posting.purpose }} · {{ posting.item_code }} × {{ posting.qty }}</span>
              <span v-if="posting.docstatus === 2" class="status-chip chip-off">Cancelled</span>
              <button v-else-if="posting.docstatus === 1" type="button" class="link-button" :disabled="busy" @click="cancel(posting)">Cancel</button>
              <span v-else class="status-chip">Draft</span>
              <small>{{ place(posting) }} · {{ posting.posting_date }} {{ posting.posting_time?.slice(0, 5) }} · {{ posting.owner }}<template v-if="posting.remarks"> · {{ posting.remarks }}</template></small>
            </p>
          </div>
          <p v-else class="muted">No receipts, transfers or counts yet.</p>
        </section>
      </div>
    </div>
  </section>
</template>
