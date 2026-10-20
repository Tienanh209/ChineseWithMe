<script setup lang="ts">
import { onMounted, onUnmounted, ref, watchEffect } from 'vue'
import { useI18n } from 'vue-i18n'
import { RouterView } from 'vue-router'
import AppHeader from '@/components/AppHeader.vue'
import AppNav from '@/components/AppNav.vue'
import VerifyBanner from '@/components/VerifyBanner.vue'
import { usePrefsStore } from '@/stores/prefs'
import { useSessionStore } from '@/stores/session'

const prefs = usePrefsStore()
const session = useSessionStore()
const { locale } = useI18n()

const prefersDark = ref(false)
const media = window.matchMedia?.('(prefers-color-scheme: dark)')
const onMediaChange = (e: MediaQueryListEvent) => (prefersDark.value = e.matches)

onMounted(() => {
  prefersDark.value = media?.matches ?? false
  media?.addEventListener('change', onMediaChange)
  // Not signed in or API down: keep local preferences.
  session.ensureLoaded().catch(() => {})
})
onUnmounted(() => media?.removeEventListener('change', onMediaChange))

watchEffect(() => {
  locale.value = prefs.lang
  document.documentElement.lang = prefs.lang
  const dark = prefs.theme === 'dark' || (prefs.theme === 'system' && prefersDark.value)
  document.documentElement.classList.toggle('dark', dark)
})
</script>

<template>
  <AppHeader />
  <VerifyBanner />
  <AppNav />
  <main class="mx-auto max-w-3xl px-4 pt-4 pb-24 sm:pb-8">
    <RouterView />
  </main>
</template>
