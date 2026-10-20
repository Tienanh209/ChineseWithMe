<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { RouterLink } from 'vue-router'
import type { VocabItem } from '@/api/vocab'
import { usePrefsStore } from '@/stores/prefs'

const props = defineProps<{ item: VocabItem }>()
const { t } = useI18n()
const prefs = usePrefsStore()

const text = computed(() =>
  prefs.script === 'simplified' ? props.item.simplified : props.item.traditional,
)
const reading = computed(() => {
  const { pinyin, zhuyin } = props.item
  // A word without zhuyin shows its pinyin rather than nothing.
  return prefs.reading === 'zhuyin' ? (zhuyin ?? pinyin) : pinyin
})

/** The reader's language first, then the others; a few meanings are enough for a list. */
const meaning = computed(() => {
  const langs = Object.keys(props.item.meanings).sort(
    (a, b) => Number(a !== prefs.lang) - Number(b !== prefs.lang) || a.localeCompare(b),
  )
  const first = langs[0]
  return first ? props.item.meanings[first]!.slice(0, 3).join('; ') : ''
})
</script>

<template>
  <RouterLink
    :to="{ name: 'vocab', params: { id: item.id } }"
    class="flex min-h-11 items-center gap-3 rounded-2xl border border-stone-200 bg-white p-3 hover:border-brand-600 dark:border-stone-800 dark:bg-stone-900"
  >
    <div class="min-w-0 flex-1">
      <p class="flex flex-wrap items-baseline gap-x-3">
        <span
          :lang="prefs.script === 'simplified' ? 'zh-Hans' : 'zh-Hant'"
          class="text-2xl font-medium"
        >
          {{ text }}
        </span>
        <span
          class="text-stone-600 dark:text-stone-400"
          :lang="prefs.reading === 'zhuyin' && item.zhuyin ? 'zh-Bopo' : 'zh-Latn-pinyin'"
        >
          {{ reading }}
        </span>
      </p>
      <p class="mt-0.5 text-sm">{{ meaning }}</p>
    </div>
    <div class="flex shrink-0 flex-col items-end gap-1 text-xs">
      <span
        class="rounded-full bg-brand-100 px-2 py-0.5 font-medium text-brand-700 dark:bg-brand-600/20 dark:text-brand-100"
      >
        {{ item.level }}
      </span>
      <span v-if="item.part_of_speech" class="text-stone-500 dark:text-stone-400">
        {{ item.part_of_speech }}
      </span>
      <span
        v-if="item.in_study_list"
        class="text-emerald-700 dark:text-emerald-400"
        :title="t('lookup.inStudyList')"
        :aria-label="t('lookup.inStudyList')"
        role="img"
      >
        ✓
      </span>
    </div>
  </RouterLink>
</template>
