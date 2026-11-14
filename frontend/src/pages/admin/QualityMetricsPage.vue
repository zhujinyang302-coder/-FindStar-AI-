<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { createConfigVersion, fetchConfigVersions, fetchQualityMetrics } from '@/api'
import StateBlock from '@/components/StateBlock.vue'
import { formatDateTime } from '@/utils/format'
import type { MatchConfigVersion, QualityMetrics } from '@/types'

const metrics = ref<QualityMetrics | null>(null)
const versions = ref<MatchConfigVersion[]>([])
const loading = ref(false)
const error = ref<string | null>(null)

const dialog = ref(false)
const form = ref({ threshold: 65, quota: 3, time_window_days: 30, reason: '' })
const submitting = ref(false)

async function load() {
  loading.value = true
  error.value = null
  try {
    const [metricResult, versionResult] = await Promise.all([
      fetchQualityMetrics(),
      fetchConfigVersions()
    ])
    metrics.value = metricResult
    versions.value = versionResult.items
  } catch (err) {
    error.value = (err as Error).message
  } finally {
    loading.value = false
  }
}

function percent(value: number): string {
  return `${(value * 100).toFixed(1)}%`
}

async function submit() {
  if (!form.value.reason.trim() || form.value.reason.trim().length < 5) {
    ElMessage.warning('配置调整必须附不少于 5 字的理由')
    return
  }
  submitting.value = true
  try {
    await createConfigVersion({
      threshold: form.value.threshold,
      quota: form.value.quota,
      time_window_days: form.value.time_window_days,
      reason: form.value.reason.trim()
    })
    ElMessage.success('新配置版本已生效，不重算历史批次')
    dialog.value = false
    await load()
  } catch {
    // handled
  } finally {
    submitting.value = false
  }
}

onMounted(load)
</script>

<template>
  <section>
    <div class="head">
      <h2 class="section-title">匹配质量指标</h2>
      <el-button type="primary" @click="dialog = true">新建配置版本</el-button>
    </div>
    <el-alert
      type="info"
      title="仅展示聚合口径，不含任何候选内容与用户身份；管理员不得据此查看候选明细。"
      show-icon
      :closable="false"
      class="mb"
    />

    <StateBlock
      :loading="loading"
      :error="error"
      :empty="!metrics"
      empty-text="暂无指标数据"
      @retry="load"
    >
      <template v-if="metrics">
        <div class="stat-row">
          <div class="stat-card"><div class="value">{{ metrics.match_requests }}</div><div class="label">匹配发起量</div></div>
          <div class="stat-card"><div class="value">{{ percent(metrics.no_candidate_rate) }}</div><div class="label">无候选率</div></div>
          <div class="stat-card"><div class="value">{{ percent(metrics.top3_hit_rate) }}</div><div class="label">Top3 命中率</div></div>
          <div class="stat-card"><div class="value">{{ percent(metrics.user_false_positive_rate) }}</div><div class="label">用户误报率</div></div>
          <div class="stat-card"><div class="value">{{ percent(metrics.degraded_rate) }}</div><div class="label">降级率</div></div>
          <div class="stat-card"><div class="value">{{ metrics.candidate_p95_ms.toFixed(0) }}</div><div class="label">候选生成 P95（ms）</div></div>
        </div>
        <p class="muted">
          统计区间 {{ metrics.period_label }} · 生成时间 {{ formatDateTime(metrics.generated_at) }}
        </p>
      </template>
    </StateBlock>

    <h3 class="section-title">配置版本历史</h3>
    <el-table :data="versions" stripe>
      <el-table-column label="版本" prop="version" width="180" />
      <el-table-column label="阈值" prop="threshold" width="90" />
      <el-table-column label="配额" prop="quota" width="80" />
      <el-table-column label="时间窗口（天）" prop="time_window_days" width="130" />
      <el-table-column label="召回策略" prop="recall_strategy" width="130" />
      <el-table-column label="理由" prop="reason" show-overflow-tooltip />
      <el-table-column label="状态" width="90">
        <template #default="{ row }">
          <el-tag :type="row.active ? 'success' : 'info'" size="small">
            {{ row.active ? '生效中' : '历史' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="创建时间" width="170">
        <template #default="{ row }">{{ formatDateTime(row.created_at) }}</template>
      </el-table-column>
    </el-table>

    <el-dialog v-model="dialog" title="新建配置版本" width="480px">
      <el-form label-width="120px">
        <el-form-item label="阈值">
          <el-input-number v-model="form.threshold" :min="0" :max="100" />
        </el-form-item>
        <el-form-item label="配额">
          <el-input-number v-model="form.quota" :min="1" :max="5" />
        </el-form-item>
        <el-form-item label="时间窗口（天）">
          <el-input-number v-model="form.time_window_days" :min="1" :max="365" />
        </el-form-item>
        <el-form-item label="调整理由">
          <el-input v-model="form.reason" type="textarea" :rows="3" maxlength="500" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialog = false">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="submit">保存并生效</el-button>
      </template>
    </el-dialog>
  </section>
</template>

<style scoped>
.head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}
.mb {
  margin-bottom: 16px;
}
.muted {
  color: #9ca3af;
  font-size: 13px;
}
</style>