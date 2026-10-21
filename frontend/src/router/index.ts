import { createRouter, createWebHistory } from 'vue-router'
import { rememberLookup } from '@/lib/lastLookup'
import { safeNext } from '@/lib/redirect'
import { useSessionStore } from '@/stores/session'
import HomeView from '@/views/HomeView.vue'

const ComingSoon = () => import('@/views/ComingSoonView.vue')

declare module 'vue-router' {
  interface RouteMeta {
    requiresAuth?: boolean
    /** Sign-in and register pages: skipped when already signed in. */
    guestOnly?: boolean
  }
}

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    { path: '/', name: 'home', component: HomeView },
    {
      path: '/login',
      name: 'login',
      component: () => import('@/views/AuthView.vue'),
      meta: { guestOnly: true },
    },
    {
      path: '/register',
      name: 'register',
      component: () => import('@/views/AuthView.vue'),
      meta: { guestOnly: true },
    },
    {
      path: '/verify-email',
      name: 'verify-email',
      component: () => import('@/views/VerifyEmailView.vue'),
    },
    {
      path: '/forgot-password',
      name: 'forgot-password',
      component: () => import('@/views/ForgotPasswordView.vue'),
    },
    {
      path: '/reset-password',
      name: 'reset-password',
      component: () => import('@/views/ResetPasswordView.vue'),
    },
    {
      path: '/profile',
      name: 'profile',
      component: () => import('@/views/ProfileView.vue'),
      meta: { requiresAuth: true },
    },
    // Placeholders, replaced milestone by milestone.
    { path: '/lookup', name: 'lookup', component: () => import('@/views/LookupView.vue') },
    {
      path: '/vocab/:id(\\d+)',
      name: 'vocab',
      component: () => import('@/views/VocabDetailView.vue'),
      props: (route) => ({ id: Number(route.params.id) }),
    },
    {
      path: '/flashcards',
      name: 'flashcards',
      component: () => import('@/views/FlashcardsView.vue'),
      meta: { requiresAuth: true },
    },
    {
      path: '/lessons',
      name: 'lessons',
      component: ComingSoon,
      props: { titleKey: 'nav.lessons' },
    },
    { path: '/games', name: 'games', component: ComingSoon, props: { titleKey: 'nav.games' } },
    {
      path: '/progress',
      name: 'progress',
      component: ComingSoon,
      props: { titleKey: 'nav.progress' },
    },
    { path: '/:pathMatch(.*)*', redirect: '/' },
  ],
})

router.beforeEach(async (to) => {
  if (!to.meta.requiresAuth && !to.meta.guestOnly) return
  const session = useSessionStore()
  await session.ensureLoaded().catch(() => {}) // API down: treat as signed out
  if (to.meta.requiresAuth && !session.me) {
    return { name: 'login', query: { next: to.fullPath } }
  }
  if (to.meta.guestOnly && session.me) return safeNext(to.query.next) ?? '/'
})

router.afterEach((to) => {
  if (to.name === 'lookup') rememberLookup(to.fullPath)
})

export default router
