import { createRouter, createWebHistory } from 'vue-router'
import HomeView from '@/views/HomeView.vue'

const ComingSoon = () => import('@/views/ComingSoonView.vue')

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    { path: '/', name: 'home', component: HomeView },
    // Placeholders, replaced milestone by milestone.
    { path: '/lookup', name: 'lookup', component: ComingSoon, props: { titleKey: 'nav.lookup' } },
    {
      path: '/flashcards',
      name: 'flashcards',
      component: ComingSoon,
      props: { titleKey: 'nav.flashcards' },
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

export default router
