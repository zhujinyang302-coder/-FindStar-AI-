<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { fetchUnreadCount } from '@/api'

type NavItem = {
  key: string
  label: string
  short: string
  path: string
  query?: Record<string, string>
  badge?: boolean
}

const auth = useAuthStore()
const route = useRoute()
const router = useRouter()

const unread = ref(0)
const collapsed = ref(false)
const mobileOpen = ref(false)
const isMobile = ref(false)

const COLLAPSE_KEY = 'findstar.layout.collapsed'

function readCollapsed(): boolean {
  try {
    return localStorage.getItem(COLLAPSE_KEY) === '1'
  } catch {
    return false
  }
}

const userNav: NavItem[] = [
  { key: 'home', label: '首页', short: '首', path: '/' },
  { key: 'items', label: '我的记录', short: '记', path: '/my/items' },
  { key: 'matches', label: '我的匹配', short: '配', path: '/my/matches' },
  { key: 'requests', label: '我的申请', short: '申', path: '/my/requests' },
  { key: 'notifications', label: '通知', short: '通', path: '/notifications', badge: true }
]

const adminNav: NavItem[] = [
  { key: 'home', label: '首页', short: '首', path: '/' },
  { key: 'records', label: '记录管理', short: '录', path: '/admin/records' },
  { key: 'delisting', label: '下架审核', short: '下', path: '/admin' },
  { key: 'history', label: '审核历史', short: '史', path: '/admin', query: { tab: 'history' } },
  { key: 'quality', label: '质量指标', short: '质', path: '/admin/quality' }
]

const navItems = computed(() => (auth.isAdmin ? adminNav : userNav))

const pageTitle = computed(() => {
  const path = route.path
  if (path === '/') return '首页'
  if (path.startsWith('/my/items')) return '我的记录'
  if (path.startsWith('/my/matches') || path.startsWith('/matches/')) return '我的匹配'
  if (path.startsWith('/my/requests')) return '我的申请'
  if (path.startsWith('/notifications')) return '通知'
  if (path.startsWith('/admin/records')) return '记录管理'
  if (path.startsWith('/admin/quality')) return '质量指标'
  if (path.startsWith('/admin')) return route.query.tab === 'history' ? '审核历史' : '下架审核'
  if (path.startsWith('/publish')) return '发布记录'
  return '寻物星图'
})

function isActive(item: NavItem): boolean {
  const path = route.path
  if (item.key === 'home') return path === '/'
  if (item.key === 'items') return path.startsWith('/my/items')
  if (item.key === 'matches') return path.startsWith('/my/matches') || path.startsWith('/matches/')
  if (item.key === 'requests') return path.startsWith('/my/requests')
  if (item.key === 'notifications') return path.startsWith('/notifications')
  if (item.key === 'records') return path.startsWith('/admin/records')
  if (item.key === 'quality') return path.startsWith('/admin/quality')
  if (item.key === 'history') return path === '/admin' && route.query.tab === 'history'
  if (item.key === 'delisting') return path === '/admin' && route.query.tab !== 'history'
  return false
}

function go(item: NavItem) {
  mobileOpen.value = false
  if (item.query) {
    router.push({ path: item.path, query: item.query })
  } else {
    router.push(item.path)
  }
}

function toggleCollapse() {
  collapsed.value = !collapsed.value
  try {
    localStorage.setItem(COLLAPSE_KEY, collapsed.value ? '1' : '0')
  } catch {
    // 本地存储不可用时仅保留当前会话状态
  }
}

function handleResize() {
  isMobile.value = window.innerWidth < 768
  if (!isMobile.value) mobileOpen.value = false
}

async function loadUnread() {
  if (!auth.isLoggedIn || auth.isAdmin) return
  try {
    const result = await fetchUnreadCount()
    unread.value = result.unread_count
  } catch {
    unread.value = 0
  }
}

function logout() {
  auth.logout()
  router.push('/')
}

onMounted(() => {
  collapsed.value = readCollapsed()
  handleResize()
  window.addEventListener('resize', handleResize)
  loadUnread()
})

onUnmounted(() => {
  window.removeEventListener('resize', handleResize)
})

watch(() => route.fullPath, loadUnread)
</script>

<template>
  <el-container class="app-shell">
    <el-aside
      v-if="!isMobile"
      class="app-aside"
      :class="{ collapsed }"
      :width="collapsed ? '68px' : '210px'"
    >
      <div class="brand">
        <span class="brand-mark">星</span>
        <span v-if="!collapsed" class="brand-text">寻物星图 <em>FindStar</em></span>
      </div>

      <nav class="side-nav" aria-label="主导航">
        <button
          v-for="item in navItems"
          :key="item.key"
          type="button"
          class="nav-item"
          :class="{ active: isActive(item) }"
          :aria-label="item.label"
          :aria-current="isActive(item) ? 'page' : undefined"
          @click="go(item)"
        >
          <span class="nav-icon" aria-hidden="true">{{ item.short }}</span>
          <span v-if="!collapsed" class="nav-label">{{ item.label }}</span>
          <el-badge
            v-if="item.badge && unread > 0"
            :value="unread"
            class="nav-badge"
          />
        </button>
      </nav>

      <button type="button" class="collapse-btn" @click="toggleCollapse">
        {{ collapsed ? '展开' : '收起' }}
      </button>
    </el-aside>

    <el-drawer
      v-model="mobileOpen"
      direction="ltr"
      size="220px"
      :with-header="false"
      class="mobile-drawer"
    >
      <div class="brand">
        <span class="brand-mark">星</span>
        <span class="brand-text">寻物星图 <em>FindStar</em></span>
      </div>
      <nav class="side-nav" aria-label="主导航">
        <button
          v-for="item in navItems"
          :key="item.key"
          type="button"
          class="nav-item"
          :class="{ active: isActive(item) }"
          :aria-label="item.label"
          @click="go(item)"
        >
          <span class="nav-icon" aria-hidden="true">{{ item.short }}</span>
          <span class="nav-label">{{ item.label }}</span>
          <el-badge
            v-if="item.badge && unread > 0"
            :value="unread"
            class="nav-badge"
          />
        </button>
      </nav>
    </el-drawer>

    <el-container class="app-body">
      <el-header class="app-header" height="56px">
        <div class="header-left">
          <el-button v-if="isMobile" text class="menu-btn" @click="mobileOpen = true">
            菜单
          </el-button>
          <span class="page-title">{{ pageTitle }}</span>
        </div>
        <div class="account">
          <span v-if="auth.isLoggedIn" class="nickname">{{ auth.user?.nickname }}</span>
          <el-tag v-if="auth.isAdmin" size="small" type="warning">管理员</el-tag>
          <el-button v-if="auth.isLoggedIn" link type="primary" @click="logout">退出</el-button>
          <el-button v-else link type="primary" @click="router.push('/login')">登录</el-button>
        </div>
      </el-header>

      <el-main class="app-main">
        <slot />
      </el-main>

      <el-footer class="app-footer" height="auto">
        寻物星图 FindStar · 匹配分数由后端算法计算，仅用于推荐候选，不代表物品归属或找回概率
      </el-footer>
    </el-container>
  </el-container>
</template>

<style scoped>
.app-shell {
  min-height: 100vh;
  background: #f6f7fb;
}

.app-aside {
  display: flex;
  flex-direction: column;
  background: #111827;
  color: #e5e7eb;
  transition: width 0.2s ease;
  position: sticky;
  top: 0;
  height: 100vh;
  overflow: hidden;
}

.brand {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 18px 16px 14px;
  font-weight: 600;
  white-space: nowrap;
}

.brand-mark {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  border-radius: 9px;
  background: #6366f1;
  color: #fff;
  flex: none;
}

.brand-text em {
  font-style: normal;
  color: #9ca3af;
  font-size: 12px;
  margin-left: 4px;
}

.side-nav {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 8px;
  flex: 1;
}

.nav-item {
  display: flex;
  align-items: center;
  gap: 10px;
  width: 100%;
  border: 0;
  background: transparent;
  color: #cbd5e1;
  padding: 10px 12px;
  border-radius: 9px;
  cursor: pointer;
  font-size: 14px;
  text-align: left;
  white-space: nowrap;
}

.nav-item:hover {
  background: rgba(255, 255, 255, 0.08);
  color: #fff;
}

.nav-item.active {
  background: #4f46e5;
  color: #fff;
}

.nav-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 22px;
  height: 22px;
  border-radius: 6px;
  background: rgba(255, 255, 255, 0.12);
  font-size: 12px;
  flex: none;
}

.nav-label {
  overflow: hidden;
  text-overflow: ellipsis;
}

.nav-badge {
  margin-left: auto;
}

.collapse-btn {
  margin: 8px;
  border: 1px solid rgba(255, 255, 255, 0.18);
  background: transparent;
  color: #cbd5e1;
  border-radius: 8px;
  padding: 8px;
  cursor: pointer;
}

.collapsed .nav-item {
  justify-content: center;
  padding: 10px 0;
}

.collapsed .nav-label,
.collapsed .brand-text {
  display: none;
}

.app-body {
  min-width: 0;
}

.app-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  background: #fff;
  border-bottom: 1px solid #eef0f4;
  padding: 0 20px;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.page-title {
  font-weight: 600;
  color: #111827;
}

.account {
  display: flex;
  align-items: center;
  gap: 10px;
}

.nickname {
  color: #374151;
}

.app-main {
  padding: 20px;
  min-width: 0;
}

.app-footer {
  text-align: center;
  color: #9ca3af;
  font-size: 12px;
  padding: 12px;
}

.mobile-drawer :deep(.el-drawer__body) {
  padding: 0;
  background: #111827;
}

:deep(.mobile-drawer) {
  background: #111827;
}

@media (max-width: 767px) {
  .app-main {
    padding: 14px;
  }
  .page-title {
    font-size: 15px;
  }
}
</style>