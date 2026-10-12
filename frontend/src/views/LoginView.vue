<template>
  <div class="min-h-screen bg-gradient-to-br from-slate-900 to-slate-700 flex items-center justify-center p-4">
    <div class="bg-white rounded-2xl shadow-2xl w-full max-w-sm p-8">
      <div class="text-center mb-8">
        <div class="text-5xl mb-3"></div>
        <h1 class="text-2xl font-bold text-gray-900"></h1>
        <p class="text-gray-500 text-sm mt-1">Подсистема управления складом</p>
      </div>

      <form @submit.prevent="handleLogin" class="space-y-4">
        <div>
          <label class="label">Имя пользователя</label>
          <input
            v-model="username"
            type="text"
            class="input text-base"
            placeholder="admin"
            autocomplete="username"
            required
          />
        </div>
        <div>
          <label class="label">Пароль</label>
          <input
            v-model="password"
            type="password"
            class="input text-base"
            placeholder="••••••"
            autocomplete="current-password"
            required
          />
        </div>

        <div v-if="auth.error" class="bg-red-50 text-red-700 text-sm rounded-lg px-4 py-2.5">
          {{ auth.error }}
        </div>

        <button
          type="submit"
          class="btn-primary w-full py-3 text-base mt-2"
          :disabled="auth.loading"
        >
          <span v-if="auth.loading">Вход...</span>
          <span v-else>Войти</span>
        </button>
      </form>

      <p class="text-center text-xs text-gray-400 mt-6">
        <strong></strong>  <strong></strong>
      </p>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()
const router = useRouter()
const username = ref('')
const password = ref('')

async function handleLogin() {
  const ok = await auth.login(username.value, password.value)
  if (ok) {
    if (auth.isAdmin || auth.isManager) router.push('/dashboard')
    else router.push('/')
  }
}
</script>
