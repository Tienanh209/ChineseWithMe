<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { RouterLink } from 'vue-router'
import { ApiError } from '@/api/client'
import { getVocab, type Example, type VocabDetail } from '@/api/vocab'
import AudioButton from '@/components/AudioButton.vue'
import DisplayToggles from '@/components/DisplayToggles.vue'
import RubyText from '@/components/RubyText.vue'
import StudyButton from '@/components/StudyButton.vue'
import { errorText } from '@/lib/errors'
import { lastLookup } from '@/lib/lastLookup'
import { usePrefsStore } from '@/stores/prefs'

const props = defineProps<{ id: number }>()
const { t, te } = useI18n()
const prefs = usePrefsStore()

const detail = ref<VocabDetail | null>(null)
const state = ref<'loading' | 'ready' | 'missing' | 'failed'>('loading')
const error = ref<string | null>(null)
let controller: AbortController | null = null

async function load() {
  controller?.abort()
  controller = new AbortController()
  const { signal } = controller
  state.value = 'loading'
  try {
    const response = await getVocab(props.id, prefs.lang, signal)
    if (signal.aborted) return
    detail.value = response
    state.value = 'ready'
  } catch (e) {
    if (signal.aborted) return
    detail.value = null
    if (e instanceof ApiError && e.status === 404) {
      state.value = 'missing'
    } else {
      error.value = errorText(e)
      state.value = 'failed'
    }
  }
}
// Reload for another word (a different reading) and when the language changes, since the
// server lists the reader's language first.
watch(() => [props.id, prefs.lang], load, { immediate: true })

const simplified = computed(() => prefs.script === 'simplified')
const mainText = computed(() =>
  detail.value ? (simplified.value ? detail.value.simplified : detail.value.traditional) : '',
)
const parts = computed(() =>
  detail.value
    ? [{ text: mainText.value, pinyin: detail.value.pinyin, zhuyin: detail.value.zhuyin }]
    : [],
)
const otherForm = computed(() => {
  const d = detail.value
  if (!d || d.simplified === d.traditional) return null
  return simplified.value
    ? t('vocab.otherTraditional', { text: d.traditional })
    : t('vocab.otherSimplified', { text: d.simplified })
})

const langName = (lang: string) =>
  te(`vocab.langNames.${lang}`) ? t(`vocab.langNames.${lang}`) : lang.toUpperCase()

function readingOf(example: Example): string | null {
  return prefs.reading === 'zhuyin'
    ? (example.zhuyin ?? example.pinyin)
    : (example.pinyin ?? example.zhuyin)
}
/** Translations of an example, the reader's language first. */
function translationsOf(example: Example): [string, string][] {
  return Object.entries(example.translations).sort(
    ([a], [b]) => Number(a !== prefs.lang) - Number(b !== prefs.lang) || a.localeCompare(b),
  )
}

function onAdded() {
  if (detail.value) detail.value.study = { status: 'new', next_review_at: new Date().toISOString() }
}
</script>

<template>
  <section class="space-y-5">
    <RouterLink :to="lastLookup()" class="inline-flex min-h-11 items-center text-sm underline">
      ← {{ t('vocab.backToSearch') }}
    </RouterLink>

    <p v-if="state === 'loading'" role="status" class="py-8 text-center text-stone-500">
      {{ t('lookup.loading') }}
    </p>
    <p v-else-if="state === 'missing'" role="alert" class="py-8 text-center">
      {{ t('vocab.notFound') }}
    </p>
    <div v-else-if="state === 'failed'" role="alert" class="space-y-2 py-4">
      <p class="text-brand-600">{{ t('vocab.loadFailed') }} {{ error }}</p>
      <button
        type="button"
        class="min-h-11 rounded-lg border border-stone-300 px-4 text-sm dark:border-stone-700"
        @click="load"
      >
        {{ t('lookup.retry') }}
      </button>
    </div>

    <template v-else-if="detail">
      <header class="space-y-3">
        <div class="flex items-start gap-3">
          <h1 class="min-w-0 flex-1 text-5xl leading-tight font-medium">
            <RubyText :parts="parts" :annotation="prefs.reading" />
          </h1>
          <AudioButton :url="detail.audio_url" />
        </div>
        <p v-if="otherForm" class="text-stone-600 dark:text-stone-400">{{ otherForm }}</p>
        <p class="flex flex-wrap items-center gap-2 text-sm">
          <span
            class="rounded-full bg-brand-100 px-2 py-0.5 font-medium text-brand-700 dark:bg-brand-600/20 dark:text-brand-100"
          >
            {{ detail.level }}
          </span>
          <span v-if="detail.part_of_speech" class="text-stone-500 dark:text-stone-400">{{
            detail.part_of_speech
          }}</span>
          <span class="text-stone-600 dark:text-stone-400"
            >{{ detail.pinyin }} · {{ detail.zhuyin }}</span
          >
        </p>
        <DisplayToggles />
        <StudyButton :vocab-id="detail.id" :studying="detail.study !== null" @added="onAdded" />
      </header>

      <section v-if="detail.readings.length > 1" aria-labelledby="h-readings" class="space-y-2">
        <h2 id="h-readings" class="font-semibold">{{ t('vocab.readings') }}</h2>
        <ul class="space-y-2">
          <li v-for="reading in detail.readings" :key="reading.id">
            <p
              v-if="reading.current"
              aria-current="true"
              class="rounded-xl border border-brand-600 bg-brand-50 p-3 dark:bg-brand-600/10"
            >
              <span class="font-medium">{{
                prefs.reading === 'zhuyin' ? (reading.zhuyin ?? reading.pinyin) : reading.pinyin
              }}</span>
              <span v-if="reading.meaning" class="block text-sm">{{ reading.meaning }}</span>
            </p>
            <RouterLink
              v-else
              :to="{ name: 'vocab', params: { id: reading.id } }"
              class="block rounded-xl border border-stone-200 p-3 hover:border-brand-600 dark:border-stone-800"
            >
              <span class="font-medium">{{
                prefs.reading === 'zhuyin' ? (reading.zhuyin ?? reading.pinyin) : reading.pinyin
              }}</span>
              <span class="ml-2 text-xs text-stone-500">{{ reading.level }}</span>
              <span v-if="reading.meaning" class="block text-sm">{{ reading.meaning }}</span>
            </RouterLink>
          </li>
        </ul>
      </section>

      <section aria-labelledby="h-meanings" class="space-y-3">
        <h2 id="h-meanings" class="font-semibold">{{ t('vocab.meanings') }}</h2>
        <div v-for="translation in detail.translations" :key="translation.lang">
          <h3
            class="text-xs font-semibold tracking-wide text-stone-500 uppercase dark:text-stone-400"
          >
            {{ langName(translation.lang) }}
          </h3>
          <ol class="mt-1 list-inside list-decimal space-y-0.5">
            <li v-for="meaning in translation.meanings" :key="meaning">{{ meaning }}</li>
          </ol>
        </div>
      </section>

      <section v-if="detail.examples.length" aria-labelledby="h-examples" class="space-y-2">
        <h2 id="h-examples" class="font-semibold">{{ t('vocab.examples') }}</h2>
        <ul class="space-y-2">
          <li
            v-for="example in detail.examples"
            :key="example.id"
            class="flex items-start gap-3 rounded-xl border border-stone-200 bg-white p-3 dark:border-stone-800 dark:bg-stone-900"
          >
            <div class="min-w-0 flex-1 space-y-1">
              <p lang="zh-Hant" class="text-xl">{{ example.hanzi }}</p>
              <p v-if="readingOf(example)" class="text-sm text-stone-600 dark:text-stone-400">
                {{ readingOf(example) }}
              </p>
              <p v-for="[lang, line] in translationsOf(example)" :key="lang" class="text-sm">
                <span class="mr-1 text-xs text-stone-400 uppercase">{{ lang }}</span
                >{{ line }}
              </p>
            </div>
            <AudioButton :url="example.audio_url" />
          </li>
        </ul>
      </section>

      <section v-if="detail.groups.length" aria-labelledby="h-groups" class="space-y-2">
        <h2 id="h-groups" class="font-semibold">{{ t('vocab.groups') }}</h2>
        <ul class="flex flex-wrap gap-2">
          <li v-for="group in detail.groups" :key="group.id">
            <RouterLink
              :to="{ name: 'lookup', query: { group: group.id } }"
              class="inline-flex min-h-11 items-center rounded-full border border-stone-300 px-4 text-sm hover:border-brand-600 dark:border-stone-700"
            >
              {{ group.name }}
            </RouterLink>
          </li>
        </ul>
      </section>
    </template>
  </section>
</template>
