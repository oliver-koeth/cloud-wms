<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { Button } from 'frappe-ui'
import { deleteRecord, getAdminOptions, getCustomer, listCustomers, saveCustomer } from '../lib/erpnext'
import type { AddressInput, AdminOptions, CustomerDetail, CustomerSummary } from '../types'

const emptyAddress = (): AddressInput => ({ address_line1: '', address_line2: '', city: '', pincode: '', country: '' })
const blank = () => ({
  name: '',
  customer_name: '',
  customer_type: 'Company',
  customer_group: '',
  territory: '',
  email_id: '',
  mobile_no: '',
  disabled: false,
  address: emptyAddress(),
})

const options = ref<AdminOptions>()
const rows = ref<CustomerSummary[]>([])
const search = ref('')
const includeDisabled = ref(false)
const form = ref(blank())
const current = ref<CustomerDetail>()
const busy = ref(false)
const error = ref('')
const success = ref('')

async function guard(action: () => Promise<void>, done = '') {
  busy.value = true
  error.value = ''
  success.value = ''
  try {
    await action()
    success.value = done
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : 'The request failed.'
  } finally {
    busy.value = false
  }
}

const load = () => guard(async () => { rows.value = await listCustomers(search.value.trim(), includeDisabled.value) })

function fill(detail?: CustomerDetail) {
  current.value = detail
  form.value = detail
    ? { ...detail, email_id: detail.email_id ?? '', mobile_no: detail.mobile_no ?? '', customer_group: detail.customer_group ?? '', territory: detail.territory ?? '', disabled: !!detail.disabled, address: { ...emptyAddress(), ...detail.address } }
    : { ...blank(), customer_group: options.value?.customer_groups[0] ?? '', territory: options.value?.territories[0] ?? '' }
}

const open = (name: string) => guard(async () => fill(await getCustomer(name)))

async function save() {
  const address = form.value.address
  const hasAddress = Object.values(address).some((value) => (value ?? '').trim())
  if (hasAddress && !(address.address_line1 && address.city && address.country)) {
    error.value = 'An address needs at least a street, city and country.'
    return
  }
  await guard(async () => {
    const saved = await saveCustomer({
      name: current.value?.name,
      customer_name: form.value.customer_name.trim(),
      customer_type: form.value.customer_type,
      customer_group: form.value.customer_group || undefined,
      territory: form.value.territory || undefined,
      email_id: form.value.email_id.trim(),
      mobile_no: form.value.mobile_no.trim(),
      disabled: Number(form.value.disabled),
      address: hasAddress ? address : undefined,
      modified: current.value?.modified,
    })
    fill(saved)
    rows.value = await listCustomers(search.value.trim(), includeDisabled.value)
  }, 'Customer saved in ERPNext.')
}

async function remove() {
  const name = current.value?.name
  if (!name || !confirm(`Delete customer ${name}? Customers with orders can only be disabled.`)) return
  await guard(async () => {
    await deleteRecord('Customer', name)
    fill()
    rows.value = await listCustomers(search.value.trim(), includeDisabled.value)
  }, `${name} deleted.`)
}

onMounted(async () => {
  await guard(async () => { options.value = await getAdminOptions() })
  fill()
  await load()
})
</script>

<template>
  <section class="screen-grid">
    <div class="screen-header">
      <div><p class="eyebrow">Admin / Master data</p><h1>Customers</h1><p>ERPNext Customers with their primary contact and address.</p></div>
      <Button class="primary-button" variant="solid" :disabled="busy" @click="fill()">New customer</Button>
    </div>
    <div class="admin-layout">
      <section class="surface-card admin-list">
        <form class="admin-search" @submit.prevent="load">
          <input v-model="search" type="search" placeholder="Search name, email…" />
          <label class="check"><input v-model="includeDisabled" type="checkbox" @change="load" /> Disabled</label>
        </form>
        <button v-for="row in rows" :key="row.name" class="admin-row" :class="{ active: current?.name === row.name, disabled: row.disabled }" @click="open(row.name)">
          <strong>{{ row.customer_name }}</strong>
          <small>{{ row.email_id || row.customer_group || row.name }}<template v-if="row.disabled"> · disabled</template></small>
        </button>
        <p v-if="!rows.length" class="muted admin-empty">No customers found.</p>
      </section>

      <form class="surface-card admin-form" @submit.prevent="save">
        <p class="eyebrow">{{ current ? current.name : 'New customer' }}</p>
        <p v-if="current?.open_orders" class="muted">{{ current.open_orders }} open Sales Order{{ current.open_orders === 1 ? '' : 's' }}.</p>
        <label>Name<input v-model="form.customer_name" required maxlength="140" /></label>
        <div class="inline-fields">
          <label>Type<select v-model="form.customer_type"><option>Company</option><option>Individual</option><option>Partnership</option></select></label>
          <label>Group<select v-model="form.customer_group"><option v-for="group in options?.customer_groups" :key="group">{{ group }}</option></select></label>
        </div>
        <label>Territory<select v-model="form.territory"><option v-for="territory in options?.territories" :key="territory">{{ territory }}</option></select></label>
        <div class="inline-fields">
          <label>Email<input v-model="form.email_id" type="email" /></label>
          <label>Mobile<input v-model="form.mobile_no" type="tel" /></label>
        </div>
        <div class="form-section-title compact"><span>⌂</span><div><strong>Primary address</strong><small>Optional; street, city and country are required when given</small></div></div>
        <label>Street<input v-model="form.address.address_line1" /></label>
        <label>Street (line 2)<input v-model="form.address.address_line2" /></label>
        <div class="inline-fields">
          <label>Postcode<input v-model="form.address.pincode" /></label>
          <label>City<input v-model="form.address.city" /></label>
        </div>
        <label>Country<select v-model="form.address.country"><option value=""></option><option v-for="country in options?.countries" :key="country">{{ country }}</option></select></label>
        <label class="check"><input v-model="form.disabled" type="checkbox" /> Disabled (hidden from new orders)</label>
        <p v-if="error" class="form-error" role="alert">{{ error }}</p>
        <p v-if="success" class="form-success" role="status">{{ success }}</p>
        <div class="admin-actions">
          <Button class="primary-button" variant="solid" type="submit" :loading="busy">Save</Button>
          <Button v-if="current" variant="outline" type="button" :disabled="busy" @click="remove">Delete</Button>
        </div>
      </form>
    </div>
  </section>
</template>
