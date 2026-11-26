<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { Button } from 'frappe-ui'
import { cancelDeliveryNote, cancelPickList, getDeliveryNote, getPickList, listDeliveryNotes, listPickLists } from '../lib/erpnext'
import { useGuard } from '../lib/useGuard'
import type { DeliveryNoteDetail, DeliveryNoteSummary, PickListDetail, PickListSummary } from '../types'

type Kind = 'pick' | 'note'

const statuses: Record<Kind, string[]> = {
  pick: ['Draft', 'Open', 'Partly Delivered', 'Completed', 'Cancelled'],
  note: ['Draft', 'To Bill', 'Partially Billed', 'Completed', 'Return', 'Return Issued', 'Cancelled', 'Closed'],
}

const { busy, error, success, guard } = useGuard()
const kind = ref<Kind>('pick')
const search = ref('')
const status = ref('')
const picks = ref<PickListSummary[]>([])
const notes = ref<DeliveryNoteSummary[]>([])
const pick = ref<PickListDetail>()
const note = ref<DeliveryNoteDetail>()
const reason = ref('')

const current = computed(() => (kind.value === 'pick' ? pick.value : note.value))
const docChip = (docstatus: number) => (docstatus === 2 ? 'chip-off' : docstatus === 1 ? 'chip-ok' : 'chip-warn')

async function reload() {
  if (kind.value === 'pick') picks.value = await listPickLists(search.value.trim(), status.value)
  else notes.value = await listDeliveryNotes(search.value.trim(), status.value)
}

function switchTo(next: Kind) {
  kind.value = next
  status.value = ''
  pick.value = undefined
  note.value = undefined
  reason.value = ''
  void guard(reload)
}

function open(next: Kind, name: string) {
  reason.value = ''
  return guard(async () => {
    if (kind.value !== next) {
      kind.value = next
      status.value = ''
      search.value = ''
      await reload()
    }
    if (next === 'pick') pick.value = await getPickList(name)
    else note.value = await getDeliveryNote(name)
  })
}

async function cancel() {
  const doc = current.value
  if (!doc) return
  const what = kind.value === 'pick' ? 'Pick List' : 'Delivery Note'
  const effect =
    kind.value === 'pick'
      ? 'Its stock reservations are cancelled and the Sales Order returns to the pick queue.'
      : 'ERPNext reverses its stock ledger entries and the delivered quantities on the Sales Order.'
  if (!confirm(`Cancel ${what} ${doc.name}? ${effect}`)) return
  await guard(async () => {
    const why = reason.value.trim() || undefined
    if (kind.value === 'pick') pick.value = await cancelPickList(doc.name, doc.modified, why)
    else note.value = await cancelDeliveryNote(doc.name, doc.modified, why)
    reason.value = ''
    await reload()
  }, `${what} ${doc.name} cancelled.`)
}

onMounted(() => guard(reload))
</script>

<template>
  <section class="screen-grid">
    <div class="screen-header">
      <div><p class="eyebrow">Admin / Exceptions</p><h1>Pick Lists &amp; Delivery Notes</h1><p>Read-only views of the ERPNext documents behind each pick and dispatch. Cancel reverses a wrong dispatch: the Delivery Note first, then its Pick List.</p></div>
    </div>
    <div class="admin-tabs" role="tablist">
      <button type="button" role="tab" :aria-selected="kind === 'pick'" :class="{ active: kind === 'pick' }" @click="switchTo('pick')">Pick Lists</button>
      <button type="button" role="tab" :aria-selected="kind === 'note'" :class="{ active: kind === 'note' }" @click="switchTo('note')">Delivery Notes</button>
    </div>
    <div class="admin-layout">
      <section class="surface-card admin-list">
        <form class="admin-search admin-search-wide" @submit.prevent="guard(reload)">
          <input v-model="search" :placeholder="kind === 'pick' ? 'Pick List, customer or Sales Order' : 'Delivery Note, customer or Sales Order'" />
          <select v-model="status" @change="guard(reload)"><option value="">Any status</option><option v-for="option in statuses[kind]" :key="option">{{ option }}</option></select>
          <Button variant="outline" type="submit" :disabled="busy">Search</Button>
        </form>
        <template v-if="kind === 'pick'">
          <button v-for="row in picks" :key="row.name" class="admin-row" :class="{ active: pick?.name === row.name }" @click="open('pick', row.name)">
            <strong>{{ row.name }}<span class="status-chip" :class="docChip(row.docstatus)">{{ row.status }}</span></strong>
            <small>{{ row.customer || '—' }} · {{ row.sales_orders.join(', ') || 'no order' }}</small>
          </button>
          <p v-if="!picks.length" class="muted admin-empty">No Pick Lists match.</p>
        </template>
        <template v-else>
          <button v-for="row in notes" :key="row.name" class="admin-row" :class="{ active: note?.name === row.name }" @click="open('note', row.name)">
            <strong>{{ row.name }}<span v-if="row.is_return" class="status-chip chip-warn">Return</span><span class="status-chip" :class="docChip(row.docstatus)">{{ row.status }}</span></strong>
            <small>{{ row.customer_name || row.customer }} · {{ row.posting_date }} · {{ row.total_qty }} units</small>
            <small>{{ row.sales_orders.join(', ') || 'no order' }}<template v-if="row.pick_lists.length"> · {{ row.pick_lists.join(', ') }}</template></small>
          </button>
          <p v-if="!notes.length" class="muted admin-empty">No Delivery Notes match.</p>
        </template>
      </section>

      <section class="surface-card admin-form">
        <template v-if="kind === 'pick' && pick">
          <p class="eyebrow">Pick List</p>
          <h2>{{ pick.name }} <span class="status-chip" :class="docChip(pick.docstatus)">{{ pick.status }}</span></h2>
          <p class="muted">{{ pick.customer }} · {{ pick.company }} · created by {{ pick.owner }}<template v-if="pick.assignees.length"> · assigned to {{ pick.assignees.join(', ') }}</template></p>
          <p class="muted">Sales Orders: {{ pick.sales_orders.join(', ') || '—' }}</p>
          <div class="admin-lines">
            <p v-for="line in pick.lines" :key="line.row">
              <span><code>{{ line.item_code }}</code> {{ line.item_name }}</span>
              <span>{{ line.picked_qty }} / {{ line.qty }} {{ line.uom }}</span>
              <small>{{ line.warehouse }} · {{ line.sales_order }}<template v-if="line.shortage_state"> · shortage {{ line.shortage_state }}</template></small>
            </p>
          </div>
          <div v-if="pick.delivery_notes.length" class="admin-lines">
            <p v-for="dn in pick.delivery_notes" :key="dn.name"><button type="button" class="link-button" @click="open('note', dn.name)">{{ dn.name }}</button><span class="status-chip" :class="docChip(dn.docstatus)">{{ dn.status }}</span></p>
          </div>
        </template>
        <template v-else-if="kind === 'note' && note">
          <p class="eyebrow">Delivery Note<template v-if="note.is_return"> · return</template></p>
          <h2>{{ note.name }} <span class="status-chip" :class="docChip(note.docstatus)">{{ note.status }}</span></h2>
          <p class="muted">{{ note.customer_name || note.customer }} · {{ note.company }} · posted {{ note.posting_date }} by {{ note.owner }}<template v-if="note.reference"> · ref {{ note.reference }}</template></p>
          <p class="muted">Sales Orders: {{ note.sales_orders.join(', ') || '—' }}</p>
          <div class="admin-lines">
            <p v-for="line in note.lines" :key="line.row">
              <span><code>{{ line.item_code }}</code> {{ line.item_name }}</span>
              <span>{{ line.qty }} {{ line.uom }}</span>
              <small>{{ line.warehouse }} · {{ line.sales_order }}</small>
            </p>
          </div>
          <div v-if="note.pick_lists.length" class="admin-lines">
            <p v-for="name in note.pick_lists" :key="name"><button type="button" class="link-button" @click="open('pick', name)">{{ name }}</button><span>Pick List</span></p>
          </div>
        </template>
        <div v-else class="empty-state"><strong>Select a document.</strong><p>Pick a row on the left to see its lines, linked documents and whether it can be cancelled.</p></div>

        <template v-if="current">
          <div v-if="current.cancel_blocker" class="shortage-callout"><span>CANNOT CANCEL</span><p>{{ current.cancel_blocker.message }} {{ current.cancel_blocker.next_action }}</p></div>
          <template v-else>
            <label>Cancellation reason<textarea v-model="reason" maxlength="500" placeholder="Kept in the audit log"></textarea></label>
            <div class="admin-actions"><Button variant="outline" type="button" :loading="busy" @click="cancel">Cancel {{ kind === 'pick' ? 'Pick List' : 'Delivery Note' }}</Button></div>
          </template>
        </template>
        <p v-if="error" class="form-error" role="alert">{{ error }}</p>
        <p v-if="success" class="form-success" role="status">{{ success }}</p>
      </section>
    </div>
  </section>
</template>
