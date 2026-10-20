<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import BaseButton from '@/components/BaseButton.vue'
import FormField from '@/components/FormField.vue'
import GoogleButton from '@/components/GoogleButton.vue'
import { errorText } from '@/lib/errors'
import { safeNext } from '@/lib/redirect'
import { usePrefsStore } from '@/stores/prefs'
import { useSessionStore } from '@/stores/session'

const { t } = useI18n()
const route = useRoute()
const router = useRouter()
const session = useSessionStore()
const prefs = usePrefsStore()

const isRegister = computed(() => route.name === 'register')
const email = ref('')
const password = ref('')
const displayName = ref('')
const busy = ref(false)
const error = ref<string | null>(null)
const googleUnavailable = ref(false)

const other = computed(() => ({
  name: isRegister.value ? 'login' : 'register',
  query: route.query.next ? { next: route.query.next } : undefined,
}))

async function finish() {
  await router.push(safeNext(route.query.next) ?? '/')
}

async function run(action: () => Promise<void>) {
  busy.value = true
  error.value = null
  try {
    await action()
    await finish()
  } catch (e) {
    error.value = errorText(e)
  } finally {
    busy.value = false
  }
}

const submit = () =>
  run(() =>
    isRegister.value
      ? session.register({
          email: email.value.trim(),
          password: password.value,
          display_name: displayName.value.trim() || undefined,
          ui_lang: prefs.lang,
          target_level: prefs.level,
        })
      : session.login(email.value.trim(), password.value),
  )

const onGoogle = (credential: string) => run(() => session.loginWithGoogle(credential))
</script>

<template>
  <section class="mx-auto max-w-md space-y-5">
    <h1 class="text-2xl font-bold">
      {{ isRegister ? t('auth.registerTitle') : t('auth.signInTitle') }}
    </h1>

    <GoogleButton
      :text="isRegister ? 'signup_with' : 'signin_with'"
      :one-tap="!isRegister"
      @credential="onGoogle"
      @unavailable="googleUnavailable = true"
    />
    <p v-if="googleUnavailable" class="text-sm text-stone-500 dark:text-stone-400">
      {{ t('auth.googleFailed') }}
    </p>
    <p v-if="session.googleClientId" class="text-center text-sm text-stone-500 dark:text-stone-400">
      {{ t('auth.googleOr') }}
    </p>

    <form class="space-y-4" novalidate @submit.prevent="submit">
      <FormField
        v-model="email"
        :label="t('common.email')"
        type="email"
        autocomplete="email"
        inputmode="email"
        required
      />
      <FormField
        v-if="isRegister"
        v-model="displayName"
        :label="t('auth.displayName')"
        autocomplete="name"
        :maxlength="100"
      />
      <FormField
        v-model="password"
        :label="t('common.password')"
        type="password"
        :autocomplete="isRegister ? 'new-password' : 'current-password'"
        :hint="isRegister ? t('auth.passwordHint') : undefined"
        :maxlength="128"
        required
      />
      <p v-if="error" role="alert" class="text-sm text-brand-600">{{ error }}</p>
      <BaseButton type="submit" class="w-full" :loading="busy">
        {{
          busy ? t('auth.working') : isRegister ? t('auth.registerButton') : t('auth.signInButton')
        }}
      </BaseButton>
    </form>

    <div class="flex flex-wrap justify-between gap-2 text-sm">
      <RouterLink :to="other" class="inline-flex min-h-11 items-center underline">
        {{ isRegister ? t('auth.haveAccount') : t('auth.noAccount') }}
        {{ isRegister ? t('auth.signInButton') : t('auth.registerButton') }}
      </RouterLink>
      <RouterLink
        v-if="!isRegister"
        :to="{ name: 'forgot-password' }"
        class="inline-flex min-h-11 items-center underline"
      >
        {{ t('auth.forgot') }}
      </RouterLink>
    </div>
  </section>
</template>
