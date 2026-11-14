<script setup lang="ts">
import { useRouter } from 'vue-router'

const router = useRouter()
</script>

<template>
  <section class="privacy">
    <h2 class="section-title">隐私与可见性说明</h2>
    <el-card>
      <h3>我们如何保护信息</h3>
      <ul>
        <li>任何人不能浏览全部失物或拾获记录，也不能进行全局关键词检索。</li>
        <li>你上传记录后，仅你本人可以看到完整内容；记录需经管理员审核通过后才会参与匹配。</li>
        <li>匹配结果只展示模糊到日的时间、校园区域和摘要信息，不展示对方身份、账号与联系方式。</li>
        <li>只有在提交申请并经对方确认后，双方才能看到约定的交接点位与时间窗口，仍需线下核验。</li>
        <li>管理员只负责记录的上架与下架审核，不能查看匹配候选与私密核验信息。</li>
      </ul>
      <div class="actions">
        <el-button type="primary" @click="router.push('/')">返回首页</el-button>
      </div>
    </el-card>
  </section>
</template>

<style scoped>
.privacy {
  max-width: 760px;
  margin: 0 auto;
}
ul {
  line-height: 1.9;
  color: #4b5563;
}
.actions {
  margin-top: 18px;
}
</style>