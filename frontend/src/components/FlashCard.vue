<script setup lang="ts">
/**
 * One flashcard. Front: the word. Back: its reading, meanings and an example, and the four answers with
 * what each would schedule. Keyboard: Space or Enter reveals; 1-4 answer.
 */
import { computed, onBeforeUnmount, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import type { Card, Rating } from '@/api/flashcards'
import { intervalLabel } from '@/lib/studyQueue'
import { usePrefsStore } from '@/stores/prefs'
import AudioButton from './AudioButton.vue'
import BaseButton from './BaseButton.vue'
import RubyText from './RubyText.vue'

const props = defineProps<{
  card: Card
  revealed: boolean
  /** Answers are being saved: ignore further input. */
  busy: boolean
  now: Date
}>()
const emit = defineEmits<{ reveal: []; rate: [rating: Rating] }>()

const { t } = useI18n()
const prefs = usePrefsStore()

const text = computed(() =>
  prefs.script === 'simplified' ? props.card.simplified : props.card.traditional,
)
const parts = computed(() => [
  { text: text.value, pinyin: props.card.pinyin, zhuyin: props.card.zhuyin },
])

function sortedLangs<T>(record: Record<string, T>): [string, T][] {
  return Object.entries(record).sort(
    ([a], [b]) => Number(a !== prefs.lang) - Number(b !== prefs.lang) || a.localeCompare(b),
  )
}
const meanings = computed(() => sortedLangs(props.card.meanings))
const exampleReading = computed(() => {
  const example = props.card.example
  if (!example) return null
  return prefs.reading === 'zhuyin'
    ? (example.zhuyin ?? example.pinyin)
    : (example.pinyin ?? example.zhuyin)
})
const exampleTranslations = computed(() => sortedLangs(props.card.example?.translations ?? {}))

const buttons: { rating: Rating; key: 'again' | 'hard' | 'good' | 'easy'; style: string }[] = [
  { rating: 1, key: 'again', style: 'border-brand-600 text-brand-700 dark:text-brand-100' },
  { rating: 2, key: 'hard', style: 'border-amber-500' },
  { rating: 3, key: 'good', style: 'border-emerald-600' },
  { rating: 4, key: 'easy', style: 'border-sky-600' },
]

function label(rating: Rating): string {
  const option = props.card.next.find((n) => n.rating === rating)
  if (!option) return ''
  const { unit, n } = intervalLabel(option.interval_days, option.due_at, props.now)
  return t(`cards.${unit}`, { n }, n)
}

function onKey(event: KeyboardEvent) {
  if (props.busy || event.metaKey || event.ctrlKey || event.altKey) return
  const target = event.target as HTMLElement | null
  if (target && ['INPUT', 'SELECT', 'TEXTAREA'].includes(target.tagName)) return
  if (!props.revealed) {
    if (event.key === ' ' || event.key === 'Enter') {
      event.preventDefault()
      emit('reveal')
    }
    return
  }
  const rating = Number(event.key)
  if (rating >= 1 && rating <= 4 && Number.isInteger(rating)) emit('rate', rating as Rating)
}
onMounted(() => window.addEventListener('keydown', onKey))
onBeforeUnmount(() => window.removeEventListener('keydown', onKey))
</script>

<template>
  <div class="space-y-4">
    <article
      :aria-label="t('cards.card')"
      class="space-y-4 rounded-2xl border border-stone-200 bg-white p-5 dark:border-stone-800 dark:bg-stone-900"
    >
      <div class="flex items-center gap-2 text-xs">
        <span
          class="rounded-full bg-brand-100 px-2 py-0.5 font-medium text-brand-700 dark:bg-brand-600/20 dark:text-brand-100"
        >
          {{ card.level }}
        </span>
        <span
          v-if="card.is_new"
          class="rounded-full border border-stone-300 px-2 py-0.5 dark:border-stone-700"
        >
          {{ t('cards.newCard') }}
        </span>
        <span v-if="card.part_of_speech" class="text-stone-500 dark:text-stone-400">{{
          card.part_of_speech
        }}</span>
        <span class="ml-auto"><AudioButton :url="card.audio_url" /></span>
      </div>

      <p class="py-2 text-center text-6xl leading-tight font-medium" data-testid="word">
        <RubyText :parts="parts" :annotation="revealed ? prefs.reading : 'none'" />
      </p>

      <template v-if="revealed">
        <div class="space-y-3 border-t border-stone-200 pt-4 dark:border-stone-800">
          <p class="text-center text-stone-600 dark:text-stone-400">
            {{ card.pinyin }}<template v-if="card.zhuyin"> · {{ card.zhuyin }}</template>
          </p>
          <ul class="space-y-1 text-center">
            <li v-for="[lang, list] in meanings" :key="lang" class="text-lg">
              <span class="mr-1 text-xs text-stone-400 uppercase">{{ lang }}</span
              >{{ list.join('; ') }}
            </li>
          </ul>
          <div
            v-if="card.example"
            class="flex items-start gap-3 rounded-xl bg-stone-100 p-3 dark:bg-stone-800"
          >
            <div class="min-w-0 flex-1 space-y-0.5">
              <p class="text-xs font-semibold tracking-wide text-stone-500 uppercase">
                {{ t('cards.example') }}
              </p>
              <p lang="zh-Hant" class="text-lg">{{ card.example.hanzi }}</p>
              <p v-if="exampleReading" class="text-sm text-stone-600 dark:text-stone-400">
                {{ exampleReading }}
              </p>
              <p v-for="[lang, line] in exampleTranslations" :key="lang" class="text-sm">
                <span class="mr-1 text-xs text-stone-400 uppercase">{{ lang }}</span
                >{{ line }}
              </p>
            </div>
            <AudioButton :url="card.example.audio_url" />
          </div>
        </div>
      </template>
      <div v-else class="flex flex-col items-center gap-2">
        <BaseButton class="w-full max-w-xs" @click="emit('reveal')">{{
          t('cards.showAnswer')
        }}</BaseButton>
        <p class="hidden text-xs text-stone-500 sm:block dark:text-stone-400">
          {{ t('cards.keys') }}
        </p>
      </div>
    </article>

    <!-- On a phone the answers stay pinned just above the tab bar, so a tall card never pushes them off screen. -->
    <div
      v-if="revealed"
      class="sticky bottom-[calc(3.5rem+env(safe-area-inset-bottom))] z-[5] -mx-4 bg-stone-50/95 px-4 py-2 backdrop-blur sm:static sm:mx-0 sm:bg-transparent sm:p-0 sm:backdrop-blur-none dark:bg-stone-950/95 sm:dark:bg-transparent"
    >
      <div
        role="group"
        :aria-label="t('cards.rating')"
        class="grid grid-cols-2 gap-2 sm:grid-cols-4"
      >
        <button
          v-for="button in buttons"
          :key="button.rating"
          type="button"
          :disabled="busy"
          :aria-keyshortcuts="String(button.rating)"
          class="flex min-h-16 flex-col items-center justify-center rounded-xl border-2 bg-white px-2 py-2 text-sm font-medium transition-colors hover:bg-stone-50 disabled:opacity-60 dark:bg-stone-900 dark:hover:bg-stone-800"
          :class="button.style"
          @click="emit('rate', button.rating)"
        >
          <span class="text-base">{{ t(`cards.${button.key}`) }}</span>
          <span class="text-xs font-normal text-stone-500 dark:text-stone-400">{{
            label(button.rating)
          }}</span>
        </button>
      </div>
    </div>
  </div>
</template>
