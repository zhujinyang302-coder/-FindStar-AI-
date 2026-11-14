<script setup lang="ts">
defineProps<{
  loading?: boolean
  error?: string | null
  empty?: boolean
  emptyText?: string
}>()

const emit = defineEmits<{ (e: 'retry'): void }>()
</script>

<template>
  <div class="state-block">
    <el-skeleton v-if="loading" :rows="4" animated />
    <el-alert v-else-if="error" type="error" :title="error" show-icon :closable="false">
      <template #default>
        <el-button size="small" type="primary" plain @click="emit('retry')">重试</el-button>
      </template>
    </el-alert>
    <el-empty v-else-if="empty" :description="emptyText || '暂无数据'">
      <slot name="empty-action" />
    </el-empty>
    <slot v-else />
  </div>
</template>