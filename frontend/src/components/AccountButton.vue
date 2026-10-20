<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { RouterLink } from 'vue-router'
import { useSessionStore } from '@/stores/session'

const { t } = useI18n()
const session = useSessionStore()

const initial = computed(() => {
  const me = session.me
  return me ? [...(me.display_name || me.username || me.email)][0]?.toUpperCase() : null
})
</script>

<template>
  <RouterLink
    :to="session.me ? { name: 'profile' } : { name: 'login' }"
    :aria-label="session.me ? t('account.menu') : t('account.signIn')"
    :title="session.me ? t('account.menu') : t('account.signIn')"
    class="flex size-11 shrink-0 items-center justify-center overflow-hidden rounded-full border border-stone-300 bg-white text-sm font-semibold dark:border-stone-700 dark:bg-stone-900"
  >
    <img
      v-if="session.me?.avatar_url"
      :src="session.me.avatar_url"
      alt=""
      referrerpolicy="no-referrer"
      class="size-full object-cover"
    />
    <span v-else-if="initial">{{ initial }}</span>
    <span v-else lang="zh-Hant" aria-hidden="true" class="text-lg">人</span>
  </RouterLink>
</template>
