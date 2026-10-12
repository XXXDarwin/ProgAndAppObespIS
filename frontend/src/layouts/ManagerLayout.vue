<template>
  <div class="flex h-screen bg-gray-50">
    <!-- Sidebar -->
    <aside class="w-60 bg-slate-900 text-white flex flex-col shrink-0">
      <div class="px-5 py-4 border-b border-slate-700">
        <div class="text-lg font-bold text-white"></div>
        <div class="text-xs text-slate-400 mt-0.5">Подсистема управления складом</div>
      </div>

      <nav class="flex-1 px-3 py-4 space-y-1 overflow-y-auto">
        <NavItem to="/dashboard">Аналитика</NavItem>
        <NavItem to="/stocks">Остатки</NavItem>
        <NavItem to="/orders">Заказы</NavItem>
        <NavItem to="/moves">Перемещения</NavItem>
        <NavItem to="/forecast">Прогнозирование</NavItem>

        <div class="pt-3 pb-1 text-xs font-semibold text-slate-500 uppercase tracking-wider px-2">Справочники</div>
        <NavItem to="/products">Товары</NavItem>
        <NavItem to="/cells">Ячейки</NavItem>
        <NavItem to="/warehouse-map">Зоны склада</NavItem>
        <NavItem v-if="auth.isAdmin" to="/users">Пользователи</NavItem>

        <div class="pt-3 pb-1 text-xs font-semibold text-slate-500 uppercase tracking-wider px-2">Склад</div>
        <NavItem to="/arrival-requests">Заказы на приёмку</NavItem>
        <NavItem to="/consumption-requests">Заказы на расход</NavItem>
        <NavItem to="/inventory-requests">Инвентаризация</NavItem>
      </nav>

      <!-- User block -->
      <div class="px-4 py-3 border-t border-slate-700 flex items-center gap-3">
        <div class="w-8 h-8 rounded-full bg-blue-500 flex items-center justify-center text-sm font-bold shrink-0">
          {{ auth.user?.username?.[0]?.toUpperCase() }}
        </div>
        <div class="min-w-0">
          <div class="text-sm font-medium text-white truncate">{{ auth.user?.username }}</div>
          <div class="text-xs text-slate-400">{{ roleLabel }}</div>
        </div>
        <button @click="doLogout" class="ml-auto text-slate-400 hover:text-white transition" title="Выйти">
          <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
              d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1"/>
          </svg>
        </button>
      </div>
    </aside>

    <!-- Main -->
    <div class="flex-1 flex flex-col overflow-hidden">
      <header class="bg-white border-b border-gray-200 px-6 py-3 flex items-center justify-between shrink-0">
        <h1 class="text-lg font-semibold text-gray-800">{{ pageTitle }}</h1>
        <div class="text-sm text-gray-500">{{ currentDate }}</div>
      </header>
      <main class="flex-1 overflow-y-auto p-6">
        <slot />
      </main>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import NavItem from '@/components/NavItem.vue'

const auth = useAuthStore()
const router = useRouter()
const route = useRoute()

const roleLabel = computed(() => ({ ADMIN: 'Администратор', MANAGER: 'Менеджер', WORKER: 'Кладовщик' }[auth.user?.role] ?? ''))
const currentDate = computed(() => new Date().toLocaleDateString('ru-RU', { weekday: 'long', day: 'numeric', month: 'long' }))
const pageTitle = computed(() => route.meta?.title ?? '')

function doLogout() {
  auth.logout()
  router.push('/login')
}
</script>
