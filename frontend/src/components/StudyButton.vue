<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { RouterLink, useRoute } from 'vue-router'
import { addToStudyList } from '@/api/vocab'
import { errorText } from '@/lib/errors'
import { useSessionStore } from '@/stores/session'
import BaseButton from './BaseButton.vue'

const props = defineProps<{ vocabId: number; studying: boolean }>()
const emit = defineEmits<{ added: [] }>()

const { t } = useI18n()
const route = useRoute()
const session = useSessionStore()

const inList = ref(props.studying)
const busy = ref(false)
const error = ref<string | null>(null)
watch(
  () => [props.vocabId, props.studying] as const,
  () => {
    inList.value = props.studying
    error.value = null
  },
)

const signInTarget = computed(() => ({ name: 'login', query: { next: route.fullPath } }))

async function add() {
  busy.value = true
  error.value = null
  try {
    await addToStudyList(props.vocabId)
    inList.value = true
    emit('added')
  } catch (e) {
    error.value = errorText(e)
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <div class="space-y-1">
    <p
      v-if="inList"
      role="status"
      class="inline-flex min-h-11 items-center gap-2 text-sm font-medium"
    >
      <span aria-hidden="true" class="text-emerald-600 dark:text-emerald-400">✓</span>
      {{ t('vocab.inList') }}
    </p>
    <RouterLink
      v-else-if="!session.me"
      :to="signInTarget"
      class="inline-flex min-h-11 items-center rounded-lg border border-stone-300 px-4 text-sm font-medium dark:border-stone-700"
    >
      {{ t('vocab.signInToAdd') }}
    </RouterLink>
    <BaseButton v-else :loading="busy" @click="add">
      {{ busy ? t('vocab.adding') : t('vocab.addToStudy') }}
    </BaseButton>
    <p v-if="error" role="alert" class="text-sm text-brand-600">{{ error }}</p>
  </div>
</template>
