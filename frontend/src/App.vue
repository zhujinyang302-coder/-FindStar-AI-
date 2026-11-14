<script setup lang="ts">
import DefaultLayout from '@/layouts/DefaultLayout.vue'
import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()
</script>

<template>
  <!-- 未登录：只渲染登录页，不展示导航与任何业务功能 -->
  <DefaultLayout v-if="auth.isLoggedIn">
    <router-view />
  </DefaultLayout>
  <router-view v-else />
</template>