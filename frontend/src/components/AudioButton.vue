<script setup lang="ts">
/** Plays one audio file. Hidden when there is none; says so when the file will not play. */
import { onBeforeUnmount, ref } from 'vue'
import { useI18n } from 'vue-i18n'

const props = defineProps<{ url: string | null }>()
const { t } = useI18n()

const playing = ref(false)
const failed = ref(false)
let audio: HTMLAudioElement | null = null

function stop() {
  audio?.pause()
  playing.value = false
}

async function toggle() {
  if (playing.value) return stop()
  if (!props.url) return
  failed.value = false
  if (!audio || audio.src !== new URL(props.url, document.baseURI).href) {
    audio?.pause()
    audio = new Audio(props.url)
    audio.addEventListener('ended', () => (playing.value = false))
    audio.addEventListener('error', () => {
      playing.value = false
      failed.value = true
    })
  }
  audio.currentTime = 0
  playing.value = true
  try {
    await audio.play()
  } catch {
    playing.value = false
    failed.value = true
  }
}

onBeforeUnmount(stop)
</script>

<template>
  <button
    v-if="url"
    type="button"
    class="inline-flex size-11 shrink-0 items-center justify-center rounded-full border border-stone-300 text-lg dark:border-stone-700"
    :class="failed ? 'text-stone-400' : ''"
    :aria-label="failed ? t('vocab.audioFailed') : playing ? t('vocab.stop') : t('vocab.play')"
    :title="failed ? t('vocab.audioFailed') : undefined"
    :aria-pressed="playing"
    @click="toggle"
  >
    <span aria-hidden="true">{{ failed ? '⚠' : playing ? '■' : '▶' }}</span>
  </button>
</template>
