import { ref } from 'vue'

/** Busy, error and success state for an admin screen; `guard` runs one action at a time. */
export function useGuard() {
  const busy = ref(false)
  const error = ref('')
  const success = ref('')

  async function guard(action: () => Promise<void>, done: string | (() => string) = '') {
    busy.value = true
    error.value = ''
    success.value = ''
    try {
      await action()
      success.value = typeof done === 'function' ? done() : done
    } catch (cause) {
      error.value = cause instanceof Error ? cause.message : 'The request failed.'
    } finally {
      busy.value = false
    }
  }

  return { busy, error, success, guard }
}
