<script setup lang="ts">
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { RouterLink } from 'vue-router'
import { ApiError } from '@/api/client'
import LevelPicker from '@/components/LevelPicker.vue'
import RubyText, { type RubyPart } from '@/components/RubyText.vue'
import { errorText } from '@/lib/errors'
import { usePrefsStore, type Theme } from '@/stores/prefs'
import { useSessionStore } from '@/stores/session'

const { t } = useI18n()
const prefs = usePrefsStore()
const session = useSessionStore()

const annotation = ref<'pinyin' | 'zhuyin' | 'none'>('zhuyin')
const sample: RubyPart[] = [
  { text: '我', pinyin: 'wǒ', zhuyin: 'ㄨㄛˇ' },
  { text: '每天', pinyin: 'měitiān', zhuyin: 'ㄇㄟˇ ㄊㄧㄢ' },
  { text: '學習', pinyin: 'xuéxí', zhuyin: 'ㄒㄩㄝˊ ㄒㄧˊ' },
  { text: '中文', pinyin: 'Zhōngwén', zhuyin: 'ㄓㄨㄥ ㄨㄣˊ' },
  { text: '。' },
]
const themes: Theme[] = ['system', 'light', 'dark']
const error = ref<string | null>(null)

async function setLevel(level: Parameters<typeof prefs.setLevel>[0]) {
  error.value = null
  try {
    await prefs.setLevel(level)
  } catch (e) {
    error.value = e instanceof ApiError ? errorText(e) : t('errors.generic')
  }
}

const chip = (active: boolean) =>
  active
    ? 'border-brand-600 bg-brand-50 text-brand-700 dark:bg-brand-600/20 dark:text-brand-100'
    : 'border-stone-300 dark:border-stone-700'
const linkButton = 'inline-flex min-h-11 items-center rounded-lg px-4 text-sm font-medium'
</script>

<template>
  <div class="space-y-6">
    <section>
      <h1 class="text-2xl font-bold">{{ t('home.title') }}</h1>
      <p class="mt-1 text-stone-600 dark:text-stone-400">{{ t('home.subtitle') }}</p>
    </section>

    <section
      class="rounded-2xl border border-stone-200 bg-white p-4 dark:border-stone-800 dark:bg-stone-900"
    >
      <div class="flex flex-wrap items-center gap-2 text-sm">
        <span class="mr-auto font-medium">{{ t('home.sample') }}</span>
        <span class="sr-only">{{ t('home.annotation') }}</span>
        <button
          v-for="mode in ['zhuyin', 'pinyin', 'none'] as const"
          :key="mode"
          type="button"
          class="min-h-11 rounded-full border px-3"
          :class="chip(annotation === mode)"
          :aria-pressed="annotation === mode"
          @click="annotation = mode"
        >
          {{ mode === 'zhuyin' ? 'ㄅㄆㄇ' : mode === 'pinyin' ? 'Pinyin' : t('home.none') }}
        </button>
      </div>
      <p class="mt-3 text-3xl"><RubyText :parts="sample" :annotation="annotation" /></p>
    </section>

    <section class="space-y-2">
      <h2 class="font-semibold">{{ t('prefs.level') }}</h2>
      <p class="text-sm text-stone-600 dark:text-stone-400">{{ t('prefs.levelHint') }}</p>
      <LevelPicker
        :model-value="prefs.level"
        :label="t('prefs.level')"
        @update:model-value="setLevel"
      />
      <p v-if="error" role="alert" class="text-sm text-brand-600">{{ error }}</p>
    </section>

    <section class="space-y-2">
      <h2 class="font-semibold">{{ t('prefs.theme') }}</h2>
      <div class="flex gap-2">
        <button
          v-for="value in themes"
          :key="value"
          type="button"
          class="min-h-11 rounded-full border px-4 text-sm"
          :class="chip(prefs.theme === value)"
          :aria-pressed="prefs.theme === value"
          @click="prefs.setTheme(value)"
        >
          {{ t(`prefs.themes.${value}`) }}
        </button>
      </div>
    </section>

    <section class="space-y-2 text-sm">
      <p v-if="session.me">
        {{ t('account.signedInAs', { name: session.me.display_name ?? session.me.email }) }}
      </p>
      <template v-else>
        <p class="text-stone-600 dark:text-stone-400">{{ t('prefs.savedLocally') }}</p>
        <div class="flex flex-wrap gap-2">
          <RouterLink
            :to="{ name: 'login' }"
            :class="linkButton"
            class="bg-brand-600 text-white hover:bg-brand-700"
          >
            {{ t('home.signIn') }}
          </RouterLink>
          <RouterLink
            :to="{ name: 'register' }"
            :class="linkButton"
            class="border border-stone-300 dark:border-stone-700"
          >
            {{ t('home.createAccount') }}
          </RouterLink>
        </div>
      </template>
    </section>
  </div>
</template>
