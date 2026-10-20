<script setup lang="ts">
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { RouterLink, useRoute } from 'vue-router'
import BaseButton from '@/components/BaseButton.vue'
import FormField from '@/components/FormField.vue'
import { errorText } from '@/lib/errors'
import { useSessionStore } from '@/stores/session'

const { t } = useI18n()
const route = useRoute()
const session = useSessionStore()
const token = typeof route.query.token === 'string' ? route.query.token : ''
const password = ref('')
const busy = ref(false)
const done = ref(false)
const error = ref<string | null>(null)

async function submit() {
  busy.value = true
  error.value = null
  try {
    await session.resetPassword(token, password.value)
    session.me = null // the server signed every session out
    done.value = true
  } catch (e) {
    error.value = errorText(e)
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <section class="mx-auto max-w-md space-y-4">
    <h1 class="text-2xl font-bold">{{ t('reset.title') }}</h1>
    <template v-if="!token">
      <p role="alert" class="text-brand-600">{{ t('reset.missingToken') }}</p>
      <RouterLink
        :to="{ name: 'forgot-password' }"
        class="inline-flex min-h-11 items-center underline"
      >
        {{ t('reset.requestNew') }}
      </RouterLink>
    </template>
    <template v-else-if="done">
      <p role="status">{{ t('reset.done') }}</p>
      <RouterLink :to="{ name: 'login' }" class="inline-flex min-h-11 items-center underline">
        {{ t('auth.signInButton') }}
      </RouterLink>
    </template>
    <form v-else class="space-y-4" novalidate @submit.prevent="submit">
      <FormField
        v-model="password"
        :label="t('reset.newPassword')"
        type="password"
        autocomplete="new-password"
        :hint="t('auth.passwordHint')"
        :maxlength="128"
        required
      />
      <p v-if="error" role="alert" class="text-sm text-brand-600">{{ error }}</p>
      <BaseButton type="submit" class="w-full" :loading="busy">{{ t('reset.submit') }}</BaseButton>
    </form>
  </section>
</template>
