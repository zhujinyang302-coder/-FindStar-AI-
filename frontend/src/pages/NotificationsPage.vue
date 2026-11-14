<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import {
  fetchNotifications,
  markAllNotificationsRead,
  markNotificationRead
} from '@/api'
import StateBlock from '@/components/StateBlock.vue'
import { formatDateTime } from '@/utils/format'
import type { NotificationItem } from '@/types'

const items = ref<NotificationItem[]>([])
const unread = ref(0)
const loading = ref(false)
const error = ref<string | null>(null)

async function load() {
  loading.value = true
  error.value = null
  try {
    const result = await fetchNotifications({ page: 1, page_size: 50 })
    items.value = result.items
    unread.value = result.unread_count
  } catch (err) {
    error.value = (err as Error).message
  } finally {
    loading.value = false
  }
}

async function readOne(item: NotificationItem) {
  if (item.is_read) return
  try {
    await markNotificationRead(item.id)
    item.is_read = true
    unread.value = Math.max(0, unread.value - 1)
  } catch {
    // handled
  }
}

async function readAll() {
  try {
    const result = await markAllNotificationsRead()
    items.value.forEach((item) => (item.is_read = true))
    unread.value = 0
    ElMessage.success(`已将 ${result.updated} 条通知标记为已读`)
  } catch {
    // handled
  }
}

onMounted(load)
</script>

<template>
  <section>
    <div class="head">
      <h2 class="section-title">通知</h2>
      <el-button :disabled="unread === 0" @click="readAll">全部已读</el-button>
    </div>
    <StateBlock
      :loading="loading"
      :error="error"
      :empty="items.length === 0"
      empty-text="暂无通知"
      @retry="load"
    >
      <el-card
        v-for="item in items"
        :key="item.id"
        class="notice"
        :class="{ unread: !item.is_read }"
        shadow="never"
        @click="readOne(item)"
      >
        <div class="row">
          <strong>{{ item.title }}</strong>
          <span class="muted">{{ formatDateTime(item.created_at) }}</span>
        </div>
        <p class="body">{{ item.body }}</p>
        <el-tag v-if="!item.is_read" size="small" type="danger">未读</el-tag>
      </el-card>
    </StateBlock>
  </section>
</template>

<style scoped>
.head {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.notice {
  margin-bottom: 10px;
  cursor: pointer;
}
.notice.unread {
  border-left: 3px solid #3b5bdb;
}
.row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
}
.body {
  margin: 8px 0;
  color: #4b5563;
}
.muted {
  color: #9ca3af;
  font-size: 13px;
}
</style>