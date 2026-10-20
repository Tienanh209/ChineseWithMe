<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { usePrefsStore, type Reading, type Script } from '@/stores/prefs'

const { t } = useI18n()
const prefs = usePrefsStore()

const scripts: { value: Script; label: string; lang: string }[] = [
  { value: 'traditional', label: '繁', lang: 'zh-Hant' },
  { value: 'simplified', label: '简', lang: 'zh-Hans' },
]
const readings: { value: Reading; label: string }[] = [
  { value: 'zhuyin', label: 'ㄅㄆㄇ' },
  { value: 'pinyin', label: 'Pinyin' },
]

const base = 'min-h-11 min-w-11 px-3 text-sm transition-colors'
const active = 'bg-brand-600 text-white'
const idle = 'bg-white hover:bg-stone-100 dark:bg-stone-900 dark:hover:bg-stone-800'
</script>

<template>
  <div class="flex flex-wrap items-center gap-3">
    <div
      role="group"
      :aria-label="t('vocab.script')"
      class="inline-flex overflow-hidden rounded-lg border border-stone-300 dark:border-stone-700"
    >
      <button
        v-for="option in scripts"
        :key="option.value"
        type="button"
        :lang="option.lang"
        :aria-pressed="prefs.script === option.value"
        :aria-label="t(`vocab.${option.value}`)"
        :title="t(`vocab.${option.value}`)"
        :class="[base, prefs.script === option.value ? active : idle]"
        @click="prefs.setScript(option.value)"
      >
        {{ option.label }}
      </button>
    </div>
    <div
      role="group"
      :aria-label="t('vocab.reading')"
      class="inline-flex overflow-hidden rounded-lg border border-stone-300 dark:border-stone-700"
    >
      <button
        v-for="option in readings"
        :key="option.value"
        type="button"
        :aria-pressed="prefs.reading === option.value"
        :class="[base, prefs.reading === option.value ? active : idle]"
        @click="prefs.setReading(option.value)"
      >
        {{ option.label }}
      </button>
    </div>
  </div>
</template>
