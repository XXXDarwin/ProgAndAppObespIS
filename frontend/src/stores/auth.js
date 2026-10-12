import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { authApi } from '@/api'

export const useAuthStore = defineStore('auth', () => {
  const user = ref(null)
  const loading = ref(false)
  const error = ref(null)

  const userRole = computed(() => String(user.value?.role ?? '').toUpperCase())

  const isAuthenticated = computed(() => !!user.value)
  const isAdmin    = computed(() => userRole.value === 'ADMIN')
  const isManager  = computed(() => ['ADMIN', 'MANAGER'].includes(userRole.value))
  const isWorker   = computed(() => userRole.value === 'WORKER')

  async function login(username, password) {
    loading.value = true
    error.value = null
    try {
      const { data } = await authApi.login(username, password)
      localStorage.setItem('access_token', data.access_token)
      localStorage.setItem('refresh_token', data.refresh_token)
      await fetchMe()
      return true
    } catch (e) {
      error.value = e.response?.data?.detail || 'Ошибка входа'
      return false
    } finally {
      loading.value = false
    }
  }

  async function fetchMe() {
    try {
      const { data } = await authApi.me()
      user.value = data
    } catch {
      logout()
    }
  }

  function logout() {
    user.value = null
    localStorage.removeItem('access_token')
    localStorage.removeItem('refresh_token')
  }

  // Восстановление сессии при перезагрузке
  async function init() {
    if (localStorage.getItem('access_token')) {
      await fetchMe()
    }
  }

  return {
    user, loading, error, userRole,
    isAuthenticated, isAdmin, isManager, isWorker,
    login, logout, init, fetchMe,
  }
})
