<template>
  <div class="min-h-screen bg-gray-100 flex flex-col">
    <!-- Top bar -->
    <header class="bg-slate-900 text-white px-4 py-3 flex items-center justify-between">
      <div class="flex items-center gap-3">
        <span class="text-xl"></span>
        <span class="font-bold text-base">Подсистема Склада</span>
      </div>
      <div class="flex items-center gap-3">
        <span class="text-sm text-slate-300">{{ auth.user?.username }}</span>
        <button @click="doLogout" class="text-slate-400 hover:text-white transition">
          <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
              d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1"/>
          </svg>
        </button>
      </div>
    </header>
    <main class="flex-1 p-4 max-w-2xl mx-auto w-full">
      <slot />
    </main>
  </div>
</template>

<script setup>
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()
const router = useRouter()
function doLogout() { auth.logout(); router.push('/login') }
</script>
