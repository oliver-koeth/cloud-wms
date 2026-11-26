<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { Button } from 'frappe-ui'
import { createReference, listReference } from '../lib/erpnext'
import { useGuard } from '../lib/useGuard'
import type { ReferenceDoctype, ReferenceList, TreeReference } from '../types'

const doctypes: Array<{ value: ReferenceDoctype; hint: string }> = [
  { value: 'Customer Group', hint: 'Groups customers for pricing and reporting.' },
  { value: 'Territory', hint: 'Sales regions customers belong to.' },
  { value: 'Item Group', hint: 'Product categories.' },
  { value: 'UOM', hint: 'Units of measure. Managed in ERPNext Desk.' },
  { value: 'Price List', hint: 'Selling and buying price lists. Managed in ERPNext Desk.' },
]

const { busy, error, success, guard } = useGuard()
const doctype = ref<ReferenceDoctype>('Customer Group')
const list = ref<ReferenceList>()
const form = ref({ name: '', parent: '', is_group: false })

const groups = computed(() => (list.value?.tree ? list.value.rows.filter((row) => row.is_group) : []))
const columns = computed(() => (list.value && !list.value.tree && list.value.rows[0] ? Object.keys(list.value.rows[0]).filter((key) => key !== 'name') : []))
const hint = computed(() => doctypes.find((entry) => entry.value === doctype.value)?.hint)

const label = (key: string) => key.replace(/_/g, ' ')
const cell = (value: string | number | null) => (value === 1 ? 'yes' : value === 0 ? 'no' : (value ?? '—'))

async function load(next: ReferenceDoctype = doctype.value) {
  doctype.value = next
  form.value = { name: '', parent: '', is_group: false }
  await guard(async () => {
    list.value = await listReference(next)
  })
}

async function create() {
  let created = ''
  await guard(
    async () => {
      const result = await createReference({
        doctype: doctype.value as TreeReference,
        name: form.value.name.trim(),
        parent: form.value.parent || undefined,
        is_group: Number(form.value.is_group),
      })
      created = result.name
      list.value = await listReference(doctype.value)
      form.value = { name: '', parent: form.value.parent, is_group: false }
    },
    () => `${created} created in ERPNext.`,
  )
}

onMounted(() => load())
</script>

<template>
  <section class="screen-grid">
    <div class="screen-header">
      <div><p class="eyebrow">Admin / Master data</p><h1>Reference lists</h1><p>The lookup values Customers and Products point at. Tree lists can be extended here; rename, merge and delete stay in ERPNext Desk.</p></div>
    </div>
    <div class="admin-tabs" role="tablist">
      <button v-for="entry in doctypes" :key="entry.value" type="button" role="tab" :aria-selected="doctype === entry.value" :class="{ active: doctype === entry.value }" @click="load(entry.value)">{{ entry.value }}</button>
    </div>
    <div class="admin-layout">
      <section class="surface-card admin-list">
        <template v-if="list?.tree">
          <div v-for="row in list.rows" :key="row.name" class="admin-row tree-row" :style="{ paddingLeft: `${16 + Number(row.depth) * 18}px` }">
            <strong>{{ row.is_group ? '▸' : '·' }} {{ row.name }}</strong>
            <small>{{ row.is_group ? 'Group' : 'Leaf' }}</small>
          </div>
        </template>
        <template v-else-if="list">
          <div v-for="row in list.rows" :key="row.name" class="admin-row">
            <strong>{{ row.name }}</strong>
            <small><template v-for="(key, index) in columns" :key="key">{{ index ? ' · ' : '' }}{{ label(key) }}: {{ cell(row[key]) }}</template></small>
          </div>
        </template>
        <p v-if="list && !list.rows.length" class="muted admin-empty">No {{ doctype }} records yet.</p>
      </section>

      <form v-if="list?.tree" class="surface-card admin-form" @submit.prevent="create">
        <p class="eyebrow">New {{ doctype }}</p>
        <p class="muted">{{ hint }}</p>
        <label>Name<input v-model="form.name" required maxlength="140" /></label>
        <label>Parent group<select v-model="form.parent"><option value="">(root)</option><option v-for="group in groups" :key="group.name" :value="group.name">{{ '— '.repeat(Number(group.depth)) }}{{ group.name }}</option></select></label>
        <label class="check"><input v-model="form.is_group" type="checkbox" /> Group (can contain other entries)</label>
        <p v-if="error" class="form-error" role="alert">{{ error }}</p>
        <p v-if="success" class="form-success" role="status">{{ success }}</p>
        <div class="admin-actions"><Button class="primary-button" variant="solid" type="submit" :loading="busy">Create</Button></div>
      </form>
      <section v-else class="surface-card admin-form">
        <p class="eyebrow">{{ doctype }}</p>
        <p class="muted">{{ hint }}</p>
        <p v-if="error" class="form-error" role="alert">{{ error }}</p>
      </section>
    </div>
  </section>
</template>
