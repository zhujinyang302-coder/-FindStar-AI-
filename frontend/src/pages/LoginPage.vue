<script setup lang="ts">
import { reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { useAuthStore } from '@/stores/auth'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()

const form = reactive({ email: '', password: '' })
const loading = ref(false)

async function submit() {
  if (!form.email || !form.password) {
    ElMessage.warning('请输入账号与密码')
    return
  }
  loading.value = true
  try {
    await auth.login(form.email, form.password)
    ElMessage.success('登录成功')
    const redirect = (route.query.redirect as string) || '/'
    router.push(redirect)
  } catch {
    // handled
  } finally {
    loading.value = false
  }
}

function fill(email: string, password: string) {
  form.email = email
  form.password = password
}
</script>

<template>
  <section class="login-wrap">
    <el-card>
      <h2>登录寻物星图</h2>
      <el-form label-position="top" @submit.prevent="submit">
        <el-form-item label="账号（邮箱）">
          <el-input v-model="form.email" placeholder="请输入邮箱" />
        </el-form-item>
        <el-form-item label="密码">
          <el-input v-model="form.password" type="password" show-password placeholder="请输入密码" @keyup.enter="submit" />
        </el-form-item>
        <el-button type="primary" :loading="loading" class="full" @click="submit">登录</el-button>
      </el-form>
      <el-divider>演示账号（仅开发环境）</el-divider>
      <div class="demo">
        <el-button size="small" @click="fill('admin@findstar.demo', 'DemoAdmin@2026')">管理员</el-button>
        <el-button size="small" @click="fill('alice@findstar.demo', 'User@2026')">普通用户</el-button>
      </div>
      <p class="muted">正式环境请使用部署环境配置的账号；演示账号不应写入前端代码仓库。</p>
    </el-card>
  </section>
</template>

<style scoped>
.login-wrap {
  display: flex;
  justify-content: center;
  padding-top: 40px;
}
.login-wrap :deep(.el-card) {
  width: 380px;
}
.full {
  width: 100%;
}
.demo {
  display: flex;
  gap: 10px;
  justify-content: center;
}
.muted {
  color: #9ca3af;
  font-size: 12px;
  margin-top: 12px;
}
</style>