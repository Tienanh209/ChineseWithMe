<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { RouterLink } from 'vue-router'
import { LEVELS, UI_LANGS, type Level, type UiLang } from '@/api/types'
import { usePrefsStore } from '@/stores/prefs'

const { t } = useI18n()
const prefs = usePrefsStore()

const selectClass =
  'min-h-11 rounded-lg border border-stone-300 bg-white px-2 text-sm dark:border-stone-700 dark:bg-stone-900'
</script>

<template>
  <header
    class="sticky top-0 z-10 border-b border-stone-200 bg-stone-50/90 backdrop-blur dark:border-stone-800 dark:bg-stone-950/90"
  >
    <div class="mx-auto flex max-w-3xl items-center gap-2 px-4 py-2">
      <RouterLink to="/" class="mr-auto flex min-h-11 items-center gap-2 font-semibold">
        <span lang="zh-Hant" class="rounded-md bg-brand-600 px-1.5 text-lg text-white">學</span>
        <span class="hidden sm:inline">{{ t('app.name') }}</span>
      </RouterLink>

      <label class="sr-only" for="hdr-level">{{ t('prefs.level') }}</label>
      <select
        id="hdr-level"
        :class="selectClass"
        :value="prefs.level"
        @change="prefs.setLevel(($event.target as HTMLSelectElement).value as Level)"
      >
        <option v-for="level in LEVELS" :key="level" :value="level">{{ level }}</option>
      </select>

      <label class="sr-only" for="hdr-lang">{{ t('prefs.language') }}</label>
      <select
        id="hdr-lang"
        :class="selectClass"
        :value="prefs.lang"
        @change="prefs.setLang(($event.target as HTMLSelectElement).value as UiLang)"
      >
        <option v-for="lang in UI_LANGS" :key="lang" :value="lang">
          {{ lang === 'vi' ? 'Tiếng Việt' : 'English' }}
        </option>
      </select>
    </div>
  </header>
</template>
