<script setup lang="ts">
import { onMounted, reactive, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  decideReview,
  delistAdminRecord,
  fetchAdminRecord,
  fetchAdminRecords,
  fetchReviewHistory,
  fetchReviewTicket,
  fetchReviewTickets
} from '@/api'
import StateBlock from '@/components/StateBlock.vue'
import { ApiError } from '@/api/client'
import { formatDateTime, statusLabel, statusTagType } from '@/utils/format'
import type { ReviewQueueItem, ReviewTicketDetail } from '@/types'
import type { AdminRecordDetail, AdminRecordItem } from '@/api/adminRecords'

const route = useRoute()
const tab = ref<'listing' | 'delisting' | 'history' | 'records'>(
  route.path === '/admin/records'
    ? 'records'
    : route.query.tab === 'history'
      ? 'history'
      : 'delisting'
)
const rows = ref<ReviewQueueItem[]>([])
const loading = ref(false)
const error = ref<string | null>(null)

const dialog = ref(false)
const detail = ref<ReviewTicketDetail | null>(null)
const detailLoading = ref(false)
const opinion = ref('')
const deciding = ref(false)

const recordRows = ref<AdminRecordItem[]>([])
const recordTotal = ref(0)
const recordPage = ref(1)
const recordLoading = ref(false)
const recordError = ref<string | null>(null)
const recordFilters = reactive({ type: 'all', status: 'all', keyword: '' })
const recordDialog = ref(false)
const recordDetail = ref<AdminRecordDetail | null>(null)
const recordDetailLoading = ref(false)
const delisting = ref(false)

const SOURCE_LABELS: Record<string, string> = {
  owner_request: '发布者申请',
  auto_approval: '系统自动通过',
  legacy_release: '存量迁移',
  report: '举报聚合',
  system_risk: '风控抽检'
}

function sourceLabel(source: string): string {
  return SOURCE_LABELS[source] || source
}

async function load() {
  loading.value = true
  error.value = null
  try {
    if (tab.value === 'records') {
      await loadRecords()
      return
    }
    if (tab.value === 'history') {
      rows.value = (await fetchReviewHistory({ page: 1, page_size: 50 })).items
    } else {
      rows.value = (
        await fetchReviewTickets({ review_type: tab.value, page: 1, page_size: 50 })
      ).items
    }
  } catch (err) {
    error.value = (err as Error).message
  } finally {
    loading.value = false
  }
}

async function loadRecords() {
  recordLoading.value = true
  recordError.value = null
  try {
    const result = await fetchAdminRecords({
      type: recordFilters.type,
      status: recordFilters.status,
      keyword: recordFilters.keyword || undefined,
      page: recordPage.value,
      page_size: 20
    })
    recordRows.value = result.items
    recordTotal.value = result.total
  } catch (err) {
    recordError.value = (err as Error).message
  } finally {
    recordLoading.value = false
  }
}

function searchRecords() {
  recordPage.value = 1
  void loadRecords()
}

function changeRecordPage(delta: number) {
  const maxPage = Math.max(1, Math.ceil(recordTotal.value / 20))
  const next = Math.min(maxPage, Math.max(1, recordPage.value + delta))
  if (next !== recordPage.value) {
    recordPage.value = next
    void loadRecords()
  }
}

async function openRecordDetail(row: AdminRecordItem) {
  recordDialog.value = true
  recordDetailLoading.value = true
  recordDetail.value = null
  try {
    recordDetail.value = await fetchAdminRecord(row.item_type, row.item_id)
  } catch {
    recordDetail.value = null
  } finally {
    recordDetailLoading.value = false
  }
}

async function doDirectDelist() {
  if (!recordDetail.value) return
  let reason = ''
  try {
    const input = await ElMessageBox.prompt('请填写下架理由（不少于 5 字）', '直接下架', {
      inputValidator: (v: string) => (v && v.trim().length >= 5 ? true : '至少 5 字'),
      inputType: 'textarea'
    })
    reason = input.value.trim()
  } catch {
    return
  }
  try {
    await ElMessageBox.confirm(
      '确认直接下架该记录？操作将记录审计并通知发布者。',
      '二次确认',
      { type: 'warning' }
    )
  } catch {
    return
  }
  delisting.value = true
  try {
    const result = await delistAdminRecord(
      recordDetail.value.item_type,
      recordDetail.value.item_id,
      reason
    )
    ElMessage.success(
      `已下架，单号 ${result.ticket_no}，影响批次 ${result.invalidated_batches}`
    )
    recordDialog.value = false
    await loadRecords()
  } catch {
    // handled
  } finally {
    delisting.value = false
  }
}

watch(tab, load)

async function openDetail(row: ReviewQueueItem) {
  dialog.value = true
  detailLoading.value = true
  opinion.value = ''
  try {
    detail.value = await fetchReviewTicket(row.ticket_no)
  } catch {
    detail.value = null
  } finally {
    detailLoading.value = false
  }
}

async function decide(action: 'approve' | 'reject') {
  if (!detail.value) return
  if (action === 'reject' && opinion.value.trim().length < 5) {
    ElMessage.warning('驳回需填写不少于 5 字的理由')
    return
  }
  const label = action === 'approve' ? '通过' : '驳回'
  try {
    await ElMessageBox.confirm(
      `确认${label}该${detail.value.review_type === 'listing' ? '上架' : '下架'}审核单？操作将记录审计。`,
      '二次确认',
      { type: 'warning' }
    )
  } catch {
    return
  }
  deciding.value = true
  try {
    await decideReview(detail.value.ticket_no, {
      decision: action,
      opinion: opinion.value.trim() || undefined
    })
    ElMessage.success(`已${label}`)
    dialog.value = false
    await load()
  } catch (err) {
    if (err instanceof ApiError && err.status === 410) {
      ElMessage.warning('上架审核已退役，记录已由系统自动完成上架')
    }
  } finally {
    deciding.value = false
  }
}

onMounted(load)
</script>

<template>
  <section>
    <h2 class="section-title">审核工作台</h2>
    <el-alert
      type="info"
      title="上架由系统自动完成；管理员负责下架审核与举报/风控处置，不参与认领判定，也不查看匹配候选、申请人身份或私密核验信息。"
      show-icon
      :closable="false"
      class="mb"
    />

    <el-tabs v-model="tab">
      <el-tab-pane label="上架审核（已退役）" name="listing" />
      <el-tab-pane label="待下架审核" name="delisting" />
      <el-tab-pane label="审核历史" name="history" />
      <el-tab-pane label="记录管理" name="records" />
    </el-tabs>

    <el-alert
      v-if="tab === 'listing'"
      type="info"
      title="上架审核已由系统自动完成；此处仅保留存量待办查看，不再提供通过 / 驳回操作。"
      show-icon
      :closable="false"
      class="mb"
    />

    <template v-if="tab !== 'records'">
    <StateBlock
      :loading="loading"
      :error="error"
      :empty="rows.length === 0"
      empty-text="当前没有待处理审核单"
      @retry="load"
    >
      <el-table :data="rows" stripe>
        <el-table-column label="单号" prop="ticket_no" width="160" />
        <el-table-column label="类型" width="110">
          <template #default="{ row }">
            {{ row.review_type === 'listing' ? '上架' : '下架' }}
          </template>
        </el-table-column>
        <el-table-column label="来源" width="110">
          <template #default="{ row }">
            {{ sourceLabel(row.source) }}
          </template>
        </el-table-column>
        <el-table-column label="记录标题" prop="item_title" show-overflow-tooltip />
        <el-table-column v-if="tab !== 'history'" label="等待" width="100">
          <template #default="{ row }">
            {{ row.waiting_minutes }} 分钟
            <el-tag v-if="row.overdue" type="danger" size="small">超时</el-tag>
          </template>
        </el-table-column>
        <el-table-column v-else label="状态" width="110">
          <template #default="{ row }">
            <el-tag :type="statusTagType(row.status)" size="small">{{ statusLabel(row.status) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="提交时间" width="170">
          <template #default="{ row }">{{ formatDateTime(row.created_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="120">
          <template #default="{ row }">
            <el-button size="small" @click="openDetail(row)">审核详情</el-button>
          </template>
        </el-table-column>
      </el-table>
    </StateBlock>

    <el-dialog v-model="dialog" title="审核详情" width="620px">
      <div v-loading="detailLoading">
        <template v-if="detail">
          <el-descriptions :column="1" border>
            <el-descriptions-item label="单号">{{ detail.ticket_no }}</el-descriptions-item>
            <el-descriptions-item label="类型">
              {{ detail.review_type === 'listing' ? '上架审核' : '下架审核' }}
            </el-descriptions-item>
            <el-descriptions-item label="记录">{{ detail.item_title }}</el-descriptions-item>
            <el-descriptions-item label="类别">{{ detail.item_category }}</el-descriptions-item>
            <el-descriptions-item label="描述">{{ detail.item_description || '—' }}</el-descriptions-item>
            <el-descriptions-item label="地点">{{ detail.location_text }}</el-descriptions-item>
            <el-descriptions-item label="时间">{{ formatDateTime(detail.occurred_at) }}</el-descriptions-item>
            <el-descriptions-item label="合规检查">
              <el-tag
                v-for="check in detail.compliance_checks"
                :key="check.key"
                :type="check.passed ? 'success' : 'danger'"
                size="small"
                class="check"
              >
                {{ check.key }} {{ check.passed ? '通过' : '未通过' }}
              </el-tag>
            </el-descriptions-item>
            <el-descriptions-item label="历史结论">
              <div v-for="item in detail.history" :key="item.review_round">
                第 {{ item.review_round }} 轮：{{ statusLabel(item.status) }} · {{ item.opinion || '—' }}
              </div>
            </el-descriptions-item>
          </el-descriptions>
          <el-alert :title="detail.disclaimer" type="info" :closable="false" show-icon class="mt" />
          <el-input
            v-model="opinion"
            class="mt"
            type="textarea"
            :rows="3"
            maxlength="500"
            placeholder="审核意见（驳回必填，不少于 5 字）"
          />
        </template>
      </div>
      <template #footer>
        <el-button @click="dialog = false">关闭</el-button>
        <template v-if="detail && tab === 'delisting'">
          <el-button type="danger" :loading="deciding" @click="decide('reject')">驳回</el-button>
          <el-button type="primary" :loading="deciding" @click="decide('approve')">通过</el-button>
        </template>
      </template>
    </el-dialog>
    </template>

    <template v-else>
      <div class="record-filters">
        <el-select v-model="recordFilters.type" class="filter">
          <el-option label="全部类型" value="all" />
          <el-option label="寻物启事" value="lost" />
          <el-option label="失物招领" value="found" />
        </el-select>
        <el-select v-model="recordFilters.status" class="filter">
          <el-option label="已上架 + 下架审核中" value="all" />
          <el-option label="待上架审核" value="pending_listing" />
          <el-option label="已上架" value="active" />
          <el-option label="下架审核中" value="delisting_review" />
          <el-option label="已下架" value="delisted" />
          <el-option label="已认领" value="claimed" />
          <el-option label="已完成" value="resolved" />
          <el-option label="已关闭" value="closed" />
        </el-select>
        <el-input
          v-model="recordFilters.keyword"
          class="filter keyword"
          maxlength="50"
          placeholder="标题关键词"
          @keyup.enter="searchRecords"
        />
        <el-button type="primary" @click="searchRecords">查询</el-button>
      </div>

      <StateBlock
        :loading="recordLoading"
        :error="recordError"
        :empty="recordRows.length === 0"
        empty-text="没有符合条件的记录"
        @retry="loadRecords"
      >
        <el-table :data="recordRows" stripe>
          <el-table-column label="类型" width="100">
            <template #default="{ row }">
              {{ row.item_type === 'lost' ? '寻物' : '失物招领' }}
            </template>
          </el-table-column>
          <el-table-column label="标题" prop="title" show-overflow-tooltip />
          <el-table-column label="类别" prop="category" width="110" />
          <el-table-column label="地点" prop="location_text" show-overflow-tooltip />
          <el-table-column label="状态" width="120">
            <template #default="{ row }">
              <el-tag :type="statusTagType(row.status)" size="small">
                {{ statusLabel(row.status) }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="创建时间" width="170">
            <template #default="{ row }">{{ formatDateTime(row.created_at) }}</template>
          </el-table-column>
          <el-table-column label="操作" width="120">
            <template #default="{ row }">
              <el-button size="small" @click="openRecordDetail(row)">查看详情</el-button>
            </template>
          </el-table-column>
        </el-table>
      </StateBlock>

      <div class="record-pager">
        <span class="muted">共 {{ recordTotal }} 条</span>
        <el-button size="small" :disabled="recordPage <= 1" @click="changeRecordPage(-1)">
          上一页
        </el-button>
        <span class="muted">第 {{ recordPage }} 页</span>
        <el-button
          size="small"
          :disabled="recordPage * 20 >= recordTotal"
          @click="changeRecordPage(1)"
        >
          下一页
        </el-button>
      </div>

      <el-dialog v-model="recordDialog" title="记录详情" width="680px">
        <div v-loading="recordDetailLoading">
          <template v-if="recordDetail">
            <el-descriptions :column="1" border>
              <el-descriptions-item label="类型">
                {{ recordDetail.item_type === 'lost' ? '寻物启事' : '失物招领' }}
              </el-descriptions-item>
              <el-descriptions-item label="标题">{{ recordDetail.title }}</el-descriptions-item>
              <el-descriptions-item label="类别">{{ recordDetail.category }}</el-descriptions-item>
              <el-descriptions-item label="颜色 / 品牌">
                {{ recordDetail.color || '—' }} / {{ recordDetail.brand || '—' }}
              </el-descriptions-item>
              <el-descriptions-item label="地点">{{ recordDetail.location_text }}</el-descriptions-item>
              <el-descriptions-item label="时间">
                {{ formatDateTime(recordDetail.occurred_at) }}
              </el-descriptions-item>
              <el-descriptions-item label="状态">
                <el-tag :type="statusTagType(recordDetail.status)" size="small">
                  {{ statusLabel(recordDetail.status) }}
                </el-tag>
              </el-descriptions-item>
              <el-descriptions-item label="描述">{{ recordDetail.description || '—' }}</el-descriptions-item>
              <el-descriptions-item label="图片">
                <span v-if="!recordDetail.images.length" class="muted">无</span>
                <el-image
                  v-for="img in recordDetail.images"
                  :key="img.id"
                  :src="img.thumb_url || img.url || ''"
                  fit="cover"
                  class="record-image"
                />
              </el-descriptions-item>
              <el-descriptions-item label="审核历史">
                <div v-for="item in recordDetail.history" :key="item.review_round + item.status">
                  第 {{ item.review_round }} 轮：{{ statusLabel(item.status) }} ·
                  {{ item.opinion || '—' }}
                </div>
                <span v-if="!recordDetail.history.length" class="muted">无</span>
              </el-descriptions-item>
            </el-descriptions>
          </template>
        </div>
        <template #footer>
          <el-button @click="recordDialog = false">关闭</el-button>
          <el-button
            type="danger"
            :loading="delisting"
            :disabled="!recordDetail || recordDetail.status === 'delisted'"
            @click="doDirectDelist"
          >
            直接下架
          </el-button>
        </template>
      </el-dialog>
    </template>
  </section>
</template>

<style scoped>
.mb {
  margin-bottom: 16px;
}
.mt {
  margin-top: 12px;
}
.check {
  margin-right: 6px;
}
.record-filters {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
  margin-bottom: 14px;
}
.filter {
  width: 190px;
}
.keyword {
  width: 240px;
}
.record-pager {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-top: 14px;
}
.record-image {
  width: 88px;
  height: 88px;
  border-radius: 6px;
  margin: 4px 8px 4px 0;
}
.muted {
  color: #9ca3af;
  font-size: 13px;
}
</style>