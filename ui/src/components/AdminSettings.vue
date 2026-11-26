<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { getSettings } from '../lib/erpnext'
import { useGuard } from '../lib/useGuard'
import type { WmsSettings } from '../types'

const { error, guard } = useGuard()
const settings = ref<WmsSettings>()

const label = (key: string) => key.replace(/_/g, ' ').replace(/^./, (char) => char.toUpperCase())
const value = (raw: string | number | null | undefined) => (raw === 1 ? 'Yes' : raw === 0 ? 'No' : raw || '—')
const drifted = (key: string) => {
  const expected = settings.value?.enforced[key]
  return expected !== undefined && settings.value?.stock[key] !== expected
}

onMounted(() =>
  guard(async () => {
    settings.value = await getSettings()
  }),
)
</script>

<template>
  <section class="screen-grid">
    <div class="screen-header">
      <div><p class="eyebrow">Admin / System</p><h1>Settings</h1><p>Read-only view of the ERPNext settings the WMS depends on. Change them in ERPNext Desk; the values marked “WMS” are re-applied by <code>bench migrate</code>.</p></div>
    </div>
    <p v-if="error" class="form-error" role="alert">{{ error }}</p>
    <div v-if="settings" class="settings-grid">
      <section class="surface-card admin-form">
        <p class="eyebrow">Stock Settings</p>
        <div class="admin-lines">
          <p v-for="(raw, key) in settings.stock" :key="key">
            <span>{{ label(String(key)) }}<span v-if="String(key) in settings.enforced" class="status-chip" :class="drifted(String(key)) ? 'chip-warn' : 'chip-ok'">WMS</span></span>
            <strong>{{ value(raw) }}</strong>
            <small v-if="drifted(String(key))">The WMS expects {{ value(settings.enforced[String(key)]) }}. Run <code>bench migrate</code> to restore it.</small>
          </p>
        </div>
      </section>
      <section class="surface-card admin-form">
        <p class="eyebrow">Selling Settings</p>
        <div class="admin-lines">
          <p v-for="(raw, key) in settings.selling" :key="key"><span>{{ label(String(key)) }}</span><strong>{{ value(raw) }}</strong></p>
        </div>
      </section>
      <section class="surface-card admin-form">
        <p class="eyebrow">Companies</p>
        <div class="admin-lines">
          <p v-for="company in settings.companies" :key="company.name">
            <span>{{ company.name }} <code>{{ company.abbr }}</code><span v-if="company.name === settings.default_company" class="status-chip chip-ok">Default</span></span>
            <strong>{{ company.default_currency || '—' }}</strong>
            <small>{{ company.country || 'No country set' }}</small>
          </p>
          <p v-if="!settings.companies.length" class="muted">No company yet. Run the ERPNext setup wizard.</p>
        </div>
      </section>
      <section class="surface-card admin-form">
        <p class="eyebrow">Versions</p>
        <div class="admin-lines">
          <p v-for="(version, app) in settings.versions" :key="app"><span>{{ app }}</span><strong>{{ version || 'unknown' }}</strong></p>
        </div>
      </section>
    </div>
  </section>
</template>
