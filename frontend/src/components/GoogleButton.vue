<script setup lang="ts">
/**
 * The official Google button (Google Identity Services). Emits the signed ID token as
 * `credential`; the caller decides what to do with it (sign in, link, confirm deletion).
 * Renders nothing when the server has no Google client id or the script is blocked.
 */
import { nextTick, onMounted, onUnmounted, ref } from 'vue'
import { loadGoogleIdentity } from '@/lib/google'
import { usePrefsStore } from '@/stores/prefs'
import { useSessionStore } from '@/stores/session'

const props = defineProps<{
  text?: 'signin_with' | 'signup_with' | 'continue_with'
  oneTap?: boolean
}>()
const emit = defineEmits<{ credential: [value: string]; unavailable: [] }>()

const session = useSessionStore()
const prefs = usePrefsStore()
const host = ref<HTMLElement | null>(null)
const ready = ref(false)

onMounted(async () => {
  await session.loadConfig()
  const clientId = session.googleClientId
  if (!clientId) return
  try {
    const id = await loadGoogleIdentity()
    id.initialize({
      client_id: clientId,
      callback: (response) => emit('credential', response.credential),
      auto_select: false,
      cancel_on_tap_outside: true,
    })
    ready.value = true
    await nextTick()
    const el = host.value
    if (!el) return
    id.renderButton(el, {
      type: 'standard',
      theme: document.documentElement.classList.contains('dark') ? 'filled_black' : 'outline',
      size: 'large',
      shape: 'pill',
      text: props.text ?? 'continue_with',
      locale: prefs.lang,
      width: Math.max(200, Math.min(400, el.offsetWidth)),
    })
    if (props.oneTap) id.prompt()
  } catch {
    emit('unavailable')
  }
})

onUnmounted(() => window.google?.accounts.id.cancel())
</script>

<template>
  <div v-show="ready" ref="host" class="flex min-h-11 w-full justify-center" />
</template>
