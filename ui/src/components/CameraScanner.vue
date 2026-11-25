<script setup lang="ts">
import { nextTick, onBeforeUnmount, ref } from 'vue'
import { Button } from 'frappe-ui'

type Detector = { detect: (source: HTMLVideoElement) => Promise<Array<{ rawValue: string }>> }
type DetectorConstructor = new (options?: { formats?: string[] }) => Detector

const emit = defineEmits<{ detected: [value: string]; close: [] }>()

const video = ref<HTMLVideoElement>()
const started = ref(false)
const error = ref('')
const manualValue = ref('')
let stream: MediaStream | undefined
let timer: number | undefined

function detectorConstructor(): DetectorConstructor | undefined {
  return (window as unknown as { BarcodeDetector?: DetectorConstructor }).BarcodeDetector
}

function stop() {
  if (timer) window.clearInterval(timer)
  timer = undefined
  stream?.getTracks().forEach((track) => track.stop())
  stream = undefined
  started.value = false
}

async function start() {
  error.value = ''
  try {
    stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: { ideal: 'environment' } }, audio: false })
    started.value = true
    await nextTick()
    if (video.value) video.value.srcObject = stream

    const BarcodeDetector = detectorConstructor()
    if (!BarcodeDetector) {
      error.value = 'This browser has no BarcodeDetector support. Use the scanner input below or scan with a compatible device.'
      return
    }
    const detector = new BarcodeDetector({ formats: ['code_128', 'ean_13', 'ean_8', 'qr_code'] })
    timer = window.setInterval(async () => {
      if (!video.value || video.value.readyState < HTMLMediaElement.HAVE_CURRENT_DATA) return
      const codes = await detector.detect(video.value).catch(() => [])
      if (codes[0]?.rawValue) {
        emit('detected', codes[0].rawValue)
        stop()
      }
    }, 700)
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : 'Camera access was not granted.'
  }
}

function submitManual() {
  if (!manualValue.value.trim()) return
  emit('detected', manualValue.value.trim())
  stop()
}

function close() {
  stop()
  emit('close')
}

onBeforeUnmount(stop)
</script>

<template>
  <div class="scanner-backdrop" role="dialog" aria-modal="true" aria-labelledby="scanner-title">
    <section class="scanner-modal">
      <div class="modal-heading"><div><p class="eyebrow">Camera scanner</p><h2 id="scanner-title">Confirm item barcode</h2></div><button class="icon-button" aria-label="Close scanner" @click="close">×</button></div>
      <div class="camera-frame"><video ref="video" autoplay playsinline muted></video><div v-if="!started" class="camera-empty">Camera is off</div><div class="scan-corners" aria-hidden="true"></div></div>
      <p v-if="error" class="scanner-error">{{ error }}</p>
      <Button v-if="!started" class="primary-button" variant="solid" @click="start">Open camera</Button>
      <div class="manual-scan"><label>Scanner fallback<input v-model="manualValue" placeholder="Type or paste barcode" @keyup.enter="submitManual" /></label><Button variant="outline" @click="submitManual">Confirm</Button></div>
    </section>
  </div>
</template>
