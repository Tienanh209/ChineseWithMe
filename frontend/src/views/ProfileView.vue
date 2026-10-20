<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import { UI_LANGS, type UiLang } from '@/api/types'
import BaseButton from '@/components/BaseButton.vue'
import FormField from '@/components/FormField.vue'
import GoogleButton from '@/components/GoogleButton.vue'
import LevelPicker from '@/components/LevelPicker.vue'
import { errorText } from '@/lib/errors'
import { usePrefsStore } from '@/stores/prefs'
import { useSessionStore } from '@/stores/session'

const { t } = useI18n()
const router = useRouter()
const session = useSessionStore()
const prefs = usePrefsStore()

// The router guard guarantees a signed-in user; `me` is only null briefly while signing out.
const me = computed(() => session.me!)

type Section = 'details' | 'password' | 'google' | 'delete' | 'learning' | 'verify'
const busy = ref<Section | null>(null)
const messages = reactive<Partial<Record<Section, { ok: boolean; text: string }>>>({})

async function run(section: Section, action: () => Promise<string | void>) {
  busy.value = section
  delete messages[section]
  try {
    const done = await action()
    if (done) messages[section] = { ok: true, text: done }
  } catch (e) {
    messages[section] = { ok: false, text: errorText(e) }
  } finally {
    busy.value = null
  }
}

// Details ---------------------------------------------------------------------
const details = reactive({ display_name: '', username: '', avatar_url: '' })
watch(
  () => session.me,
  (value) => {
    if (!value) return
    details.display_name = value.display_name ?? ''
    details.username = value.username ?? ''
    details.avatar_url = value.avatar_url ?? ''
  },
  { immediate: true },
)
const saveDetails = () =>
  run('details', async () => {
    await session.update({
      display_name: details.display_name.trim() || null,
      username: details.username.trim() || null,
      avatar_url: details.avatar_url.trim() || null,
    })
    return t('common.saved')
  })

// Learning preferences (saved to the account by the prefs store) ---------------
const setLevel = (level: Parameters<typeof prefs.setLevel>[0]) =>
  run('learning', () => prefs.setLevel(level))
const setLang = (event: Event) =>
  run('learning', () => prefs.setLang((event.target as HTMLSelectElement).value as UiLang))

// Password ----------------------------------------------------------------------
const pw = reactive({ current: '', next: '' })
const savePassword = () =>
  run('password', async () => {
    await session.changePassword(me.value.has_password ? pw.current : null, pw.next)
    pw.current = pw.next = ''
    return t('profile.passwordChanged')
  })

// Google --------------------------------------------------------------------------
const linkPassword = ref('')
const linkGoogle = (credential: string) =>
  run('google', async () => {
    await session.linkGoogle(credential, me.value.has_password ? linkPassword.value : null)
    linkPassword.value = ''
    return t('profile.googleLinkedNow')
  })
const unlinkGoogle = () =>
  run('google', async () => {
    await session.unlinkGoogle()
    return t('profile.googleUnlinked')
  })

// Verify email ----------------------------------------------------------------------
const resend = () =>
  run('verify', async () => {
    await session.resendVerification()
    return t('verify.resent')
  })

// Delete account ----------------------------------------------------------------------
const deletePassword = ref('')
async function afterDelete() {
  await router.push('/')
}
const deleteWithPassword = () =>
  run('delete', async () => {
    await session.deleteAccount({ password: deletePassword.value })
    await afterDelete()
  })
const deleteWithGoogle = (credential: string) =>
  run('delete', async () => {
    await session.deleteAccount({ credential })
    await afterDelete()
  })

const logout = async () => {
  await session.logout()
  await router.push('/')
}

const section =
  'space-y-3 rounded-2xl border border-stone-200 bg-white p-4 dark:border-stone-800 dark:bg-stone-900'
</script>

<template>
  <div v-if="session.me" class="space-y-5">
    <h1 class="text-2xl font-bold">{{ t('profile.title') }}</h1>

    <section :class="section" aria-labelledby="h-account">
      <h2 id="h-account" class="font-semibold">{{ t('profile.account') }}</h2>
      <p class="break-all">{{ me.email }}</p>
      <p class="text-sm">
        <span
          :class="
            me.email_verified
              ? 'text-emerald-700 dark:text-emerald-400'
              : 'text-amber-700 dark:text-amber-400'
          "
        >
          {{ me.email_verified ? t('profile.emailVerified') : t('profile.emailUnverified') }}
        </span>
      </p>
      <BaseButton
        v-if="!me.email_verified"
        variant="secondary"
        :loading="busy === 'verify'"
        @click="resend"
      >
        {{ t('verify.resend') }}
      </BaseButton>
      <p
        v-if="messages.verify"
        role="status"
        :class="messages.verify.ok ? '' : 'text-brand-600'"
        class="text-sm"
      >
        {{ messages.verify.text }}
      </p>
    </section>

    <section :class="section" aria-labelledby="h-details">
      <h2 id="h-details" class="font-semibold">{{ t('profile.details') }}</h2>
      <form class="space-y-3" novalidate @submit.prevent="saveDetails">
        <FormField
          v-model="details.display_name"
          :label="t('profile.displayName')"
          autocomplete="name"
          :maxlength="100"
        />
        <FormField
          v-model="details.username"
          :label="t('profile.username')"
          autocomplete="username"
          :hint="t('profile.usernameHint')"
          :maxlength="32"
        />
        <FormField
          v-model="details.avatar_url"
          :label="t('profile.avatarUrl')"
          type="url"
          inputmode="url"
          :hint="t('profile.avatarHint')"
          :maxlength="500"
        />
        <BaseButton type="submit" :loading="busy === 'details'">
          {{ busy === 'details' ? t('common.saving') : t('common.save') }}
        </BaseButton>
        <p
          v-if="messages.details"
          role="status"
          :class="messages.details.ok ? '' : 'text-brand-600'"
          class="text-sm"
        >
          {{ messages.details.text }}
        </p>
      </form>
    </section>

    <section :class="section" aria-labelledby="h-learning">
      <h2 id="h-learning" class="font-semibold">{{ t('profile.learning') }}</h2>
      <LevelPicker
        :model-value="prefs.level"
        :label="t('prefs.level')"
        @update:model-value="setLevel"
      />
      <label class="block text-sm font-medium" for="prof-lang">{{ t('prefs.language') }}</label>
      <select
        id="prof-lang"
        class="min-h-11 rounded-lg border border-stone-300 bg-white px-2 dark:border-stone-700 dark:bg-stone-900"
        :value="prefs.lang"
        @change="setLang"
      >
        <option v-for="lang in UI_LANGS" :key="lang" :value="lang">
          {{ lang === 'vi' ? 'Tiếng Việt' : 'English' }}
        </option>
      </select>
      <p v-if="messages.learning" role="alert" class="text-sm text-brand-600">
        {{ messages.learning.text }}
      </p>
    </section>

    <section :class="section" aria-labelledby="h-password">
      <h2 id="h-password" class="font-semibold">
        {{ me.has_password ? t('profile.changePassword') : t('profile.setPassword') }}
      </h2>
      <form class="space-y-3" novalidate @submit.prevent="savePassword">
        <FormField
          v-if="me.has_password"
          v-model="pw.current"
          :label="t('profile.currentPassword')"
          type="password"
          autocomplete="current-password"
          :maxlength="128"
        />
        <FormField
          v-model="pw.next"
          :label="t('profile.newPassword')"
          type="password"
          autocomplete="new-password"
          :hint="t('auth.passwordHint')"
          :maxlength="128"
        />
        <BaseButton type="submit" :loading="busy === 'password'">{{ t('common.save') }}</BaseButton>
        <p
          v-if="messages.password"
          role="status"
          :class="messages.password.ok ? '' : 'text-brand-600'"
          class="text-sm"
        >
          {{ messages.password.text }}
        </p>
      </form>
    </section>

    <section :class="section" aria-labelledby="h-google">
      <h2 id="h-google" class="font-semibold">{{ t('profile.google') }}</h2>
      <template v-if="me.google_linked">
        <p>{{ t('profile.googleLinked') }}</p>
        <p v-if="!me.has_password" class="text-sm text-stone-600 dark:text-stone-400">
          {{ t('profile.unlinkBlocked') }}
        </p>
        <BaseButton
          variant="secondary"
          :disabled="!me.has_password"
          :loading="busy === 'google'"
          @click="unlinkGoogle"
        >
          {{ t('profile.unlinkGoogle') }}
        </BaseButton>
      </template>
      <template v-else>
        <p>{{ t('profile.googleNotLinked') }}</p>
        <template v-if="me.has_password">
          <p class="text-sm text-stone-600 dark:text-stone-400">
            {{ t('profile.linkNeedsPassword') }}
          </p>
          <FormField
            v-model="linkPassword"
            :label="t('common.password')"
            type="password"
            autocomplete="current-password"
            :maxlength="128"
          />
        </template>
        <GoogleButton text="continue_with" @credential="linkGoogle" />
      </template>
      <p
        v-if="messages.google"
        role="status"
        :class="messages.google.ok ? '' : 'text-brand-600'"
        class="text-sm"
      >
        {{ messages.google.text }}
      </p>
    </section>

    <section :class="section" aria-labelledby="h-session">
      <h2 id="h-session" class="font-semibold">{{ t('profile.session') }}</h2>
      <BaseButton variant="secondary" @click="logout">{{ t('account.signOut') }}</BaseButton>
    </section>

    <section
      class="space-y-3 rounded-2xl border border-brand-600/40 bg-white p-4 dark:bg-stone-900"
      aria-labelledby="h-delete"
    >
      <h2 id="h-delete" class="font-semibold text-brand-700 dark:text-brand-100">
        {{ t('profile.danger') }}
      </h2>
      <p class="text-sm">{{ t('profile.dangerText') }}</p>
      <form
        v-if="me.has_password"
        class="space-y-3"
        novalidate
        @submit.prevent="deleteWithPassword"
      >
        <FormField
          v-model="deletePassword"
          :label="t('profile.confirmPassword')"
          type="password"
          autocomplete="current-password"
          :maxlength="128"
        />
        <BaseButton type="submit" variant="danger" :loading="busy === 'delete'">
          {{ t('profile.deleteButton') }}
        </BaseButton>
      </form>
      <template v-else>
        <p class="text-sm">{{ t('profile.confirmGoogle') }}</p>
        <GoogleButton text="continue_with" @credential="deleteWithGoogle" />
      </template>
      <p v-if="messages.delete" role="alert" class="text-sm text-brand-600">
        {{ messages.delete.text }}
      </p>
    </section>
  </div>
</template>
