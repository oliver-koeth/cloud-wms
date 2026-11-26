<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { Button } from 'frappe-ui'
import { listEvents } from '../lib/erpnext'
import { useGuard } from '../lib/useGuard'
import type { EventFilters, TaskEvent } from '../types'

const { busy, error, guard } = useGuard()
const filters = ref<EventFilters>({})
const events = ref<TaskEvent[]>([])
const eventTypes = ref<string[]>([])
const limit = ref(0)
const open = ref<string>()

const load = () =>
  guard(async () => {
    const trimmed = Object.fromEntries(
      Object.entries(filters.value).map(([key, value]) => [key, typeof value === 'string' ? value.trim() : value]),
    ) as EventFilters
    const log = await listEvents(trimmed)
    events.value = log.events
    eventTypes.value = log.event_types
    limit.value = log.limit
  })

function clear() {
  filters.value = {}
  void load()
}

function follow(key: keyof EventFilters, value: string | null) {
  if (!value) return
  filters.value = { [key]: value }
  void load()
}

function details(event: TaskEvent) {
  if (!event.details) return ''
  try {
    return JSON.stringify(JSON.parse(event.details), null, 2)
  } catch {
    return event.details
  }
}

onMounted(load)
</script>

<template>
  <section class="screen-grid">
    <div class="screen-header">
      <div><p class="eyebrow">Admin / Audit</p><h1>Audit log</h1><p>Append-only WMS Task Events: every claim, scan, shortage, dispatch, cancellation and master-data change, newest first.</p></div>
    </div>
    <form class="surface-card audit-filters" @submit.prevent="load">
      <label>Event<select v-model="filters.event_type"><option :value="undefined">Any event</option><option v-for="type in eventTypes" :key="type">{{ type }}</option></select></label>
      <label>Actor<input v-model="filters.actor" placeholder="user@example.com" /></label>
      <label>Sales Order<input v-model="filters.sales_order" /></label>
      <label>Pick List<input v-model="filters.pick_list" /></label>
      <label>Delivery Note<input v-model="filters.delivery_note" /></label>
      <label>Correlation id<input v-model="filters.correlation_id" /></label>
      <label>From<input v-model="filters.from_date" type="date" /></label>
      <label>To<input v-model="filters.to_date" type="date" /></label>
      <div class="admin-actions"><Button class="primary-button" variant="solid" type="submit" :loading="busy">Filter</Button><Button variant="outline" type="button" :disabled="busy" @click="clear">Clear</Button></div>
    </form>
    <p v-if="error" class="form-error" role="alert">{{ error }}</p>
    <section class="surface-card admin-list audit-list">
      <article v-for="event in events" :key="event.name" class="admin-row" :class="{ active: open === event.name }">
        <button type="button" class="audit-toggle" :aria-expanded="open === event.name" @click="open = open === event.name ? undefined : event.name">
          <strong>{{ event.event_type }}<span class="status-chip">{{ event.creation.slice(0, 19) }}</span></strong>
          <small>{{ event.actor }}<template v-if="event.item_code"> · {{ event.item_code }}</template><template v-if="event.qty !== null"> × {{ event.qty }}</template><template v-if="event.warehouse"> @ {{ event.warehouse }}</template><template v-if="event.reason"> · “{{ event.reason }}”</template></small>
        </button>
        <small class="audit-links">
          <button v-if="event.sales_order" type="button" class="link-button" @click="follow('sales_order', event.sales_order)">{{ event.sales_order }}</button>
          <button v-if="event.pick_list" type="button" class="link-button" @click="follow('pick_list', event.pick_list)">{{ event.pick_list }}</button>
          <button v-if="event.delivery_note" type="button" class="link-button" @click="follow('delivery_note', event.delivery_note)">{{ event.delivery_note }}</button>
          <button v-if="event.correlation_id" type="button" class="link-button" @click="follow('correlation_id', event.correlation_id)">ref {{ event.correlation_id.slice(0, 8) }}</button>
        </small>
        <pre v-if="open === event.name && details(event)" class="audit-details">{{ details(event) }}</pre>
      </article>
      <p v-if="!events.length" class="muted admin-empty">No events match these filters.</p>
      <p v-else-if="events.length >= limit" class="muted admin-empty">Showing the newest {{ limit }} events. Narrow the filters to see older ones.</p>
    </section>
  </section>
</template>
