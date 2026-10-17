<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { RouterLink } from 'vue-router'

const { t } = useI18n()

const items = [
  { to: '/lookup', key: 'nav.lookup', icon: '查' },
  { to: '/flashcards', key: 'nav.flashcards', icon: '卡' },
  { to: '/lessons', key: 'nav.lessons', icon: '課' },
  { to: '/games', key: 'nav.games', icon: '玩' },
  { to: '/progress', key: 'nav.progress', icon: '進' },
]
</script>

<template>
  <!-- Bottom tab bar on phones, a row under the header on wider screens. -->
  <nav
    :aria-label="t('nav.main')"
    class="fixed inset-x-0 bottom-0 z-10 border-t border-stone-200 bg-white pb-[env(safe-area-inset-bottom)] sm:static sm:border-t-0 sm:border-b sm:bg-transparent dark:border-stone-800 dark:bg-stone-900 sm:dark:bg-transparent"
  >
    <ul class="mx-auto grid max-w-3xl grid-cols-5 sm:flex sm:gap-1 sm:px-4">
      <li v-for="item in items" :key="item.to">
        <RouterLink
          :to="item.to"
          class="flex min-h-14 flex-col items-center justify-center gap-0.5 px-2 text-xs text-stone-500 sm:min-h-11 sm:flex-row sm:gap-1.5 sm:text-sm dark:text-stone-400"
          active-class="!text-brand-600 font-medium"
        >
          <span lang="zh-Hant" aria-hidden="true" class="text-lg leading-none sm:text-base">{{
            item.icon
          }}</span>
          <span>{{ t(item.key) }}</span>
        </RouterLink>
      </li>
    </ul>
  </nav>
</template>
