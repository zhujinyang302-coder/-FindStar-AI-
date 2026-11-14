<script setup lang="ts">
import { computed } from 'vue'
import type { ScoreBreakdown, ScorePart } from '@/types'

const props = defineProps<{ breakdown: ScoreBreakdown; total: number }>()

const labels: Record<keyof ScoreBreakdown, string> = {
  text: '文本语义',
  image: '视觉特征',
  location: '地点',
  time: '时间',
  attribute: '结构化属性'
}

const rows = computed(() =>
  (Object.keys(labels) as (keyof ScoreBreakdown)[]).map((key) => ({
    key,
    label: labels[key],
    part: props.breakdown[key] as ScorePart
  }))
)
</script>

<template>
  <div class="score-panel">
    <div class="total">
      <span class="score">{{ total.toFixed(1) }}</span>
      <span class="unit">/ 100（算法分数，非找回概率）</span>
    </div>
    <div v-for="row in rows" :key="row.key" class="score-bar">
      <div class="bar-label">
        <span>{{ row.label }}</span>
        <span class="weight" v-if="row.part.available">权重 {{ Math.round(row.part.weight * 100) }}%</span>
        <el-tag v-else size="small" type="warning" effect="plain">不可用</el-tag>
      </div>
      <el-progress
        :percentage="Math.round(row.part.score * 100)"
        :stroke-width="10"
        :status="row.part.available ? undefined : 'warning'"
      />
      <div v-if="row.part.note" class="note">{{ row.part.note }}</div>
    </div>
  </div>
</template>

<style scoped>
.score-panel {
  padding: 4px 0;
}
.total {
  margin-bottom: 12px;
}
.score {
  font-size: 26px;
  font-weight: 700;
  color: #3b5bdb;
}
.unit {
  font-size: 12px;
  color: #6b7280;
  margin-left: 6px;
}
.bar-label {
  display: flex;
  justify-content: space-between;
  font-size: 13px;
  margin-bottom: 4px;
  color: #374151;
}
.weight {
  color: #9ca3af;
  font-size: 12px;
}
.note {
  font-size: 12px;
  color: #9ca3af;
  margin-top: 2px;
}
</style>