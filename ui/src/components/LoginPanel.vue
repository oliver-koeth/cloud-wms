<script setup lang="ts">
import { ref } from 'vue'
import { Button } from 'frappe-ui'
import { login } from '../lib/erpnext'
import type { SessionUser } from '../types'

const emit = defineEmits<{ authenticated: [user: SessionUser] }>()

const username = ref('Administrator')
const password = ref('admin')
const loading = ref(false)
const error = ref('')

async function submit() {
  loading.value = true
  error.value = ''
  try {
    emit('authenticated', await login(username.value, password.value))
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : 'Could not sign in to ERPNext.'
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <main class="login-shell">
    <section class="login-panel" aria-labelledby="login-title">
      <div class="brand-lockup"><span class="brand-mark">›</span> CLOUD WMS</div>
      <p class="eyebrow">ERPNext-connected warehouse workspace</p>
      <h1 id="login-title">Sign in for operations.</h1>
      <p class="login-copy">Use an existing ERPNext user. Access is governed by that user’s ERPNext permissions.</p>

      <form class="login-form" @submit.prevent="submit">
        <label>
          ERPNext user
          <input v-model="username" autocomplete="username" required />
        </label>
        <label>
          Password
          <input v-model="password" type="password" autocomplete="current-password" required />
        </label>
        <p v-if="error" class="form-error" role="alert">{{ error }}</p>
        <Button class="primary-button" variant="solid" :loading="loading" type="submit">Sign in</Button>
      </form>
      <p class="login-note">Local evaluation environment · ERPNext session authentication</p>
    </section>
    <aside class="login-aside" aria-label="Operational workflow summary">
      <span class="signal-label">SYSTEM ONLINE</span>
      <h2>Make work visible.<br /><em>Keep decisions human.</em></h2>
      <div class="workflow-rail">
        <span>01</span><div><strong>Order intake</strong><small>Submitted Sales Order in ERPNext</small></div>
        <span>02</span><div><strong>Pick &amp; confirm</strong><small>Camera-assisted item validation</small></div>
        <span>03</span><div><strong>QA &amp; dispatch</strong><small>Delivery Note submitted in ERPNext</small></div>
      </div>
    </aside>
  </main>
</template>
