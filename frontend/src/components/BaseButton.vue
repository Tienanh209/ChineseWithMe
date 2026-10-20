<script setup lang="ts">
withDefaults(
  defineProps<{
    variant?: 'primary' | 'secondary' | 'danger'
    type?: 'button' | 'submit'
    loading?: boolean
    disabled?: boolean
  }>(),
  { variant: 'primary', type: 'button' },
)

const styles = {
  primary: 'bg-brand-600 text-white hover:bg-brand-700',
  secondary:
    'border border-stone-300 bg-white hover:border-brand-600 dark:border-stone-700 dark:bg-stone-900',
  danger: 'bg-brand-700 text-white hover:bg-brand-600',
}
</script>

<template>
  <button
    :type="type"
    :disabled="disabled || loading"
    :aria-busy="loading || undefined"
    class="min-h-11 rounded-lg px-4 text-sm font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-60"
    :class="styles[variant]"
  >
    <slot />
  </button>
</template>
