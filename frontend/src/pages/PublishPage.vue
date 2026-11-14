<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  abandonDraft,
  createFoundItem,
  createLostDraft,
  createLostItem,
  extractFeatures,
  fetchDraft,
  fetchDraftPreview,
  fetchPublishMode,
  publishDraft,
  uploadImage
} from '@/api'
import { CATEGORIES, toUtcIso } from '@/utils/format'
import type { ItemType } from '@/types'
import type { DraftDetail, DraftPreview } from '@/types/drafts'

const route = useRoute()
const router = useRouter()

const itemType = ref<ItemType>(route.query.type === 'found' ? 'found' : 'lost')
const publishMode = ref<'match_first' | 'direct'>('direct')

watch(
  () => route.query.type,
  (value) => {
    itemType.value = value === 'found' ? 'found' : 'lost'
  }
)

const form = reactive({
  title: '',
  description: '',
  category: '',
  color: '',
  brand: '',
  location_code: '',
  location_text: '',
  occurred_at: ''
})

const imageKeys = ref<string[]>([])
const uploading = ref(false)
const recognizing = ref(false)
const submitting = ref(false)
const publishing = ref(false)
const previewLoading = ref(false)
const noticeAccepted = ref(false)
const aiDegraded = ref(false)
const aiWarnings = ref<string[]>([])

const draft = ref<DraftDetail | null>(null)
const preview = ref<DraftPreview | null>(null)
const showNoCandidate = ref(false)
const dialogResolved = ref(false)

const title = computed(() => (itemType.value === 'lost' ? '发布寻物记录' : '发布拾获记录'))
const timeLabel = computed(() => (itemType.value === 'lost' ? '丢失时间' : '拾获时间'))
const infoSufficient = computed(
  () => imageKeys.value.length >= 1 || form.description.trim().length >= 20
)
const isMatchFirstLost = computed(
  () => itemType.value === 'lost' && publishMode.value === 'match_first'
)

const stageHint = computed(() => {
  if (isMatchFirstLost.value) {
    return '先填写丢失信息并提交，系统会立即匹配现有失物招领；你可以先查看候选，再决定是否发布寻物启事。'
  }
  if (itemType.value === 'found') {
    return '提交后将由系统自动校验并立即上架，同时自动发起匹配；无需等待人工审核。'
  }
  return '提交后将由系统自动校验并立即上架，同时自动发起匹配；无需等待人工审核。'
})

const submitLabel = computed(() =>
  isMatchFirstLost.value ? '提交并匹配失物招领' : '提交并上架'
)

async function handleUpload(options: { file: File }) {
  uploading.value = true
  try {
    if (imageKeys.value.length >= 5) {
      ElMessage.warning('单条记录最多 5 张图片')
      return
    }
    const result = await uploadImage(options.file)
    imageKeys.value.push(result.object_key)
    ElMessage.success('图片上传成功')
  } catch {
    // handled
  } finally {
    uploading.value = false
  }
}

function removeImage(key: string) {
  imageKeys.value = imageKeys.value.filter((k) => k !== key)
}

async function recognize() {
  if (!form.description.trim() && imageKeys.value.length === 0) {
    ElMessage.warning('请先填写描述或上传图片')
    return
  }
  recognizing.value = true
  try {
    const result = await extractFeatures({
      description: form.description || undefined,
      image_keys: imageKeys.value
    })
    aiDegraded.value = result.degraded
    aiWarnings.value = result.warnings
    if (result.features.category && result.features.category !== '未知' && !form.category) {
      form.category = result.features.category
    }
    if (result.features.color && !form.color) form.color = result.features.color
    if (result.features.brand && !form.brand) form.brand = result.features.brand
    ElMessage.success('已填充识别结果，可自行修改')
  } catch {
    // handled
  } finally {
    recognizing.value = false
  }
}

function buildPayload() {
  return {
    title: form.title.trim(),
    description: form.description.trim(),
    category: form.category,
    color: form.color || null,
    brand: form.brand || null,
    location_code: form.location_code || null,
    location_text: form.location_text.trim(),
    occurred_at: toUtcIso(form.occurred_at),
    image_keys: imageKeys.value,
    matching_notice_accepted: noticeAccepted.value
  }
}

function validate(): boolean {
  if (!form.title.trim() || !form.category || !form.location_text.trim()) {
    ElMessage.warning('请完整填写标题、类别与地点')
    return false
  }
  if (!infoSufficient.value) {
    ElMessage.warning('请至少上传 1 张图片，或填写不少于 20 字的描述')
    return false
  }
  if (!noticeAccepted.value) {
    ElMessage.warning('请先阅读并勾选匹配告知')
    return false
  }
  return true
}

async function loadDraft(draftId: string) {
  previewLoading.value = true
  try {
    draft.value = await fetchDraft(draftId)
    preview.value = await fetchDraftPreview(draftId)
    if (preview.value.status === 'no_candidates') {
      showNoCandidate.value = true
    }
  } catch {
    draft.value = null
    preview.value = null
  } finally {
    previewLoading.value = false
  }
}

async function refreshPreview() {
  if (!draft.value) return
  await loadDraft(draft.value.draft_id)
}

async function submit() {
  if (submitting.value) return
  if (!validate()) return
  submitting.value = true
  try {
    const payload = buildPayload()
    if (isMatchFirstLost.value) {
      const created = await createLostDraft(payload)
      ElMessage.success(
        created.idempotent_replay ? '已恢复未发布的草稿' : '已提交，正在匹配失物招领'
      )
      await router.replace({ path: '/publish', query: { type: 'lost', draft: created.draft_id } })
      await loadDraft(created.draft_id)
      if (preview.value?.status === 'processing') {
        window.setTimeout(() => {
          void refreshPreview()
        }, 1500)
      } else if ((preview.value?.candidate_count || 0) > 0) {
        ElMessage.success('已找到可能的失物招领，可在右上角继续发布寻物启事')
      }
      return
    }

    const created = itemType.value === 'lost'
      ? await createLostItem(payload)
      : await createFoundItem(payload)
    if (created.status === 'active') {
      ElMessage.success('提交成功，已自动上架；匹配任务已受理，可在我的记录查看进度')
    } else {
      ElMessage.success(
        `提交成功，审核单号 ${created.review_ticket_no || '—'}；审核通过后将自动发起匹配`
      )
    }
    router.push('/my/items')
  } catch {
    // handled
  } finally {
    submitting.value = false
  }
}

async function confirmPublish() {
  if (!draft.value) return
  try {
    await ElMessageBox.confirm(
      '发布后记录将由系统自动校验并上架，同时进入正式匹配；候选将按正式口径展示。',
      '确认发布',
      { type: 'warning' }
    )
  } catch {
    return
  }
  publishing.value = true
  try {
    const result = await publishDraft(draft.value.draft_id)
    dialogResolved.value = true
    showNoCandidate.value = false
    ElMessage.success(
      result.status === 'active'
        ? `发布成功，已上架；审核单号 ${result.review_ticket_no || '—'}`
        : `发布成功，等待审核；单号 ${result.review_ticket_no || '—'}`
    )
    router.push('/my/items')
  } catch {
    // handled
  } finally {
    publishing.value = false
  }
}

async function doAbandon() {
  if (!draft.value) return
  dialogResolved.value = true
  try {
    await abandonDraft(draft.value.draft_id)
    ElMessage.info('已暂不发布，草稿保留 7 天')
  } catch {
    // handled
  } finally {
    draft.value = null
    preview.value = null
    showNoCandidate.value = false
    await router.replace({ path: '/publish', query: { type: 'lost' } })
  }
}

function closeNoCandidate() {
  showNoCandidate.value = false
  void doAbandon()
}

function handleDialogClosed() {
  if (!dialogResolved.value && draft.value) {
    void doAbandon()
  }
}

async function init() {
  try {
    const mode = await fetchPublishMode()
    publishMode.value = mode.publish_mode
  } catch {
    publishMode.value = 'direct'
  }
  const draftId = typeof route.query.draft === 'string' ? route.query.draft : ''
  if (draftId) {
    await loadDraft(draftId)
    if (draft.value) {
      form.title = draft.value.title
      form.description = draft.value.description
      form.category = draft.value.category
      form.color = draft.value.color || ''
      form.brand = draft.value.brand || ''
      form.location_code = draft.value.location_code || ''
      form.location_text = draft.value.location_text
      form.occurred_at = draft.value.occurred_at || ''
      noticeAccepted.value = true
    }
  }
}

onMounted(init)
watch(
  () => route.query.draft,
  (value) => {
    if (typeof value === 'string' && value && draft.value?.draft_id !== value) {
      void loadDraft(value)
    }
  }
)
</script>

<template>
  <section>
    <h2 class="section-title">{{ draft ? '匹配到的失物招领' : title }}</h2>

    <el-alert
      v-if="!draft"
      type="info"
      :title="stageHint"
      show-icon
      :closable="false"
      class="mb"
    />

    <el-form v-if="!draft" label-width="90px" class="publish-form">
      <el-form-item label="记录类型" required>
        <el-radio-group v-model="itemType">
          <el-radio-button value="lost">寻物启事</el-radio-button>
          <el-radio-button value="found">失物招领</el-radio-button>
        </el-radio-group>
      </el-form-item>

      <el-form-item label="物品图片">
        <el-upload
          :auto-upload="false"
          :show-file-list="false"
          accept="image/jpeg,image/png,image/webp"
          :on-change="(f: any) => handleUpload({ file: f.raw })"
        >
          <el-button :loading="uploading">上传图片（最多 5 张）</el-button>
        </el-upload>
        <div class="thumbs">
          <el-tag
            v-for="key in imageKeys"
            :key="key"
            closable
            class="thumb-tag"
            @close="removeImage(key)"
          >
            {{ key.slice(0, 10) }}…
          </el-tag>
        </div>
      </el-form-item>

      <el-form-item label="标题" required>
        <el-input v-model="form.title" maxlength="120" show-word-limit placeholder="例如：黑色无线耳机" />
      </el-form-item>
      <el-form-item label="描述">
        <el-input
          v-model="form.description"
          type="textarea"
          :rows="3"
          maxlength="5000"
          placeholder="描述外观、特征、可能遗失/拾获的位置等；无图片时至少 20 字"
        />
        <div class="muted">
          当前信息量：{{ infoSufficient ? '充足，可提交' : '图片或 20 字以上描述至少满足其一' }}
        </div>
      </el-form-item>
      <el-form-item label="AI 识别">
        <el-button :loading="recognizing" @click="recognize">AI 识别特征</el-button>
        <span class="muted">识别结果可修改，失败时可手动填写</span>
      </el-form-item>
      <el-alert
        v-if="aiDegraded || aiWarnings.length"
        type="warning"
        :title="aiDegraded ? '当前为降级状态：未调用真实模型，请自行核对填写' : '识别提示'"
        :description="aiWarnings.join('；')"
        show-icon
        :closable="false"
        class="mb"
      />
      <el-form-item label="类别" required>
        <el-select v-model="form.category" placeholder="请选择类别">
          <el-option v-for="c in CATEGORIES" :key="c" :label="c" :value="c" />
        </el-select>
      </el-form-item>
      <el-form-item label="颜色">
        <el-input v-model="form.color" maxlength="40" />
      </el-form-item>
      <el-form-item label="品牌">
        <el-input v-model="form.brand" maxlength="80" />
      </el-form-item>
      <el-form-item label="地点" required>
        <el-input v-model="form.location_text" maxlength="200" placeholder="例如：教学楼二楼" />
      </el-form-item>
      <el-form-item label="地点编码">
        <el-input v-model="form.location_code" maxlength="100" placeholder="可选，用于地点层级匹配，如：教学楼/二楼" />
      </el-form-item>
      <el-form-item :label="timeLabel">
        <el-date-picker v-model="form.occurred_at" type="datetime" placeholder="选择时间（不超过当前）" />
      </el-form-item>
      <el-form-item>
        <el-checkbox v-model="noticeAccepted">
          我已阅读并同意匹配告知：系统将对记录进行相似度匹配，匹配结果不代表物品归属，交接前需线下核验。
        </el-checkbox>
      </el-form-item>
      <el-form-item>
        <el-button type="primary" :loading="submitting" @click="submit">{{ submitLabel }}</el-button>
      </el-form-item>
    </el-form>

    <div v-else class="preview-wrap">
      <div class="preview-actions">
        <el-button @click="doAbandon">暂不发布</el-button>
        <el-button type="primary" :loading="publishing" @click="confirmPublish">
          继续发布寻物启事
        </el-button>
      </div>

      <el-alert
        v-if="preview?.degraded"
        type="warning"
        :title="preview.degraded_reason || '匹配服务降级，结果可能不完整'"
        show-icon
        :closable="false"
        class="mb"
      />

      <div v-if="preview?.status === 'processing'" v-loading="previewLoading" class="state-box">
        正在匹配失物招领…
        <el-button link type="primary" @click="refreshPreview">刷新</el-button>
      </div>
      <el-empty
        v-else-if="!preview?.candidates.length"
        description="暂未找到相似的失物招领"
      />
      <div v-else class="candidate-list">
        <el-card
          v-for="c in preview.candidates"
          :key="c.candidate_public_id"
          class="candidate"
        >
          <div class="candidate-head">
            <strong>{{ c.title_excerpt }}</strong>
            <span class="score">{{ c.score.toFixed(1) }} 分</span>
            <el-tag v-if="c.low_similar" type="warning" size="small">
              相似度较低，请谨慎核验
            </el-tag>
            <el-tag v-if="c.requires_offline_verification" type="danger" size="small">
              需线下核验
            </el-tag>
          </div>
          <div class="candidate-meta">
            {{ c.category }} · {{ c.color || '颜色未知' }} · {{ c.area_name }} ·
            {{ c.occurred_on || '时间未知' }}
          </div>
          <p class="candidate-desc">{{ c.description_excerpt }}</p>
          <p v-if="c.reasons.length" class="muted">依据：{{ c.reasons.join('；') }}</p>
        </el-card>
        <p class="muted">{{ preview.disclaimer }}</p>
      </div>
    </div>

    <el-dialog
      v-model="showNoCandidate"
      title="暂未找到相似的失物招领"
      width="460px"
      @closed="handleDialogClosed"
    >
      <p>暂未找到相似的失物招领。是否发布寻物启事，让拾获者通过匹配找到你？</p>
      <template #footer>
        <el-button @click="closeNoCandidate">暂不发布</el-button>
        <el-button type="primary" :loading="publishing" @click="confirmPublish">
          发布寻物启事
        </el-button>
      </template>
    </el-dialog>
  </section>
</template>

<style scoped>
.publish-form {
  background: #fff;
  border-radius: 10px;
  padding: 20px 20px 4px;
  border: 1px solid #eef0f4;
  max-width: 760px;
}
.mb {
  margin-bottom: 16px;
}
.muted {
  color: #9ca3af;
  font-size: 13px;
  margin-top: 6px;
}
.thumbs {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 8px;
}
.preview-wrap {
  background: #fff;
  border-radius: 10px;
  border: 1px solid #eef0f4;
  padding: 0 20px 20px;
  max-width: 860px;
}
.preview-actions {
  position: sticky;
  top: 0;
  z-index: 10;
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  padding: 12px 0;
  background: #fff;
  border-bottom: 1px solid #eef0f4;
  margin-bottom: 14px;
}
.candidate-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.candidate-head {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}
.score {
  color: #4f46e5;
  font-weight: 600;
}
.candidate-meta {
  color: #6b7280;
  font-size: 13px;
  margin-top: 6px;
}
.candidate-desc {
  color: #374151;
  margin: 8px 0 0;
  line-height: 1.6;
}
.state-box {
  min-height: 160px;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  color: #6b7280;
}
@media (max-width: 767px) {
  .preview-actions {
    justify-content: stretch;
  }
  .preview-actions .el-button {
    flex: 1;
  }
}
</style>