<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { Button } from 'frappe-ui'
import { getFormOptions, ingestOrder } from '../lib/erpnext'
import type { FormOptions, IngestedOrder } from '../types'

const emit = defineEmits<{ created: [order: IngestedOrder] }>()

interface LineDraft { itemCode: string; quantity: number; rate: number | null }

const options = ref<FormOptions>({ customers: [], items: [], warehouses: [] })
const loading = ref(true)
const saving = ref(false)
const error = ref('')
const success = ref('')
const deliveryDate = new Date(Date.now() + 86_400_000).toISOString().slice(0, 10)
const emptyLine = (): LineDraft => ({ itemCode: '', quantity: 1, rate: null })
const form = ref({ customer: '', warehouse: '', externalOrderId: '', deliveryDate, lines: [emptyLine()] })

// One key per distinct request: a retry of the same submission replays instead of duplicating the order.
let idempotencyKey = crypto.randomUUID()
watch(form, () => { idempotencyKey = crypto.randomUUID() }, { deep: true })

const needsDemoData = computed(() => !loading.value && (!options.value.customers.length || !options.value.items.length))

function itemFor(code: string) {
  return options.value.items.find((item) => item.name === code)
}

function addLine() {
  form.value.lines.push(emptyLine())
}

function removeLine(index: number) {
  if (form.value.lines.length > 1) form.value.lines.splice(index, 1)
}

async function loadOptions() {
  try {
    options.value = await getFormOptions()
    if (!form.value.customer) form.value.customer = options.value.customers[0]?.name ?? ''
    if (!form.value.lines[0].itemCode) form.value.lines[0].itemCode = options.value.items[0]?.name ?? ''
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : 'Could not load ERPNext order data.'
  }
}

onMounted(async () => {
  await loadOptions()
  loading.value = false
})

async function submit() {
  if (!options.value.company) {
    error.value = 'No ERPNext Company is available to this user. Complete ERPNext setup or grant Company access.'
    return
  }
  if (!form.value.customer || form.value.lines.some((line) => !line.itemCode)) {
    error.value = 'A Customer and an Item on every line are required.'
    return
  }

  saving.value = true
  success.value = ''
  error.value = ''
  try {
    const order = await ingestOrder(
      {
        source: 'manual',
        externalOrderId: form.value.externalOrderId.trim(),
        customer: form.value.customer,
        company: options.value.company,
        deliveryDate: form.value.deliveryDate,
        warehouse: form.value.warehouse,
        lines: form.value.lines.map((line) => ({
          itemCode: line.itemCode,
          quantity: Number(line.quantity),
          rate: typeof line.rate === 'number' ? line.rate : undefined,
        })),
      },
      idempotencyKey,
    )
    success.value = order.duplicate
      ? `${order.sales_order} already exists for this external reference; nothing new was created.`
      : `${order.sales_order} was submitted in ERPNext. It is ready for a picker to claim.`
    emit('created', order)
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : 'Could not create the Sales Order.'
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <section class="screen-grid order-screen">
    <div class="screen-header">
      <div>
        <p class="eyebrow">Tactical intake</p>
        <h1>Create a test order</h1>
        <p>Submit a real ERPNext Sales Order through the WMS intake service, with the signed-in user’s permissions.</p>
      </div>
      <span class="system-pill">ERPNext · Submitted Sales Order</span>
    </div>

    <div class="order-layout">
      <form class="surface-card order-form" @submit.prevent="submit">
        <div class="form-section-title"><span>01</span><div><strong>Order demand</strong><small>Choose existing ERPNext master data</small></div></div>
        <p v-if="loading" class="muted">Loading customers, items and warehouse locations…</p>
        <template v-else>
          <div v-if="needsDemoData" class="demo-data-callout">
            <div><span>LOCAL DEMO DATA</span><p>This site has no Customer or Item yet. Run <code>make demo-data</code> to create them.</p></div>
          </div>
          <label>
            Customer
            <select v-model="form.customer" required>
              <option disabled value="">Select customer</option>
              <option v-for="customer in options.customers" :key="customer.name" :value="customer.name">
                {{ customer.customer_name || customer.name }}
              </option>
            </select>
          </label>
          <label>
            Delivery date
            <input v-model="form.deliveryDate" type="date" required />
          </label>

          <label>
            External reference <small>(optional, prevents duplicate orders)</small>
            <input v-model="form.externalOrderId" type="text" maxlength="140" placeholder="e.g. PO-1042" />
          </label>

          <div class="form-section-title compact"><span>02</span><div><strong>Order lines</strong><small>Each line becomes a pick line once the order is claimed</small></div></div>
          <div v-for="(line, index) in form.lines" :key="index" class="order-line">
            <label>
              Item
              <select v-model="line.itemCode" required @change="line.rate = Number(itemFor(line.itemCode)?.standard_rate ?? 0)">
                <option disabled value="">Select item</option>
                <option v-for="item in options.items" :key="item.name" :value="item.name">
                  {{ item.item_name || item.name }} · {{ item.name }}
                </option>
              </select>
            </label>
            <div class="inline-fields">
              <label>Quantity<input v-model.number="line.quantity" type="number" min="1" step="1" required /></label>
              <label>Rate<input v-model.number="line.rate" type="number" min="0" step="0.01" :placeholder="String(itemFor(line.itemCode)?.standard_rate ?? 0)" /></label>
            </div>
            <Button v-if="form.lines.length > 1" type="button" variant="outline" @click="removeLine(index)">Remove line</Button>
          </div>
          <Button type="button" variant="outline" @click="addLine">Add line</Button>
          <label>
            Source warehouse
            <select v-model="form.warehouse">
              <option value="">Use ERPNext default</option>
              <option v-for="warehouse in options.warehouses" :key="warehouse.name" :value="warehouse.name">
                {{ warehouse.warehouse_name || warehouse.name }}
              </option>
            </select>
          </label>
        </template>
        <p v-if="error" class="form-error" role="alert">{{ error }}</p>
        <p v-if="success" class="form-success" role="status">{{ success }}</p>
        <Button class="primary-button" variant="solid" :loading="saving" :disabled="loading" type="submit">Create Sales Order</Button>
      </form>

      <aside class="surface-card guide-card">
        <span class="signal-label">OPERATIONAL BOUNDARY</span>
        <h2>ERPNext owns the order.</h2>
        <p>This screen submits a real <strong>Sales Order</strong> through the WMS intake service. Retrying the same request never creates a second order.</p>
        <ol>
          <li>ERPNext validates customer, item, company and permission.</li>
          <li>The submitted order becomes claimable; a Pick List is created when a picker claims it.</li>
          <li>Short picks and partial delivery are recorded against the ERPNext documents.</li>
        </ol>
      </aside>
    </div>
  </section>
</template>
