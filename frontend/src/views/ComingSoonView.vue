<script setup lang="ts">
import { useI18n } from 'vue-i18n'

defineProps<{ titleKey: string }>()
const { t } = useI18n()
</script>

<template>
  <section>
    <h1 class="text-2xl font-bold">{{ t(titleKey) }}</h1>
    <p class="mt-2 text-stone-600 dark:text-stone-400">{{ t('comingSoon') }}</p>
  </section>
</template>
