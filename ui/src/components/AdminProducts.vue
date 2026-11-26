<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { Button } from 'frappe-ui'
import { deleteRecord, getAdminOptions, getItem, listItems, saveItem } from '../lib/erpnext'
import type { AdminOptions, ItemDetail, ItemSummary } from '../types'

const blank = () => ({
  item_code: '',
  item_name: '',
  item_group: '',
  stock_uom: 'Nos',
  is_stock_item: true,
  description: '',
  barcodes: '',
  selling_rate: null as number | null,
  disabled: false,
})

const options = ref<AdminOptions>()
const rows = ref<ItemSummary[]>([])
const search = ref('')
const includeDisabled = ref(false)
const form = ref(blank())
const current = ref<ItemDetail>()
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

const reload = async () => { rows.value = await listItems(search.value.trim(), includeDisabled.value) }
const load = () => guard(reload)

function fill(detail?: ItemDetail) {
  current.value = detail
  form.value = detail
    ? {
        item_code: detail.name,
        item_name: detail.item_name,
        item_group: detail.item_group,
        stock_uom: detail.stock_uom,
        is_stock_item: !!detail.is_stock_item,
        description: detail.description ?? '',
        barcodes: detail.barcodes.join('\n'),
        selling_rate: detail.selling_rate,
        disabled: !!detail.disabled,
      }
    : { ...blank(), item_group: options.value?.item_groups.find((group) => group !== 'All Item Groups') ?? 'All Item Groups' }
}

const open = (name: string) => guard(async () => fill(await getItem(name)))

const save = () =>
  guard(async () => {
    const saved = await saveItem({
      name: current.value?.name,
      item_code: current.value ? undefined : form.value.item_code.trim(),
      item_name: form.value.item_name.trim(),
      item_group: form.value.item_group,
      stock_uom: form.value.stock_uom,
      is_stock_item: Number(form.value.is_stock_item),
      description: form.value.description.trim(),
      disabled: Number(form.value.disabled),
      barcodes: form.value.barcodes.split(/[\s,]+/).filter(Boolean),
      selling_rate: typeof form.value.selling_rate === 'number' ? form.value.selling_rate : null,
      modified: current.value?.modified,
    })
    fill(saved)
    await reload()
  }, 'Product saved in ERPNext.')

async function remove() {
  const name = current.value?.name
  if (!name || !confirm(`Delete product ${name}? Products with stock or orders can only be disabled.`)) return
  await guard(async () => {
    await deleteRecord('Item', name)
    fill()
    await reload()
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
      <div><p class="eyebrow">Admin / Master data</p><h1>Products</h1><p>ERPNext Items with the barcodes pickers scan and the selling rate used on orders.</p></div>
      <Button class="primary-button" variant="solid" :disabled="busy" @click="fill()">New product</Button>
    </div>
    <div class="admin-layout">
      <section class="surface-card admin-list">
        <form class="admin-search" @submit.prevent="load">
          <input v-model="search" type="search" placeholder="Search code, name…" />
          <label class="check"><input v-model="includeDisabled" type="checkbox" @change="load" /> Disabled</label>
        </form>
        <button v-for="row in rows" :key="row.name" class="admin-row" :class="{ active: current?.name === row.name, disabled: row.disabled }" @click="open(row.name)">
          <strong>{{ row.item_name }} <code>{{ row.name }}</code></strong>
          <small>{{ row.on_hand }} {{ row.stock_uom }} on hand · {{ row.barcodes.length ? row.barcodes.join(', ') : 'no barcode' }}<template v-if="row.disabled"> · disabled</template></small>
        </button>
        <p v-if="!rows.length" class="muted admin-empty">No products found.</p>
      </section>

      <form class="surface-card admin-form" @submit.prevent="save">
        <p class="eyebrow">{{ current ? current.name : 'New product' }}</p>
        <label v-if="!current">Item code<input v-model="form.item_code" required maxlength="140" placeholder="e.g. SKU-1001" /></label>
        <label>Name<input v-model="form.item_name" required maxlength="140" /></label>
        <div class="inline-fields">
          <label>Group<select v-model="form.item_group"><option v-for="group in options?.item_groups" :key="group">{{ group }}</option></select></label>
          <label>Stock unit<select v-model="form.stock_uom"><option v-for="uom in options?.uoms" :key="uom">{{ uom }}</option></select></label>
        </div>
        <label>Barcodes <small>(one per line; any of them confirms a pick)</small><textarea v-model="form.barcodes" placeholder="4006381333931"></textarea></label>
        <label>Selling rate <small>({{ current?.selling_price_list || options?.selling_price_list || 'default price list' }})</small><input v-model.number="form.selling_rate" type="number" min="0" step="0.01" /></label>
        <label>Description<textarea v-model="form.description"></textarea></label>
        <label class="check"><input v-model="form.is_stock_item" type="checkbox" /> Keep stock (pickable)</label>
        <label class="check"><input v-model="form.disabled" type="checkbox" /> Disabled</label>
        <div v-if="current?.stock.length" class="admin-stock">
          <p class="eyebrow">Stock by location</p>
          <p v-for="bin in current.stock" :key="bin.warehouse"><span>{{ bin.warehouse }}</span><strong>{{ bin.actual_qty }}</strong><small v-if="bin.reserved_stock">{{ bin.reserved_stock }} reserved</small></p>
        </div>
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
