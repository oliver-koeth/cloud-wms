<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { Button } from 'frappe-ui'
import { createSalesOrder, getFormOptions, prepareDemoMasterData } from '../lib/erpnext'
import { taskFromSalesOrder } from '../lib/tasks'
import type { FormOptions, WmsTask } from '../types'

const emit = defineEmits<{ created: [task: WmsTask] }>()

const options = ref<FormOptions>({ customers: [], items: [], warehouses: [] })
const loading = ref(true)
const saving = ref(false)
const preparingDemo = ref(false)
const error = ref('')
const success = ref('')
const deliveryDate = new Date(Date.now() + 86_400_000).toISOString().slice(0, 10)
const form = ref({ customer: '', itemCode: '', warehouse: '', quantity: 1, rate: 0, deliveryDate })

const selectedItem = computed(() => options.value.items.find((item) => item.name === form.value.itemCode))
const needsDemoData = computed(() => !loading.value && (!options.value.customers.length || !options.value.items.length))

watch(selectedItem, (item) => {
  if (item && !form.value.rate) form.value.rate = Number(item.standard_rate ?? 0)
})

async function loadOptions() {
  try {
    options.value = await getFormOptions()
    if (!form.value.customer) form.value.customer = options.value.customers[0]?.name ?? ''
    if (!form.value.itemCode) form.value.itemCode = options.value.items[0]?.name ?? ''
    if (!form.value.warehouse) form.value.warehouse = options.value.warehouses[0]?.name ?? ''
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : 'Could not load ERPNext order data.'
  }
}

onMounted(async () => {
  await loadOptions()
  loading.value = false
})

async function prepareDemo() {
  if (!options.value.company) {
    error.value = 'No ERPNext Company is available to this user. Complete ERPNext setup or grant Company access.'
    return
  }
  preparingDemo.value = true
  error.value = ''
  try {
    await prepareDemoMasterData(options.value.company)
    await loadOptions()
    success.value = 'Local demo Customer and Item are ready. They can now be used to create a Sales Order.'
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : 'Could not prepare local demo master data.'
  } finally {
    preparingDemo.value = false
  }
}

async function submit() {
  if (!options.value.company) {
    error.value = 'No ERPNext Company is available to this user. Complete ERPNext setup or grant Company access.'
    return
  }
  if (!form.value.customer || !form.value.itemCode) {
    error.value = 'A Customer and Item are required. Create master data in ERPNext first.'
    return
  }

  saving.value = true
  success.value = ''
  error.value = ''
  try {
    const salesOrder = await createSalesOrder({ ...form.value, company: options.value.company })
    const item = selectedItem.value
    const task = taskFromSalesOrder(
      salesOrder,
      form.value.customer,
      form.value.itemCode,
      item?.item_name || form.value.itemCode,
      Number(form.value.quantity),
    )
    success.value = `${salesOrder} was created in ERPNext as a draft Sales Order.`
    emit('created', task)
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
        <p>Create a real, unsubmitted ERPNext Sales Order with the signed-in user’s permissions.</p>
      </div>
      <span class="system-pill">ERPNext · Draft Sales Order</span>
    </div>

    <div class="order-layout">
      <form class="surface-card order-form" @submit.prevent="submit">
        <div class="form-section-title"><span>01</span><div><strong>Order demand</strong><small>Choose existing ERPNext master data</small></div></div>
        <p v-if="loading" class="muted">Loading customers, items and warehouse locations…</p>
        <template v-else>
          <div v-if="needsDemoData" class="demo-data-callout">
            <div><span>LOCAL DEMO DATA</span><p>This empty ERPNext site needs a Customer and Item before a Sales Order can exist.</p></div>
            <Button type="button" variant="outline" :loading="preparingDemo" @click="prepareDemo">Prepare demo data</Button>
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

          <div class="form-section-title compact"><span>02</span><div><strong>Pick line</strong><small>One line for the first operational slice</small></div></div>
          <label>
            Item
            <select v-model="form.itemCode" required>
              <option disabled value="">Select item</option>
              <option v-for="item in options.items" :key="item.name" :value="item.name">
                {{ item.item_name || item.name }} · {{ item.name }}
              </option>
            </select>
          </label>
          <div class="inline-fields">
            <label>Quantity<input v-model.number="form.quantity" type="number" min="1" step="1" required /></label>
            <label>Rate<input v-model.number="form.rate" type="number" min="0" step="0.01" required /></label>
          </div>
          <label>
            Pick warehouse / shelf hierarchy
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
        <p>This screen creates only a <strong>draft Sales Order</strong>. The accompanying WMS task is a local prototype record until the custom Frappe workflow API is installed.</p>
        <ol>
          <li>ERPNext validates customer, item, company and permission.</li>
          <li>The operator self-claims the derived pick task.</li>
          <li>Any short pick stops at QA before mock dispatch.</li>
        </ol>
      </aside>
    </div>
  </section>
</template>
