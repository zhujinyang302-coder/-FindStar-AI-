import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const routes: RouteRecordRaw[] = [
  { path: '/', name: 'home', component: () => import('@/pages/HomePage.vue'), meta: { public: true } },
  { path: '/login', name: 'login', component: () => import('@/pages/LoginPage.vue'), meta: { public: true } },
  { path: '/privacy', name: 'privacy', component: () => import('@/pages/PrivacyPage.vue'), meta: { public: true } },
  {
    path: '/publish',
    name: 'publish',
    component: () => import('@/pages/PublishPage.vue'),
    meta: { requiresAuth: true }
  },
  {
    path: '/my/items',
    name: 'my-items',
    component: () => import('@/pages/MyItemsPage.vue'),
    meta: { requiresAuth: true }
  },
  {
    path: '/my/items/:type/:id',
    name: 'my-item-detail',
    component: () => import('@/pages/MyItemsPage.vue'),
    meta: { requiresAuth: true }
  },
  {
    path: '/my/matches',
    name: 'my-matches',
    component: () => import('@/pages/MyMatchesPage.vue'),
    meta: { requiresAuth: true }
  },
  {
    path: '/my/requests',
    name: 'my-requests',
    component: () => import('@/pages/MyRequestsPage.vue'),
    meta: { requiresAuth: true }
  },
  {
    path: '/matches/:batchId',
    name: 'match-result',
    component: () => import('@/pages/MatchResultPage.vue'),
    meta: { requiresAuth: true }
  },
  {
    path: '/notifications',
    name: 'notifications',
    component: () => import('@/pages/NotificationsPage.vue'),
    meta: { requiresAuth: true }
  },
  {
    path: '/admin',
    name: 'admin',
    component: () => import('@/pages/admin/AdminPage.vue'),
    meta: { requiresAuth: true, requiresAdmin: true }
  },
  {
    path: '/admin/records',
    name: 'admin-records',
    component: () => import('@/pages/admin/AdminPage.vue'),
    meta: { requiresAuth: true, requiresAdmin: true }
  },
  {
    path: '/admin/quality',
    name: 'admin-quality',
    component: () => import('@/pages/admin/QualityMetricsPage.vue'),
    meta: { requiresAuth: true, requiresAdmin: true }
  },
  { path: '/items', redirect: '/' },
  { path: '/items/:id', redirect: '/my/items' },
  { path: '/claims', redirect: '/my/requests' }
]

const router = createRouter({
  history: createWebHistory(),
  routes,
  scrollBehavior: () => ({ top: 0 })
})

router.beforeEach((to) => {
  const auth = useAuthStore()
  const isPublic = to.meta.public === true

  if (!auth.isLoggedIn && !isPublic) {
    return { name: 'login', query: { redirect: to.fullPath } }
  }
  if (auth.isLoggedIn && to.name === 'login') {
    return { name: 'home' }
  }
  if (to.meta.requiresAdmin && !auth.isAdmin) {
    return { name: 'home' }
  }
  return true
})

export default router