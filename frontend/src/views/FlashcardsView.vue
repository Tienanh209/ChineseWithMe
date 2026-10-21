<script setup lang="ts">
import { computed, onBeforeUnmount, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { RouterLink } from 'vue-router'
import { ApiError } from '@/api/client'
import {
  getSession,
  getStats,
  submitReview,
  type Rating,
  type SessionResponse,
  type Stats,
} from '@/api/flashcards'
import { LEVELS, type Level } from '@/api/types'
import { getGroups, type VocabGroup } from '@/api/vocab'
import BaseButton from '@/components/BaseButton.vue'
import DisplayToggles from '@/components/DisplayToggles.vue'
import FlashCard from '@/components/FlashCard.vue'
import { errorText } from '@/lib/errors'
import * as queue from '@/lib/studyQueue'

const { t } = useI18n()

type Phase = 'start' | 'loading' | 'studying' | 'finished'
const phase = ref<Phase>('loading')
const stats = ref<Stats | null>(null)
const groups = ref<VocabGroup[]>([])
const error = ref<string | null>(null)
const level = ref<Level | null>(null)
const groupId = ref<number | null>(null)

const session = ref<SessionResponse | null>(null)
const study = ref<queue.Queue>(queue.startQueue([]))
const revealed = ref(false)
const saving = ref(false)
const saveError = ref<string | null>(null)
const now = ref(new Date())
const emptyReason = ref<'list' | 'limit' | 'filter' | 'due' | null>(null)

const filtering = computed(() => level.value !== null || groupId.value !== null)
const card = computed(() => queue.current(study.value))
const available = computed(() =>
  stats.value ? stats.value.due_now + stats.value.new_available : 0,
)

const controller = new AbortController()
onBeforeUnmount(() => controller.abort())

async function loadStats() {
  error.value = null
  try {
    stats.value = await getStats(controller.signal)
    phase.value = 'start'
  } catch (e) {
    if (controller.signal.aborted) return
    error.value = errorText(e)
    phase.value = 'start'
  }
}
loadStats()
getGroups(controller.signal)
  .then((value) => (groups.value = value))
  .catch(() => {}) // the filter is optional

async function start() {
  error.value = null
  emptyReason.value = null
  phase.value = 'loading'
  try {
    const response = await getSession(
      { level: level.value, group_id: groupId.value },
      controller.signal,
    )
    if (controller.signal.aborted) return
    session.value = response
    now.value = new Date()
    if (response.cards.length === 0) {
      emptyReason.value =
        stats.value?.total_cards === 0
          ? 'list'
          : response.new_waiting > 0 && response.new_allowance === 0
            ? 'limit'
            : filtering.value
              ? 'filter'
              : 'due'
      phase.value = 'start'
      return
    }
    study.value = queue.startQueue(response.cards)
    revealed.value = false
    saveError.value = null
    phase.value = 'studying'
  } catch (e) {
    if (controller.signal.aborted) return
    error.value = errorText(e)
    phase.value = 'start'
  }
}

async function rate(rating: Rating) {
  const current = card.value
  if (!current || saving.value) return
  saving.value = true
  saveError.value = null
  try {
    await submitReview(current.vocabulary_id, rating)
    study.value = queue.answer(study.value, rating)
  } catch (e) {
    if (e instanceof ApiError && (e.code === 'not_due' || e.code === 'not_in_study_list')) {
      study.value = queue.skip(study.value) // already answered elsewhere, or removed: move on
    } else {
      saveError.value = errorText(e)
      saving.value = false
      return // keep the card on screen so the answer can be sent again
    }
  }
  saving.value = false
  revealed.value = false
  if (queue.isDone(study.value)) finish()
}

async function finish() {
  phase.value = 'finished'
  try {
    stats.value = await getStats(controller.signal)
  } catch {
    /* the summary does not need fresh numbers */
  }
}

function stop() {
  phase.value = 'loading'
  loadStats()
}

const chip = (active: boolean) =>
  active
    ? 'border-brand-600 bg-brand-600 text-white'
    : 'border-stone-300 bg-white hover:border-brand-600 dark:border-stone-700 dark:bg-stone-900'
const progressPercent = computed(() =>
  study.value.total ? Math.round((study.value.finished / study.value.total) * 100) : 0,
)
const recallPercent = computed(() => queue.recall(study.value))
</script>

<template>
  <section class="space-y-5">
    <h1 class="text-2xl font-bold">{{ t('cards.title') }}</h1>

    <p v-if="phase === 'loading'" role="status" class="py-8 text-center text-stone-500">
      {{ t('cards.loading') }}
    </p>

    <!-- Start -->
    <template v-else-if="phase === 'start'">
      <div v-if="error" role="alert" class="space-y-2 rounded-xl border border-brand-600/40 p-4">
        <p class="text-brand-600">{{ error }}</p>
        <BaseButton variant="secondary" @click="stats ? start() : loadStats()">{{
          t('cards.retry')
        }}</BaseButton>
      </div>

      <template v-if="stats">
        <dl class="grid grid-cols-2 gap-2 sm:grid-cols-4">
          <div
            v-for="tile in [
              { key: 'due', value: stats.due_now, text: String(stats.due_now) },
              { key: 'new', value: stats.new_available, text: String(stats.new_available) },
              { key: 'today', value: stats.reviewed_today, text: String(stats.reviewed_today) },
              {
                key: 'streak',
                value: stats.streak_days,
                text: t('cards.streakDays', stats.streak_days),
              },
            ]"
            :key="tile.key"
            class="rounded-xl border border-stone-200 bg-white p-3 dark:border-stone-800 dark:bg-stone-900"
          >
            <dt class="text-xs text-stone-500 dark:text-stone-400">{{ t(`cards.${tile.key}`) }}</dt>
            <dd class="text-xl font-semibold" :data-testid="`stat-${tile.key}`">{{ tile.text }}</dd>
          </div>
        </dl>
        <p class="text-sm text-stone-600 dark:text-stone-400">
          {{ t('cards.newOfLimit', { done: stats.new_today, limit: stats.daily_new_cards }) }}
        </p>

        <section v-if="stats.total_cards > 0" class="space-y-3" :aria-label="t('cards.filters')">
          <h2 class="font-semibold">{{ t('cards.filters') }}</h2>
          <div class="flex flex-wrap gap-2" role="group" :aria-label="t('cards.level')">
            <button
              type="button"
              class="min-h-11 rounded-full border px-4 text-sm"
              :class="chip(level === null)"
              :aria-pressed="level === null"
              @click="level = null"
            >
              {{ t('cards.all') }}
            </button>
            <button
              v-for="entry in LEVELS"
              :key="entry"
              type="button"
              class="min-h-11 rounded-full border px-4 text-sm"
              :class="chip(level === entry)"
              :aria-pressed="level === entry"
              @click="level = entry"
            >
              {{ entry }}
            </button>
          </div>
          <div v-if="groups.length" class="flex flex-wrap items-center gap-2">
            <label for="cards-group" class="text-sm font-medium">{{ t('cards.group') }}</label>
            <select
              id="cards-group"
              class="min-h-11 rounded-lg border border-stone-300 bg-white px-2 text-sm dark:border-stone-700 dark:bg-stone-900"
              :value="groupId ?? ''"
              @change="groupId = Number(($event.target as HTMLSelectElement).value) || null"
            >
              <option value="">{{ t('cards.anyGroup') }}</option>
              <option v-for="group in groups" :key="group.id" :value="group.id">
                {{ group.name }}
              </option>
            </select>
          </div>
        </section>

        <div class="space-y-3">
          <BaseButton class="w-full sm:w-auto" :disabled="stats.total_cards === 0" @click="start">
            {{
              filtering
                ? t('cards.start')
                : available > 0
                  ? t('cards.study', available)
                  : t('cards.start')
            }}
          </BaseButton>
        </div>

        <div
          v-if="emptyReason || stats.total_cards === 0"
          role="status"
          class="space-y-2 rounded-xl border border-stone-200 p-4 dark:border-stone-800"
        >
          <p class="font-medium">
            {{ stats.total_cards === 0 ? t('cards.emptyList') : t('cards.emptyTitle') }}
          </p>
          <p v-if="emptyReason === 'limit'" class="text-sm">
            {{ t('cards.limitReached', { n: stats.daily_new_cards }) }}
          </p>
          <p v-else-if="emptyReason === 'filter'" class="text-sm">
            {{ t('cards.nothingForFilter') }}
          </p>
          <p v-else-if="emptyReason === 'due'" class="text-sm">{{ t('cards.nothingDue') }}</p>
          <RouterLink
            v-if="stats.total_cards === 0"
            :to="{ name: 'lookup' }"
            class="inline-flex min-h-11 items-center underline"
          >
            {{ t('cards.openLookup') }}
          </RouterLink>
          <RouterLink
            v-else-if="emptyReason === 'limit'"
            :to="{ name: 'profile' }"
            class="inline-flex min-h-11 items-center underline"
          >
            {{ t('cards.openProfile') }}
          </RouterLink>
        </div>
      </template>
    </template>

    <!-- Studying -->
    <template v-else-if="phase === 'studying' && card">
      <div class="flex items-center gap-3">
        <div
          class="h-2 flex-1 overflow-hidden rounded-full bg-stone-200 dark:bg-stone-800"
          role="progressbar"
          :aria-valuenow="progressPercent"
          aria-valuemin="0"
          aria-valuemax="100"
          :aria-label="t('cards.progress', { done: study.finished, total: study.total })"
        >
          <div
            class="h-full bg-brand-600 transition-all"
            :style="{ width: `${progressPercent}%` }"
          />
        </div>
        <span class="text-sm tabular-nums" data-testid="progress">{{
          t('cards.progress', { done: study.finished, total: study.total })
        }}</span>
        <button type="button" class="min-h-11 px-2 text-sm underline" @click="stop">
          {{ t('cards.stop') }}
        </button>
      </div>
      <DisplayToggles />
      <FlashCard
        :key="card.vocabulary_id + '-' + study.answers"
        :card="card"
        :revealed="revealed"
        :busy="saving"
        :now="now"
        @reveal="revealed = true"
        @rate="rate"
      />
      <p v-if="saving" role="status" class="text-center text-sm text-stone-500">
        {{ t('cards.saving') }}
      </p>
      <div
        v-if="saveError"
        role="alert"
        class="space-y-2 rounded-xl border border-brand-600/40 p-3 text-center"
      >
        <p class="text-sm text-brand-600">{{ t('cards.saveFailed') }} {{ saveError }}</p>
        <p class="text-xs">{{ t('cards.retry') }}</p>
      </div>
    </template>

    <!-- Finished -->
    <template v-else-if="phase === 'finished'">
      <div
        class="space-y-3 rounded-2xl border border-stone-200 bg-white p-6 text-center dark:border-stone-800 dark:bg-stone-900"
        role="status"
      >
        <p class="text-4xl" aria-hidden="true">🎉</p>
        <h2 class="text-xl font-semibold">{{ t('cards.finishedTitle') }}</h2>
        <p>
          {{ t('cards.finishedSummary', { finished: study.finished, answers: study.answers }) }}
        </p>
        <p v-if="recallPercent !== null" class="text-stone-600 dark:text-stone-400">
          {{ t('cards.remembered', { pct: recallPercent })
          }}<span v-if="study.again"> · {{ t('cards.againCount', { n: study.again }) }}</span>
        </p>
        <p v-if="stats" class="text-stone-600 dark:text-stone-400">
          {{ t('cards.streakDays', stats.streak_days) }}
        </p>
      </div>
      <div class="flex flex-wrap gap-2">
        <BaseButton @click="start">{{ t('cards.studyMore') }}</BaseButton>
        <BaseButton variant="secondary" @click="stop">{{ t('cards.back') }}</BaseButton>
      </div>
    </template>
  </section>
</template>
