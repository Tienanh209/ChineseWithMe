<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { RouterLink, useRoute } from 'vue-router'
import { useSessionStore } from '@/stores/session'

const { t } = useI18n()
const route = useRoute()
const session = useSessionStore()
const state = ref<'working' | 'ok' | 'failed'>('working')

onMounted(async () => {
  const token = route.query.token
  if (typeof token !== 'string' || !token) {
    state.value = 'failed'
    return
  }
  try {
    await session.verifyEmail(token)
    state.value = 'ok'
  } catch {
    state.value = 'failed'
  }
})
</script>

<template>
  <section class="mx-auto max-w-md space-y-4">
    <h1 class="text-2xl font-bold">{{ t('verify.title') }}</h1>
    <p v-if="state === 'working'" role="status">{{ t('verify.working') }}</p>
    <p v-else-if="state === 'ok'" role="status">{{ t('verify.success') }}</p>
    <p v-else role="alert" class="text-brand-600">{{ t('verify.failure') }}</p>
    <RouterLink
      v-if="state !== 'working'"
      :to="session.me ? '/' : { name: 'login' }"
      class="inline-flex min-h-11 items-center underline"
    >
      {{ session.me ? t('verify.continue') : t('auth.signInButton') }}
    </RouterLink>
  </section>
</template>
