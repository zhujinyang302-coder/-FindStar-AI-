import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import client from '@/api/client'
import type { LoginResult, UserInfo } from '@/types'

const TOKEN_KEY = 'findstar_token'
const USER_KEY = 'findstar_user'

function readUser(): UserInfo | null {
  try {
    return JSON.parse(localStorage.getItem(USER_KEY) || 'null') as UserInfo | null
  } catch {
    return null
  }
}

export const useAuthStore = defineStore('auth', () => {
  const token = ref<string | null>(localStorage.getItem(TOKEN_KEY))
  const user = ref<UserInfo | null>(readUser())

  const isLoggedIn = computed(() => !!token.value)
  const isAdmin = computed(() => user.value?.role === 'admin')

  async function login(email: string, password: string): Promise<LoginResult> {
    const data = (await client.post('/auth/login', { email, password })) as unknown as LoginResult
    token.value = data.access_token
    user.value = data.user
    localStorage.setItem(TOKEN_KEY, data.access_token)
    localStorage.setItem(USER_KEY, JSON.stringify(data.user))
    return data
  }

  function logout() {
    token.value = null
    user.value = null
    localStorage.removeItem(TOKEN_KEY)
    localStorage.removeItem(USER_KEY)
  }

  return { token, user, isLoggedIn, isAdmin, login, logout }
})