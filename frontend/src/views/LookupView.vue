<script setup lang="ts">
/**
 * Look-up and browse. The URL is the state (?q=&level=&group=&page=), so the back button, reloads
 * and shared links all behave. With nothing typed or chosen it shows the browse panels (levels
 * and word lists); otherwise a page of results.
 */
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'
import { LEVELS, type Level } from '@/api/types'
import {
  getGroups,
  getLevels,
  searchVocab,
  type LevelCount,
  type SearchResponse,
  type VocabGroup,
} from '@/api/vocab'
import DisplayToggles from '@/components/DisplayToggles.vue'
import WordCard from '@/components/WordCard.vue'
import { errorText } from '@/lib/errors'

const PAGE_SIZE = 20
const DEBOUNCE_MS = 300

const { t } = useI18n()
const route = useRoute()
const router = useRouter()

const text = (value: unknown) => (typeof value === 'string' ? value : '')
const q = computed(() => text(route.query.q).trim())
const level = computed<Level | null>(() => {
  const value = text(route.query.level)
  return (LEVELS as readonly string[]).includes(value) ? (value as Level) : null
})
const groupId = computed<number | null>(() => {
  const value = Number(text(route.query.group))
  return Number.isInteger(value) && value > 0 ? value : null
})
const page = computed(() => {
  const value = Number(text(route.query.page))
  return Number.isInteger(value) && value > 0 ? value : 1
})
const browsing = computed(() => !q.value && !level.value && groupId.value === null)

// What the user has typed, ahead of the URL by one debounce.
const input = ref(q.value)
let timer: ReturnType<typeof setTimeout> | undefined
watch(q, (value) => {
  if (value !== input.value.trim()) input.value = value // back/forward, "clear filters"
})
watch(input, (value) => {
  clearTimeout(timer)
  if (value.trim() === q.value) return
  timer = setTimeout(
    () => setQuery({ q: value.trim() || undefined, page: undefined }, true),
    DEBOUNCE_MS,
  )
})
onBeforeUnmount(() => clearTimeout(timer))

function setQuery(changes: Record<string, string | number | undefined>, replace = false) {
  const next: Record<string, string> = {}
  for (const [key, value] of Object.entries({ ...route.query, ...changes })) {
    if (value !== undefined && value !== null && value !== '') next[key] = String(value)
  }
  return replace ? router.replace({ query: next }) : router.push({ query: next })
}

const clearFilters = () => {
  input.value = ''
  return router.push({ query: {} })
}

// Browse data: small, loaded once.
const levels = ref<LevelCount[]>([])
const groups = ref<VocabGroup[]>([])
getLevels()
  .then((value) => (levels.value = value))
  .catch(() => {})
getGroups()
  .then((value) => (groups.value = value))
  .catch(() => {})

// Results.
const result = ref<SearchResponse | null>(null)
const loading = ref(false)
const error = ref<string | null>(null)
let controller: AbortController | null = null

async function load() {
  controller?.abort()
  if (browsing.value) {
    result.value = null
    loading.value = false
    error.value = null
    return
  }
  controller = new AbortController()
  const { signal } = controller
  loading.value = true
  error.value = null
  try {
    const response = await searchVocab(
      {
        q: q.value,
        level: level.value,
        group_id: groupId.value,
        page: page.value,
        page_size: PAGE_SIZE,
      },
      signal,
    )
    if (!signal.aborted) result.value = response
  } catch (e) {
    if (signal.aborted) return // superseded by a newer search
    result.value = null
    error.value = errorText(e)
  } finally {
    if (!signal.aborted) loading.value = false
  }
}
watch(() => [q.value, level.value, groupId.value, page.value], load, { immediate: true })
onBeforeUnmount(() => controller?.abort())

const pages = computed(() =>
  result.value ? Math.max(1, Math.ceil(result.value.total / PAGE_SIZE)) : 1,
)
function goToPage(value: number) {
  setQuery({ page: value > 1 ? value : undefined }).then(() =>
    document.getElementById('results')?.scrollIntoView?.({ block: 'start' }),
  )
}

const groupName = computed(() => groups.value.find((g) => g.id === groupId.value)?.name)
const chip = (active: boolean) =>
  active
    ? 'border-brand-600 bg-brand-600 text-white'
    : 'border-stone-300 bg-white hover:border-brand-600 dark:border-stone-700 dark:bg-stone-900'
</script>

<template>
  <section class="space-y-4">
    <h1 class="text-2xl font-bold">{{ t('lookup.title') }}</h1>

    <form role="search" class="space-y-1" @submit.prevent>
      <label for="lookup-q" class="sr-only">{{ t('lookup.searchLabel') }}</label>
      <input
        id="lookup-q"
        v-model="input"
        type="search"
        enterkeyhint="search"
        autocomplete="off"
        autocapitalize="none"
        spellcheck="false"
        :placeholder="t('lookup.placeholder')"
        class="min-h-12 w-full rounded-xl border border-stone-300 bg-white px-4 text-lg dark:border-stone-700 dark:bg-stone-900"
      />
      <p class="text-sm text-stone-500 dark:text-stone-400">{{ t('lookup.hint') }}</p>
    </form>

    <DisplayToggles />

    <!-- Browse -->
    <div v-if="browsing" class="space-y-6">
      <section aria-labelledby="by-level" class="space-y-2">
        <h2 id="by-level" class="font-semibold">{{ t('lookup.browseLevel') }}</h2>
        <ul class="grid grid-cols-3 gap-2">
          <li v-for="entry in levels" :key="entry.level">
            <button
              type="button"
              class="flex min-h-16 w-full flex-col items-center justify-center rounded-xl border border-stone-200 bg-white p-2 hover:border-brand-600 dark:border-stone-800 dark:bg-stone-900"
              @click="setQuery({ level: entry.level, page: undefined })"
            >
              <span class="text-lg font-semibold">{{ entry.level }}</span>
              <span class="text-xs text-stone-500 dark:text-stone-400">
                {{ t('lookup.words', { count: entry.count }) }}
              </span>
            </button>
          </li>
        </ul>
      </section>

      <section v-if="groups.length" aria-labelledby="by-group" class="space-y-2">
        <h2 id="by-group" class="font-semibold">{{ t('lookup.browseGroup') }}</h2>
        <ul class="space-y-2">
          <li v-for="group in groups" :key="group.id">
            <button
              type="button"
              class="flex min-h-14 w-full items-center gap-3 rounded-xl border border-stone-200 bg-white p-3 text-left hover:border-brand-600 dark:border-stone-800 dark:bg-stone-900"
              @click="setQuery({ group: group.id, page: undefined })"
            >
              <span class="min-w-0 flex-1">
                <span class="block font-medium">{{ group.name }}</span>
                <span
                  v-if="group.description"
                  class="block truncate text-sm text-stone-500 dark:text-stone-400"
                >
                  {{ group.description }}
                </span>
              </span>
              <span class="shrink-0 text-right text-xs text-stone-500 dark:text-stone-400">
                <span v-if="group.level" class="block font-semibold">{{ group.level }}</span>
                {{ t('lookup.words', { count: group.count }) }}
              </span>
            </button>
          </li>
        </ul>
      </section>
    </div>

    <!-- Results -->
    <div v-else id="results" class="space-y-3">
      <div class="flex flex-wrap items-center gap-2" role="group" :aria-label="t('lookup.level')">
        <button
          type="button"
          class="min-h-11 rounded-full border px-4 text-sm"
          :class="chip(level === null)"
          :aria-pressed="level === null"
          @click="setQuery({ level: undefined, page: undefined })"
        >
          {{ t('lookup.all') }}
        </button>
        <button
          v-for="entry in LEVELS"
          :key="entry"
          type="button"
          class="min-h-11 rounded-full border px-4 text-sm"
          :class="chip(level === entry)"
          :aria-pressed="level === entry"
          @click="setQuery({ level: entry, page: undefined })"
        >
          {{ entry }}
        </button>
      </div>

      <div v-if="groups.length" class="flex flex-wrap items-center gap-2">
        <label for="lookup-group" class="text-sm font-medium">{{ t('lookup.group') }}</label>
        <select
          id="lookup-group"
          class="min-h-11 rounded-lg border border-stone-300 bg-white px-2 text-sm dark:border-stone-700 dark:bg-stone-900"
          :value="groupId ?? ''"
          @change="
            setQuery({
              group: ($event.target as HTMLSelectElement).value || undefined,
              page: undefined,
            })
          "
        >
          <option value="">{{ t('lookup.anyGroup') }}</option>
          <option v-for="group in groups" :key="group.id" :value="group.id">
            {{ group.name }}
          </option>
        </select>
        <button type="button" class="min-h-11 px-2 text-sm underline" @click="clearFilters">
          {{ t('lookup.clearFilters') }}
        </button>
      </div>
      <button v-else type="button" class="min-h-11 text-sm underline" @click="clearFilters">
        {{ t('lookup.clearFilters') }}
      </button>

      <p v-if="result" class="text-sm text-stone-600 dark:text-stone-400" aria-live="polite">
        {{ t('lookup.results', result.total) }}<span v-if="groupName"> · {{ groupName }}</span>
      </p>

      <p v-if="loading && !result" role="status" class="py-6 text-center text-stone-500">
        {{ t('lookup.loading') }}
      </p>

      <div v-if="error" role="alert" class="space-y-2 rounded-xl border border-brand-600/40 p-4">
        <p class="text-brand-600">{{ error }}</p>
        <button
          type="button"
          class="min-h-11 rounded-lg border border-stone-300 px-4 text-sm dark:border-stone-700"
          @click="load"
        >
          {{ t('lookup.retry') }}
        </button>
      </div>

      <template v-else-if="result">
        <ul v-if="result.items.length" class="space-y-2" :class="loading ? 'opacity-60' : ''">
          <li v-for="item in result.items" :key="item.id"><WordCard :item="item" /></li>
        </ul>
        <div v-else class="space-y-1 py-6 text-center">
          <p class="font-medium">
            {{ q ? t('lookup.noResults', { q }) : t('lookup.emptyBrowse') }}
          </p>
          <p v-if="q" class="text-sm text-stone-500 dark:text-stone-400">
            {{ t('lookup.noResultsHint') }}
          </p>
        </div>

        <nav
          v-if="pages > 1"
          :aria-label="t('lookup.pagination')"
          class="flex items-center justify-between gap-2 pt-2"
        >
          <button
            type="button"
            class="min-h-11 rounded-lg border border-stone-300 px-4 text-sm disabled:opacity-50 dark:border-stone-700"
            :disabled="page <= 1"
            @click="goToPage(page - 1)"
          >
            {{ t('lookup.prev') }}
          </button>
          <span class="text-sm">{{ t('lookup.page', { page, pages }) }}</span>
          <button
            type="button"
            class="min-h-11 rounded-lg border border-stone-300 px-4 text-sm disabled:opacity-50 dark:border-stone-700"
            :disabled="page >= pages"
            @click="goToPage(page + 1)"
          >
            {{ t('lookup.next') }}
          </button>
        </nav>
      </template>
    </div>
  </section>
</template>
