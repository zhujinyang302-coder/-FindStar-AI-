<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  abandonDraft,
  createMatch,
  fetchMyDrafts,
  fetchMyItem,
  fetchMyItems,
  publishDraft,
  rematch,
  requestDelist,
  resubmitItem,
  withdrawItem
} from '@/api'
import StateBlock from '@/components/StateBlock.vue'
import { formatDateTime, statusLabel, statusTagType } from '@/utils/format'
import type { MyItemDetail, MyItemListItem } from '@/types'
import type { MyDraftItem } from '@/types/drafts'

const router = useRouter()
const items = ref<MyItemListItem[]>([])
const drafts = ref<MyDraftItem[]>([])
const loading = ref(false)
const error = ref<string | null>(null)

const dialog = ref(false)
const detail = ref<MyItemDetail | null>(null)
const detailLoading = ref(false)

async function load() {
  loading.value = true
  error.value = null
  try {
    const result = await fetchMyItems({ page: 1, page_size: 50 })
    items.value = result.items
  } catch (err) {
    error.value = (err as Error).message
  } finally {
    loading.value = false
  }
}

async function openDetail(row: MyItemListItem) {
  detailLoading.value = true
  dialog.value = true
  try {
    detail.value = await fetchMyItem(row.type, row.id)
  } catch {
    detail.value = null
  } finally {
    detailLoading.value = false
  }
}

async function startMatch(row: MyItemListItem) {
  try {
    const payload = row.type === 'lost' ? { lost_item_id: row.id } : { found_item_id: row.id }
    const accepted = await createMatch(payload)
    ElMessage.success('匹配已受理，正在生成候选')
    router.push(`/matches/${accepted.batch_id}`)
  } catch {
    // handled
  }
}

async function doRematch(row: MyItemListItem) {
  try {
    const payload = row.type === 'lost' ? { lost_item_id: row.id } : { found_item_id: row.id }
    const accepted = await rematch(payload)
    ElMessage.success('已重新发起匹配')
    router.push(`/matches/${accepted.batch_id}`)
  } catch {
    // handled
  }
}

async function withdraw(row: MyItemListItem) {
  try {
    await ElMessageBox.confirm('撤回后记录将关闭，需重新提交审核。确认撤回？', '二次确认', {
      type: 'warning'
    })
  } catch {
    return
  }
  try {
    await withdrawItem(row.type, row.id)
    ElMessage.success('已撤回')
    await load()
  } catch {
    // handled
  }
}

async function resubmit(row: MyItemListItem) {
  try {
    await resubmitItem(row.type, row.id)
    ElMessage.success('已重新提交审核')
    await load()
  } catch {
    // handled
  }
}

async function delist(row: MyItemListItem) {
  try {
    const { value } = await ElMessageBox.prompt('请填写下架理由（不少于 5 字）', '申请下架', {
      inputValidator: (v: string) => (v && v.trim().length >= 5 ? true : '至少 5 字'),
      inputType: 'textarea'
    })
    await requestDelist(row.type, row.id, value.trim())
    ElMessage.success('下架审核已提交，审核期间记录保持公开但不参与匹配')
    await load()
  } catch {
    // cancelled or handled
  }
}

async function loadDrafts() {
  try {
    const result = await fetchMyDrafts({ page: 1, page_size: 20 })
    drafts.value = result.items
  } catch {
    drafts.value = []
  }
}

function continueDraft(row: MyDraftItem) {
  router.push({ path: '/publish', query: { type: 'lost', draft: row.draft_id } })
}

async function publishDraftNow(row: MyDraftItem) {
  try {
    await ElMessageBox.confirm(
      '发布后记录将由系统自动校验并上架，同时进入正式匹配。',
      '确认发布',
      { type: 'warning' }
    )
  } catch {
    return
  }
  try {
    const result = await publishDraft(row.draft_id)
    ElMessage.success(
      result.status === 'active' ? '已发布并上架' : '已发布，等待审核'
    )
    await Promise.all([loadDrafts(), load()])
  } catch {
    // handled
  }
}

async function abandonDraftNow(row: MyDraftItem) {
  try {
    await ElMessageBox.confirm(
      '放弃后草稿保留 7 天，可再次恢复。确认放弃？',
      '二次确认',
      { type: 'warning' }
    )
  } catch {
    return
  }
  try {
    await abandonDraft(row.draft_id)
    ElMessage.info('已放弃草稿')
    await loadDrafts()
  } catch {
    // handled
  }
}

onMounted(() => {
  void load()
  void loadDrafts()
})
</script>

<template>
  <section>
    <div class="head">
      <h2 class="section-title">我的记录</h2>
      <div>
        <el-button type="primary" @click="router.push('/publish?type=lost')">发布寻物</el-button>
        <el-button type="success" @click="router.push('/publish?type=found')">发布拾获</el-button>
      </div>
    </div>

    <div v-if="drafts.length" class="draft-panel">
      <div class="draft-head">
        <strong>待发布草稿</strong>
        <span class="muted">保留 7 天，可继续查看或发布</span>
      </div>
      <div v-for="item in drafts" :key="item.draft_id" class="draft-item">
        <div class="draft-main">
          <span class="draft-title">{{ item.title }}</span>
          <span class="muted">
            {{ formatDateTime(item.created_at) }} · 候选 {{ item.candidate_count }} 条 ·
            剩余 {{ Math.max(1, Math.ceil(item.remaining_seconds / 3600)) }} 小时
          </span>
        </div>
        <div class="draft-actions">
          <el-button size="small" @click="continueDraft(item)">继续查看</el-button>
          <el-button size="small" type="primary" @click="publishDraftNow(item)">继续发布</el-button>
          <el-button size="small" type="danger" @click="abandonDraftNow(item)">放弃</el-button>
        </div>
      </div>
    </div>

    <StateBlock
      :loading="loading"
      :error="error"
      :empty="items.length === 0"
      empty-text="还没有记录，先发布一条吧"
      @retry="load"
    >
      <el-table :data="items" stripe>
        <el-table-column label="标题" prop="title" show-overflow-tooltip />
        <el-table-column label="类型" width="90">
          <template #default="{ row }">{{ row.type === 'lost' ? '寻物' : '拾获' }}</template>
        </el-table-column>
        <el-table-column label="状态" width="120">
          <template #default="{ row }">
            <el-tag :type="statusTagType(row.status)" size="small">{{ statusLabel(row.status) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="通过方式/审核意见" width="200">
          <template #default="{ row }">
            <span class="muted">
              {{ row.latest_review?.opinion || (row.status === 'active' ? '系统自动通过' : '—') }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="匹配概况" width="150">
          <template #default="{ row }">
            <template v-if="row.match_summary">
              {{ row.match_summary.candidate_count }} 条
              <el-tag v-if="row.match_summary.degraded" size="small" type="warning">降级</el-tag>
            </template>
            <span v-else class="muted">—</span>
          </template>
        </el-table-column>
        <el-table-column label="更新时间" width="170">
          <template #default="{ row }">{{ formatDateTime(row.updated_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="280">
          <template #default="{ row }">
            <el-button size="small" @click="openDetail(row)">详情</el-button>
            <el-button
              v-if="row.status === 'active'"
              size="small"
              type="primary"
              @click="startMatch(row)"
            >
              发起匹配
            </el-button>
            <el-button
              v-if="row.status === 'active' && row.match_summary"
              size="small"
              @click="doRematch(row)"
            >
              重新匹配
            </el-button>
            <el-button
              v-if="row.status === 'pending_listing'"
              size="small"
              @click="withdraw(row)"
            >
              撤回
            </el-button>
            <el-button
              v-if="['listing_rejected', 'delisted'].includes(row.status)"
              size="small"
              type="warning"
              @click="resubmit(row)"
            >
              重新提交
            </el-button>
            <el-button
              v-if="['active', 'claimed'].includes(row.status)"
              size="small"
              type="danger"
              @click="delist(row)"
            >
              申请下架
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </StateBlock>

    <el-dialog v-model="dialog" title="记录详情" width="620px">
      <div v-loading="detailLoading">
        <template v-if="detail">
          <el-descriptions :column="1" border>
            <el-descriptions-item label="标题">{{ detail.title }}</el-descriptions-item>
            <el-descriptions-item label="状态">{{ statusLabel(detail.status) }}</el-descriptions-item>
            <el-descriptions-item label="类别">{{ detail.category }}</el-descriptions-item>
            <el-descriptions-item label="描述">{{ detail.description || '—' }}</el-descriptions-item>
            <el-descriptions-item label="地点">{{ detail.location_text }}</el-descriptions-item>
            <el-descriptions-item label="时间">{{ formatDateTime(detail.occurred_at) }}</el-descriptions-item>
            <el-descriptions-item label="图片">
              <span v-if="!detail.images.length" class="muted">无</span>
              <img
                v-for="image in detail.images"
                :key="image.id"
                :src="image.url"
                class="image"
              />
            </el-descriptions-item>
          </el-descriptions>
        </template>
      </div>
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
.muted {
  color: #9ca3af;
  font-size: 13px;
}
.image {
  width: 88px;
  height: 88px;
  object-fit: cover;
  border-radius: 6px;
  margin: 4px 8px 4px 0;
}
.draft-panel {
  background: #fff;
  border: 1px solid #eef0f4;
  border-radius: 10px;
  padding: 14px 16px;
  margin-bottom: 16px;
}
.draft-head {
  display: flex;
  align-items: baseline;
  gap: 10px;
  margin-bottom: 10px;
}
.draft-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  padding: 10px 0;
  border-top: 1px solid #f1f3f7;
  flex-wrap: wrap;
}
.draft-main {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
}
.draft-title {
  font-weight: 600;
  color: #111827;
}
.draft-actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}
</style>