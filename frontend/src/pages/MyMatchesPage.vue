<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { fetchMyBatches } from '@/api'
import StateBlock from '@/components/StateBlock.vue'
import { formatDateTime, statusLabel, statusTagType } from '@/utils/format'
import type { MyBatchItem } from '@/types'

const router = useRouter()
const batches = ref<MyBatchItem[]>([])
const loading = ref(false)
const error = ref<string | null>(null)

async function load() {
  loading.value = true
  error.value = null
  try {
    const result = await fetchMyBatches({ page: 1, page_size: 50 })
    batches.value = result.items
  } catch (err) {
    error.value = (err as Error).message
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<template>
  <section>
    <h2 class="section-title">我的匹配</h2>
    <StateBlock
      :loading="loading"
      :error="error"
      :empty="batches.length === 0"
      empty-text="还没有发起过匹配，请到「我的记录」选择已上架记录发起匹配"
      @retry="load"
    >
      <el-card v-for="batch in batches" :key="batch.batch_id" class="batch" shadow="hover">
        <div class="row">
          <div>
            <el-tag :type="statusTagType(batch.status)" size="small">{{ statusLabel(batch.status) }}</el-tag>
            <el-tag v-if="batch.degraded" type="warning" size="small" class="tag">降级</el-tag>
            <span class="muted">
              {{ batch.initiated_item_type === 'lost' ? '寻物记录' : '拾获记录' }} #{{ batch.initiated_item_id }}
            </span>
          </div>
          <div class="right">
            <span class="muted">候选 {{ batch.candidate_count }} 条</span>
            <el-button
              v-if="['completed', 'degraded_completed'].includes(batch.status)"
              type="primary"
              size="small"
              @click="router.push(`/matches/${batch.batch_id}`)"
            >
              查看候选
            </el-button>
            <el-button
              v-else-if="batch.status === 'processing'"
              size="small"
              @click="router.push(`/matches/${batch.batch_id}`)"
            >
              查看进度
            </el-button>
            <span v-else class="muted">结果已失效，请重新匹配</span>
          </div>
        </div>
        <div class="muted">
          创建 {{ formatDateTime(batch.created_at) }} · 过期 {{ formatDateTime(batch.expires_at) }}
        </div>
      </el-card>
    </StateBlock>
  </section>
</template>

<style scoped>
.batch {
  margin-bottom: 12px;
}
.row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}
.right {
  display: flex;
  align-items: center;
  gap: 10px;
}
.tag {
  margin-left: 6px;
}
.muted {
  color: #9ca3af;
  font-size: 13px;
  margin-top: 6px;
}
</style>