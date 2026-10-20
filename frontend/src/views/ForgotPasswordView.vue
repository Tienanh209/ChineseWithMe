<script setup lang="ts">
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { RouterLink } from 'vue-router'
import BaseButton from '@/components/BaseButton.vue'
import FormField from '@/components/FormField.vue'
import { errorText } from '@/lib/errors'
import { useSessionStore } from '@/stores/session'

const { t } = useI18n()
const session = useSessionStore()
const email = ref('')
const busy = ref(false)
const sent = ref(false)
const error = ref<string | null>(null)

async function submit() {
  busy.value = true
  error.value = null
  try {
    await session.forgotPassword(email.value.trim())
    sent.value = true
  } catch (e) {
    error.value = errorText(e)
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <section class="mx-auto max-w-md space-y-4">
    <h1 class="text-2xl font-bold">{{ t('forgot.title') }}</h1>
    <p v-if="sent" role="status">{{ t('forgot.sent') }}</p>
    <form v-else class="space-y-4" novalidate @submit.prevent="submit">
      <p class="text-stone-600 dark:text-stone-400">{{ t('forgot.intro') }}</p>
      <FormField
        v-model="email"
        :label="t('common.email')"
        type="email"
        autocomplete="email"
        inputmode="email"
        required
      />
      <p v-if="error" role="alert" class="text-sm text-brand-600">{{ error }}</p>
      <BaseButton type="submit" class="w-full" :loading="busy">{{ t('forgot.send') }}</BaseButton>
    </form>
    <RouterLink :to="{ name: 'login' }" class="inline-flex min-h-11 items-center text-sm underline">
      {{ t('common.backToSignIn') }}
    </RouterLink>
  </section>
</template>
