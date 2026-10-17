<script setup lang="ts">
import { LEVELS, type Level } from '@/api/types'

defineProps<{ modelValue: Level; label: string }>()
const emit = defineEmits<{ 'update:modelValue': [value: Level] }>()
</script>

<template>
  <div role="radiogroup" :aria-label="label" class="grid grid-cols-6 gap-1.5">
    <button
      v-for="level in LEVELS"
      :key="level"
      type="button"
      role="radio"
      :aria-checked="level === modelValue"
      class="min-h-11 rounded-lg border text-sm font-medium transition-colors"
      :class="
        level === modelValue
          ? 'border-brand-600 bg-brand-600 text-white'
          : 'border-stone-300 bg-white text-stone-700 hover:border-brand-600 dark:border-stone-700 dark:bg-stone-900 dark:text-stone-200'
      "
      @click="emit('update:modelValue', level)"
    >
      {{ level }}
    </button>
  </div>
</template>
