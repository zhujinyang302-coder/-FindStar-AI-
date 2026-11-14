<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import {
  createContactRequest,
  fetchBatch,
  fetchCandidates,
  sendFeedback
} from '@/api'
import MatchScorePanel from '@/components/MatchScorePanel.vue'
import StateBlock from '@/components/StateBlock.vue'
import { ApiError } from '@/api/client'
import { areaLabel, formatDateTime, statusLabel, statusTagType } from '@/utils/format'
import type {
  CandidateSummary,
  FeedbackType,
  MatchBatchInfo
} from '@/types'

const route = useRoute()
const router = useRouter()
const batchId = computed(() => String(route.params.batchId || ''))

const batch = ref<MatchBatchInfo | null>(null)
const candidates = ref<CandidateSummary[]>([])
const loading = ref(false)
const error = ref<string | null>(null)

const filter = ref({ category: '', color: '', keyword: '' })

const applyDialog = ref(false)
const activeCandidate = ref<CandidateSummary | null>(null)
const applyType = ref<'claim' | 'return_clue'>('claim')
const privateVerification = ref('')
const handoverCode = ref('')
const submitting = ref(false)

const shownCandidates = computed(() =>
  candidates.value.filter((candidate) => {
    if (filter.value.category && candidate.category !== filter.value.category) return false
    if (filter.value.color && (candidate.color || '') !== filter.value.color) return false
    if (filter.value.keyword) {
      const text = `${candidate.title_excerpt}${candidate.description_excerpt}`
      if (!text.includes(filter.value.keyword)) return false
    }
    return true
  })
)

async function load() {
  loading.value = true
  error.value = null
  try {
    batch.value = await fetchBatch(batchId.value)
    if (['completed', 'degraded_completed'].includes(batch.value.status)) {
      const result = await fetchCandidates(batchId.value)
      candidates.value = result.candidates
    } else {
      candidates.value = []
    }
  } catch (err) {
    const status = err instanceof ApiError ? err.status : 0
    error.value = status === 404 ? '匹配批次不存在或不可见' : (err as Error).message
  } finally {
    loading.value = false
  }
}

function openApply(candidate: CandidateSummary) {
  activeCandidate.value = candidate
  applyType.value = candidate.item_type === 'found' ? 'claim' : 'return_clue'
  privateVerification.value = ''
  handoverCode.value = ''
  applyDialog.value = true
}

async function submitApply() {
  if (!activeCandidate.value) return
  const text = privateVerification.value.trim()
  if (applyType.value === 'claim' && text.length < 10) {
    ElMessage.warning('认领申请需填写不少于 10 字的私密核验信息')
    return
  }
  submitting.value = true
  try {
    await createContactRequest({
      batch_id: batchId.value,
      candidate_public_id: activeCandidate.value.candidate_public_id,
      request_type: applyType.value,
      private_verification: text || undefined,
      handover_location_code: handoverCode.value || undefined
    })
    ElMessage.success('申请已提交，等待对侧发布者确认')
    applyDialog.value = false
    router.push('/my/requests')
  } catch {
    // handled
  } finally {
    submitting.value = false
  }
}

async function report(candidate: CandidateSummary, type: FeedbackType) {
  try {
    await sendFeedback(candidate.candidate_public_id, { feedback_type: type })
    ElMessage.success('反馈已记录，不会改变记录状态')
  } catch {
    // handled
  }
}

onMounted(load)
</script>

<template>
  <section>
    <h2 class="section-title">匹配结果</h2>
    <StateBlock
      :loading="loading"
      :error="error"
      :empty="!batch"
      empty-text="匹配批次不存在或不可见"
      @retry="load"
    >
      <template v-if="batch">
        <el-alert
          type="info"
          title="匹配分数仅用于推荐候选，不代表物品归属或找回概率。候选不展示对方身份与联系方式，交接前请线下核验。"
          show-icon
          :closable="false"
          class="mb"
        />
        <el-descriptions :column="3" border class="mb">
          <el-descriptions-item label="状态">
            <el-tag :type="statusTagType(batch.status)" size="small">{{ statusLabel(batch.status) }}</el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="候选数">{{ batch.candidate_count }}</el-descriptions-item>
          <el-descriptions-item label="过期时间">{{ formatDateTime(batch.expires_at) }}</el-descriptions-item>
          <el-descriptions-item label="算法版本">{{ batch.algorithm_version || '—' }}</el-descriptions-item>
          <el-descriptions-item label="召回通道">{{ batch.recall_channel || '—' }}</el-descriptions-item>
          <el-descriptions-item label="降级">
            <span v-if="batch.degraded" class="warn">{{ batch.degraded_reason || '是' }}</span>
            <span v-else>否</span>
          </el-descriptions-item>
        </el-descriptions>

        <el-alert
          v-if="batch.status === 'processing'"
          type="warning"
          title="匹配仍在处理中，请稍后刷新；系统会在完成后通知你。"
          show-icon
          :closable="false"
          class="mb"
        />
        <el-empty v-if="batch.status === 'no_candidates'" description="暂无可靠候选">
          <p class="muted">请留意后续新增记录或重新匹配。</p>
        </el-empty>

        <template v-if="shownCandidates.length || candidates.length">
          <el-card class="filters mb">
            <el-form inline>
              <el-form-item label="类别">
                <el-input v-model="filter.category" placeholder="批次内筛选" clearable />
              </el-form-item>
              <el-form-item label="颜色">
                <el-input v-model="filter.color" clearable />
              </el-form-item>
              <el-form-item label="关键词">
                <el-input v-model="filter.keyword" placeholder="仅匹配摘要文本" clearable />
              </el-form-item>
            </el-form>
            <span class="muted">筛选仅作用于当前批次已返回的候选，不会检索其他记录。</span>
          </el-card>

          <el-card v-for="candidate in shownCandidates" :key="candidate.candidate_public_id" class="candidate">
            <div class="candidate-head">
              <img v-if="candidate.thumb_url" :src="candidate.thumb_url" class="thumb" />
              <div>
                <el-tag :type="candidate.item_type === 'lost' ? 'danger' : 'success'" size="small">
                  {{ candidate.item_type === 'lost' ? '寻物' : '拾获' }}
                </el-tag>
                <el-tag v-if="candidate.requires_offline_verification" type="warning" size="small" class="tag">
                  需线下核验
                </el-tag>
                <h3>{{ candidate.title_excerpt }}</h3>
                <p class="muted">
                  {{ areaLabel(candidate.area_name) }} · {{ candidate.occurred_on || '时间未知' }} · {{ candidate.category }}
                </p>
                <p class="desc">{{ candidate.description_excerpt }}</p>
              </div>
            </div>
            <el-divider />
            <MatchScorePanel :breakdown="candidate.score_breakdown" :total="candidate.score" />
            <h4>匹配理由</h4>
            <ul class="reasons">
              <li v-for="(reason, index) in candidate.reasons" :key="index">{{ reason }}</li>
              <li v-if="!candidate.reasons.length" class="muted">解释生成不可用，已保留分数</li>
            </ul>
            <h4>待核验点</h4>
            <el-table :data="candidate.differences" size="small" empty-text="未发现显著差异">
              <el-table-column prop="field" label="字段" width="90" />
              <el-table-column label="本记录" prop="self_value" show-overflow-tooltip />
              <el-table-column label="候选" prop="candidate_value" show-overflow-tooltip />
              <el-table-column prop="note" label="说明" show-overflow-tooltip />
            </el-table>
            <div class="actions">
              <el-button type="primary" @click="openApply(candidate)">
                {{ candidate.item_type === 'found' ? '提交认领申请' : '提交归还线索' }}
              </el-button>
              <el-dropdown @command="(type: FeedbackType) => report(candidate, type)">
                <el-button>误报反馈</el-button>
                <template #dropdown>
                  <el-dropdown-menu>
                    <el-dropdown-item command="not_mine">不是我的物品</el-dropdown-item>
                    <el-dropdown-item command="not_target">不是目标物品</el-dropdown-item>
                    <el-dropdown-item command="inaccurate">信息不准确</el-dropdown-item>
                    <el-dropdown-item command="suspected_impersonation">疑似冒领</el-dropdown-item>
                  </el-dropdown-menu>
                </template>
              </el-dropdown>
            </div>
          </el-card>
          <el-empty v-if="!shownCandidates.length" description="当前筛选条件下没有候选" />
        </template>
        <p class="muted disclaimer">候选基于相似度匹配，交接前请线下核验物品真伪。</p>
      </template>
    </StateBlock>

    <el-dialog v-model="applyDialog" title="提交申请" width="520px">
      <p class="muted">私密核验信息仅申请人与对侧记录发布者可见，不会展示给管理员或其他用户。</p>
      <el-input
        v-model="privateVerification"
        type="textarea"
        :rows="3"
        maxlength="500"
        show-word-limit
        :placeholder="applyType === 'claim' ? '必填：不少于 10 字的私密核验信息' : '可选：补充归还线索'"
      />
      <el-input v-model="handoverCode" class="mt" placeholder="可选：建议交接点位编码" />
      <template #footer>
        <el-button @click="applyDialog = false">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="submitApply">提交</el-button>
      </template>
    </el-dialog>
  </section>
</template>

<style scoped>
.mb {
  margin-bottom: 16px;
}
.candidate {
  margin-bottom: 16px;
}
.candidate-head {
  display: flex;
  gap: 16px;
  align-items: flex-start;
}
.thumb {
  width: 128px;
  height: 128px;
  object-fit: cover;
  border-radius: 8px;
}
.candidate-head h3 {
  margin: 6px 0;
}
.desc {
  color: #4b5563;
}
.tag {
  margin-left: 6px;
}
.reasons {
  margin: 8px 0;
  padding-left: 18px;
  color: #4b5563;
}
.actions {
  margin-top: 16px;
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
}
.muted {
  color: #9ca3af;
  font-size: 13px;
}
.warn {
  color: #b45309;
}
.disclaimer {
  margin-top: 12px;
}
.mt {
  margin-top: 10px;
}
</style>