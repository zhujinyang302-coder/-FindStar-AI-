<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  confirmContact,
  fetchContactDetail,
  fetchMyRequests,
  fetchReceivedRequests,
  rejectContact
} from '@/api'
import StateBlock from '@/components/StateBlock.vue'
import { formatDateTime, statusLabel, statusTagType } from '@/utils/format'
import type { ContactRequestDetail, ContactRequestItem, ReceivedContactItem } from '@/types'

const tab = ref<'sent' | 'received'>('sent')
const sent = ref<ContactRequestItem[]>([])
const received = ref<ReceivedContactItem[]>([])
const loading = ref(false)
const error = ref<string | null>(null)

const dialog = ref(false)
const detail = ref<ContactRequestDetail | null>(null)
const detailLoading = ref(false)
const handoverCode = ref('')
const handoverStart = ref('')
const handoverEnd = ref('')
const handoverNote = ref('')
const sensitiveVerified = ref(false)
const submitting = ref(false)

async function load() {
  loading.value = true
  error.value = null
  try {
    if (tab.value === 'sent') {
      sent.value = (await fetchMyRequests()).items
    } else {
      received.value = (await fetchReceivedRequests()).items
    }
  } catch (err) {
    error.value = (err as Error).message
  } finally {
    loading.value = false
  }
}

async function openDetail(id: number) {
  dialog.value = true
  detailLoading.value = true
  try {
    detail.value = await fetchContactDetail(id)
    handoverCode.value = detail.value.handover_location_code || ''
    handoverStart.value = detail.value.handover_window_start || ''
    handoverEnd.value = detail.value.handover_window_end || ''
    handoverNote.value = detail.value.handover_note || ''
    sensitiveVerified.value = false
  } catch {
    detail.value = null
  } finally {
    detailLoading.value = false
  }
}

async function confirmCurrent() {
  if (!detail.value) return
  if (!handoverCode.value.trim() || !handoverStart.value || !handoverEnd.value) {
    ElMessage.warning('请填写交接点位与时间窗口')
    return
  }
  if (detail.value.sensitive_category && !sensitiveVerified.value) {
    ElMessage.warning('敏感类别需先完成线下核验并勾选确认')
    return
  }
  try {
    await ElMessageBox.confirm(
      '确认后记录将标记为已认领/已完成，其他待处理申请会自动关闭，且不可撤销。',
      '二次确认',
      { type: 'warning', confirmButtonText: '确认交接' }
    )
  } catch {
    return
  }
  submitting.value = true
  try {
    await confirmContact(detail.value.id, {
      handover_location_code: handoverCode.value.trim(),
      handover_window_start: handoverStart.value,
      handover_window_end: handoverEnd.value,
      handover_note: handoverNote.value || undefined,
      sensitive_verified: sensitiveVerified.value
    })
    ElMessage.success('已确认交接')
    dialog.value = false
    await load()
  } catch {
    // handled
  } finally {
    submitting.value = false
  }
}

async function rejectCurrent() {
  if (!detail.value) return
  try {
    const { value } = await ElMessageBox.prompt('请填写拒绝理由（5–200 字）', '拒绝申请', {
      inputValidator: (v: string) => (v && v.trim().length >= 5 ? true : '至少 5 字'),
      inputType: 'textarea'
    })
    await rejectContact(detail.value.id, value.trim())
    ElMessage.success('已拒绝')
    dialog.value = false
    await load()
  } catch {
    // cancelled or handled
  }
}

onMounted(load)
</script>

<template>
  <section>
    <h2 class="section-title">联系申请</h2>
    <el-tabs v-model="tab" @tab-change="load">
      <el-tab-pane label="我提交的" name="sent">
        <StateBlock
          :loading="loading"
          :error="error"
          :empty="sent.length === 0"
          empty-text="还没有提交过申请"
          @retry="load"
        >
          <el-table :data="sent" stripe>
            <el-table-column label="编号" prop="id" width="80" />
            <el-table-column label="类型" width="120">
              <template #default="{ row }">
                {{ row.request_type === 'claim' ? '认领申请' : '归还线索' }}
              </template>
            </el-table-column>
            <el-table-column label="目标" width="120">
              <template #default="{ row }">
                {{ row.target_item_type === 'lost' ? '寻物' : '拾获' }} #{{ row.target_item_id }}
              </template>
            </el-table-column>
            <el-table-column label="状态" width="110">
              <template #default="{ row }">
                <el-tag :type="statusTagType(row.status)" size="small">{{ statusLabel(row.status) }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column label="提交时间" width="170">
              <template #default="{ row }">{{ formatDateTime(row.created_at) }}</template>
            </el-table-column>
            <el-table-column label="操作" width="110">
              <template #default="{ row }">
                <el-button size="small" @click="openDetail(row.id)">详情</el-button>
              </template>
            </el-table-column>
          </el-table>
        </StateBlock>
      </el-tab-pane>

      <el-tab-pane label="我收到的" name="received">
        <StateBlock
          :loading="loading"
          :error="error"
          :empty="received.length === 0"
          empty-text="还没有收到申请"
          @retry="load"
        >
          <el-table :data="received" stripe>
            <el-table-column label="编号" prop="id" width="80" />
            <el-table-column label="类型" width="120">
              <template #default="{ row }">
                {{ row.request_type === 'claim' ? '认领申请' : '归还线索' }}
              </template>
            </el-table-column>
            <el-table-column label="我的记录" prop="target_item_title" show-overflow-tooltip />
            <el-table-column label="状态" width="110">
              <template #default="{ row }">
                <el-tag :type="statusTagType(row.status)" size="small">{{ statusLabel(row.status) }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column label="提交时间" width="170">
              <template #default="{ row }">{{ formatDateTime(row.created_at) }}</template>
            </el-table-column>
            <el-table-column label="操作" width="110">
              <template #default="{ row }">
                <el-button size="small" @click="openDetail(row.id)">处理</el-button>
              </template>
            </el-table-column>
          </el-table>
        </StateBlock>
      </el-tab-pane>
    </el-tabs>

    <el-dialog v-model="dialog" title="申请详情" width="580px">
      <div v-loading="detailLoading">
        <template v-if="detail">
          <el-descriptions :column="1" border>
            <el-descriptions-item label="状态">{{ statusLabel(detail.status) }}</el-descriptions-item>
            <el-descriptions-item label="目标记录">{{ detail.target_item_title }}</el-descriptions-item>
            <el-descriptions-item label="私密核验信息">
              {{ detail.private_verification || '（无）' }}
            </el-descriptions-item>
            <el-descriptions-item v-if="detail.sensitive_category" label="敏感类别">
              需线下核验，确认时请谨慎
            </el-descriptions-item>
          </el-descriptions>

          <template v-if="detail.status === 'pending' && detail.request_type">
            <h4>交接约定</h4>
            <el-input v-model="handoverCode" placeholder="交接点位编码，如 LIB-1F-SERVICE" />
            <div class="time-row">
              <el-date-picker v-model="handoverStart" type="datetime" placeholder="开始时间" />
              <el-date-picker v-model="handoverEnd" type="datetime" placeholder="结束时间" />
            </div>
            <el-input v-model="handoverNote" placeholder="备注（不得填写联系方式）" />
            <el-checkbox v-if="detail.sensitive_category" v-model="sensitiveVerified">
              已完成线下核验（敏感类别）
            </el-checkbox>
          </template>
        </template>
      </div>
      <template #footer>
        <el-button @click="dialog = false">关闭</el-button>
        <template v-if="detail?.status === 'pending' && tab === 'received'">
          <el-button type="danger" @click="rejectCurrent">拒绝</el-button>
          <el-button type="primary" :loading="submitting" @click="confirmCurrent">确认交接</el-button>
        </template>
      </template>
    </el-dialog>
  </section>
</template>

<style scoped>
.time-row {
  display: flex;
  gap: 10px;
  margin: 10px 0;
  flex-wrap: wrap;
}
h4 {
  margin: 18px 0 10px;
}
</style>