<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { Button } from 'frappe-ui'
import { deleteRecord, getAdminOptions, listLocations, saveLocation } from '../lib/erpnext'
import type { AdminOptions, LocationRow } from '../types'

const blank = (parent = '') => ({ warehouse_name: '', parent_warehouse: parent, is_group: false, barcode: '', disabled: false, company: '' })

const options = ref<AdminOptions>()
const rows = ref<LocationRow[]>([])
const form = ref(blank())
const current = ref<LocationRow>()
const busy = ref(false)
const error = ref('')
const success = ref('')

// A location cannot move under itself or one of its own descendants.
const groups = computed(() => {
  const self = current.value
  return rows.value.filter((row) => row.is_group && !(self && row.lft >= self.lft && row.rgt <= self.rgt))
})

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

const reload = async () => { rows.value = await listLocations() }

function fill(row?: LocationRow, parent = '') {
  current.value = row
  form.value = row
    ? { warehouse_name: row.warehouse_name, parent_warehouse: row.parent_warehouse ?? '', is_group: !!row.is_group, barcode: row.barcode ?? '', disabled: !!row.disabled, company: row.company }
    : { ...blank(parent), company: options.value?.default_company ?? '' }
}

const save = () =>
  guard(async () => {
    const saved = await saveLocation({
      name: current.value?.name,
      warehouse_name: form.value.warehouse_name.trim(),
      parent_warehouse: form.value.parent_warehouse || null,
      is_group: Number(form.value.is_group),
      barcode: form.value.is_group ? null : form.value.barcode.trim() || null,
      disabled: Number(form.value.disabled),
      company: form.value.parent_warehouse ? undefined : form.value.company || undefined,
      modified: current.value?.modified,
    })
    await reload()
    fill(rows.value.find((row) => row.name === saved.name) ?? saved)
  }, 'Location saved in ERPNext.')

async function remove() {
  const name = current.value?.name
  if (!name || !confirm(`Delete ${name}? Locations with stock, history or children cannot be deleted.`)) return
  await guard(async () => {
    await deleteRecord('Warehouse', name)
    fill()
    await reload()
  }, `${name} deleted.`)
}

onMounted(async () => {
  await guard(async () => {
    options.value = await getAdminOptions()
    await reload()
  })
  fill()
})
</script>

<template>
  <section class="screen-grid">
    <div class="screen-header">
      <div><p class="eyebrow">Admin / Master data</p><h1>Locations</h1><p>ERPNext Warehouses as a tree. Groups are zones and aisles; bins hold stock and carry the barcode pickers scan.</p></div>
      <Button class="primary-button" variant="solid" :disabled="busy" @click="fill()">New location</Button>
    </div>
    <div class="admin-layout">
      <section class="surface-card admin-list">
        <button v-for="row in rows" :key="row.name" class="admin-row tree-row" :class="{ active: current?.name === row.name, disabled: row.disabled }" :style="{ paddingLeft: `${16 + row.depth * 18}px` }" @click="fill(row)">
          <strong>{{ row.is_group ? '▸' : '·' }} {{ row.warehouse_name }}<code v-if="row.barcode">{{ row.barcode }}</code></strong>
          <small>{{ row.is_group ? 'Group' : 'Bin' }} · {{ row.on_hand }} on hand<template v-if="row.disabled"> · disabled</template></small>
        </button>
        <p v-if="!rows.length" class="muted admin-empty">No locations yet.</p>
      </section>

      <form class="surface-card admin-form" @submit.prevent="save">
        <p class="eyebrow">{{ current ? current.name : 'New location' }}</p>
        <label>Name<input v-model="form.warehouse_name" required maxlength="140" placeholder="e.g. MAIN-A-02-01" /></label>
        <label>Parent group<select v-model="form.parent_warehouse"><option value="">(top level)</option><option v-for="group in groups" :key="group.name" :value="group.name">{{ '— '.repeat(group.depth) }}{{ group.warehouse_name }}</option></select></label>
        <label v-if="!form.parent_warehouse && !current">Company<select v-model="form.company"><option v-for="company in options?.companies" :key="company">{{ company }}</option></select></label>
        <label class="check"><input v-model="form.is_group" type="checkbox" /> Group (contains other locations, holds no stock)</label>
        <label v-if="!form.is_group">Location barcode<input v-model="form.barcode" maxlength="140" placeholder="e.g. LOC-MAIN-A-02-01" /></label>
        <label class="check"><input v-model="form.disabled" type="checkbox" /> Disabled</label>
        <p v-if="error" class="form-error" role="alert">{{ error }}</p>
        <p v-if="success" class="form-success" role="status">{{ success }}</p>
        <div class="admin-actions">
          <Button class="primary-button" variant="solid" type="submit" :loading="busy">Save</Button>
          <Button v-if="current?.is_group" variant="outline" type="button" :disabled="busy" @click="fill(undefined, current.name)">Add child</Button>
          <Button v-if="current" variant="outline" type="button" :disabled="busy" @click="remove">Delete</Button>
        </div>
      </form>
    </div>
  </section>
</template>
