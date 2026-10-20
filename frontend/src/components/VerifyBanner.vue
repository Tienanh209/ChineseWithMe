<script setup lang="ts">
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { errorText } from '@/lib/errors'
import { useSessionStore } from '@/stores/session'

const { t } = useI18n()
const session = useSessionStore()
const state = ref<'idle' | 'sending' | 'sent'>('idle')
const error = ref<string | null>(null)

async function resend() {
  state.value = 'sending'
  error.value = null
  try {
    await session.resendVerification()
    state.value = 'sent'
  } catch (e) {
    error.value = errorText(e)
    state.value = 'idle'
  }
}
</script>

<template>
  <div
    v-if="session.me && !session.me.email_verified"
    role="status"
    class="border-b border-amber-300 bg-amber-50 text-amber-950 dark:border-amber-800 dark:bg-amber-950 dark:text-amber-100"
  >
    <div class="mx-auto flex max-w-3xl flex-wrap items-center gap-x-3 gap-y-1 px-4 py-2 text-sm">
      <span class="mr-auto">{{ state === 'sent' ? t('verify.resent') : t('verify.banner') }}</span>
      <button
        v-if="state !== 'sent'"
        type="button"
        class="min-h-11 underline disabled:opacity-60"
        :disabled="state === 'sending'"
        @click="resend"
      >
        {{ t('verify.resend') }}
      </button>
      <span v-if="error" class="w-full text-brand-700 dark:text-brand-100">{{ error }}</span>
    </div>
  </div>
</template>
