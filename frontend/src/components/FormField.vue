<script setup lang="ts">
import { computed, useId } from 'vue'

const props = withDefaults(
  defineProps<{
    modelValue: string
    label: string
    type?: string
    autocomplete?: string
    hint?: string
    error?: string
    required?: boolean
    maxlength?: number
    inputmode?: 'text' | 'email' | 'url' | 'numeric'
  }>(),
  { type: 'text' },
)
defineEmits<{ 'update:modelValue': [value: string] }>()

const id = useId()
const describedBy = computed(() =>
  [props.hint ? `${id}-hint` : '', props.error ? `${id}-error` : ''].filter(Boolean).join(' '),
)
</script>

<template>
  <div class="space-y-1">
    <label :for="id" class="block text-sm font-medium">{{ label }}</label>
    <input
      :id="id"
      :value="modelValue"
      :type="type"
      :autocomplete="autocomplete"
      :required="required"
      :maxlength="maxlength"
      :inputmode="inputmode"
      :aria-invalid="error ? true : undefined"
      :aria-describedby="describedBy || undefined"
      autocapitalize="none"
      spellcheck="false"
      class="min-h-11 w-full rounded-lg border border-stone-300 bg-white px-3 text-base dark:border-stone-700 dark:bg-stone-900"
      :class="error ? 'border-brand-600' : ''"
      @input="$emit('update:modelValue', ($event.target as HTMLInputElement).value)"
    />
    <p v-if="hint" :id="`${id}-hint`" class="text-xs text-stone-500 dark:text-stone-400">
      {{ hint }}
    </p>
    <p v-if="error" :id="`${id}-error`" role="alert" class="text-sm text-brand-600">{{ error }}</p>
  </div>
</template>
