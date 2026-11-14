<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { fetchPublicStats } from '@/api'
import { useAuthStore } from '@/stores/auth'
import type { PublicStats } from '@/types'

const router = useRouter()
const auth = useAuthStore()
const stats = ref<PublicStats | null>(null)

async function load() {
  try {
    stats.value = await fetchPublicStats()
  } catch {
    stats.value = null
  }
}

onMounted(load)
</script>

<template>
  <section>
    <div class="hero">
      <h1>寻物星图 FindStar</h1>
      <p>不上传公开榜单，只做定向匹配。上传你的记录，AI 会为你寻找高相似度的对侧信息。</p>
      <div class="actions">
        <template v-if="auth.isLoggedIn && !auth.isAdmin">
          <el-button type="primary" size="large" @click="router.push('/publish?type=lost')">
            我丢了东西
          </el-button>
          <el-button type="success" size="large" @click="router.push('/publish?type=found')">
            我捡到东西
          </el-button>
          <el-button size="large" @click="router.push('/my/items')">我的记录</el-button>
        </template>
        <template v-else-if="auth.isAdmin">
          <el-button type="warning" size="large" @click="router.push('/admin')">进入审核工作台</el-button>
        </template>
        <template v-else>
          <el-button type="primary" size="large" @click="router.push('/login')">登录后开始</el-button>
        </template>
      </div>
    </div>

    <div class="stat-row">
      <div class="stat-card">
        <div class="value">{{ stats?.completed_total ?? '—' }}</div>
        <div class="label">累计完成找回</div>
      </div>
      <div class="stat-card">
        <div class="value">3 步</div>
        <div class="label">上传 → 审核 → 定向匹配</div>
      </div>
      <div class="stat-card">
        <div class="value">0</div>
        <div class="label">对侧全量记录可见</div>
      </div>
    </div>

    <el-card class="how">
      <h3>工作方式</h3>
      <ol>
        <li>寻物侧：填写丢失信息后，系统先匹配现有失物招领；你可以先查看 50% 以上相似度的候选，再决定是否发布寻物启事。</li>
        <li>拾获侧：提交后由系统自动校验并立即上架，同时自动发起匹配。</li>
        <li>匹配只展示少量候选，分数不代表物品归属；确认交接前必须线下核验。</li>
        <li>你提交认领或归还线索，由对侧记录发布者确认；确认后双方才看到交接点位。</li>
      </ol>
      <el-button link type="primary" @click="router.push('/privacy')">查看隐私与可见性说明</el-button>
    </el-card>
  </section>
</template>

<style scoped>
.hero {
  background: #fff;
  border-radius: 12px;
  padding: 32px 24px;
  border: 1px solid #eef0f4;
  margin-bottom: 24px;
}
.hero h1 {
  margin: 0 0 8px;
  font-size: 28px;
}
.hero p {
  color: #6b7280;
  margin: 0 0 18px;
  line-height: 1.7;
}
.actions {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
}
.how {
  margin-top: 8px;
  line-height: 1.9;
  color: #4b5563;
}
</style>