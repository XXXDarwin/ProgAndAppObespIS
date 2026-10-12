<template>
  <WorkerLayout>
    <div class="py-4">
      <h2 class="text-xl font-bold text-gray-800 mb-1">Добро пожаловать, {{ auth.user?.username }}!</h2>
      <p class="text-gray-500 text-sm mb-6">Выберите операцию</p>

      <div class="flex flex-col gap-3">
        <router-link
          to="/arrival"
          class="card flex items-center gap-4 py-5 px-5 hover:shadow-md hover:border-blue-200 transition-all"
        >
          <div class="w-10 h-10 rounded-lg bg-blue-100 text-blue-700 flex items-center justify-center font-bold text-sm shrink-0">
            IN
          </div>
          <div class="flex-1 min-w-0">
            <span class="font-semibold text-gray-700 text-lg block">Приёмка</span>
            <span class="text-xs text-gray-400">Заказы на приёмку</span>
          </div>
          <span v-if="pendingArrival > 0" class="shrink-0 bg-blue-600 text-white text-xs font-bold px-2.5 py-1 rounded-full">
            {{ pendingArrival }}
          </span>
        </router-link>

        <router-link
          to="/dispatch"
          class="card flex items-center gap-4 py-5 px-5 hover:shadow-md hover:border-green-200 transition-all"
        >
          <div class="w-10 h-10 rounded-lg bg-green-100 text-green-700 flex items-center justify-center font-bold text-sm shrink-0">
            OUT
          </div>
          <div class="flex-1 min-w-0">
            <span class="font-semibold text-gray-700 text-lg block">Расход</span>
            <span class="text-xs text-gray-400">Заказы на отгрузку</span>
          </div>
          <span v-if="pendingDispatch > 0" class="shrink-0 bg-green-600 text-white text-xs font-bold px-2.5 py-1 rounded-full">
            {{ pendingDispatch }}
          </span>
        </router-link>

        <router-link
          to="/move"
          class="card flex items-center gap-4 py-5 px-5 hover:shadow-md hover:border-purple-200 transition-all"
        >
          <div class="w-10 h-10 rounded-lg bg-purple-100 text-purple-700 flex items-center justify-center font-bold text-sm shrink-0">
            MV
          </div>
          <div>
            <span class="font-semibold text-gray-700 text-lg block">Перемещение</span>
            <span class="text-xs text-gray-400">Между ячейками</span>
          </div>
        </router-link>

        <router-link
          to="/inventory"
          class="card flex items-center gap-4 py-5 px-5 hover:shadow-md hover:border-yellow-200 transition-all"
        >
          <div class="w-10 h-10 rounded-lg bg-yellow-100 text-yellow-800 flex items-center justify-center font-bold text-sm shrink-0">
            INV
          </div>
          <div class="flex-1 min-w-0">
            <span class="font-semibold text-gray-700 text-lg block">Инвентаризация</span>
            <span class="text-xs text-gray-400">Пересчёт по стеллажам</span>
          </div>
          <span v-if="pendingInventory > 0" class="shrink-0 bg-yellow-600 text-white text-xs font-bold px-2.5 py-1 rounded-full">
            {{ pendingInventory }}
          </span>
        </router-link>
      </div>

      <div class="mt-6 card">
        <h3 class="font-semibold text-gray-700 mb-3">Сводка по складу</h3>
        <div v-if="loadingSummary" class="space-y-2">
          <div class="skeleton h-5 w-3/4"></div>
          <div class="skeleton h-5 w-1/2"></div>
        </div>
        <div v-else class="grid grid-cols-2 gap-3 text-sm">
          <div class="bg-blue-50 rounded-lg p-3 text-center">
            <div class="text-2xl font-bold text-blue-700">{{ summary.totalProducts }}</div>
            <div class="text-blue-500 text-xs mt-0.5">Видов товаров</div>
          </div>
          <div class="bg-green-50 rounded-lg p-3 text-center">
            <div class="text-2xl font-bold text-green-700">{{ summary.totalStock }}</div>
            <div class="text-green-500 text-xs mt-0.5">Ед. на складе</div>
          </div>
        </div>
      </div>
    </div>
  </WorkerLayout>
</template>

<script setup>
import { ref, onMounted, onActivated } from 'vue'
import WorkerLayout from '@/layouts/WorkerLayout.vue'
import { useAuthStore } from '@/stores/auth'
import { warehouseApi } from '@/api'

const auth = useAuthStore()
const loadingSummary = ref(true)
const summary = ref({ totalProducts: 0, totalStock: 0 })
const pendingDispatch = ref(0)
const pendingArrival = ref(0)
const pendingInventory = ref(0)

async function loadSummary() {
  loadingSummary.value = true
  try {
    const [stocksRes, consPending, consProgress, arrPending, arrProgress, invPending, invProgress] = await Promise.all([
      warehouseApi.stocks(),
      warehouseApi.orders({ type: 'CONSUMPTION', status: 'PENDING', limit: 100 }),
      warehouseApi.orders({ type: 'CONSUMPTION', status: 'IN_PROGRESS', limit: 100 }),
      warehouseApi.orders({ type: 'ARRIVAL', status: 'PENDING', limit: 100 }),
      warehouseApi.orders({ type: 'ARRIVAL', status: 'IN_PROGRESS', limit: 100 }),
      warehouseApi.orders({ type: 'INVENTORY', status: 'PENDING', limit: 100 }),
      warehouseApi.orders({ type: 'INVENTORY', status: 'IN_PROGRESS', limit: 100 }),
    ])
    let invRacksLeft = 0
    const invOrders = [...invPending.data, ...invProgress.data]
    await Promise.all(
      invOrders.map(async o => {
        try {
          const { data: taskList } = await warehouseApi.inventoryTasks(o.id)
          invRacksLeft += taskList.filter(t => t.status !== 'COMPLETED').length
        } catch {
          invRacksLeft += 1
        }
      }),
    )
    const data = stocksRes.data
    summary.value = {
      totalProducts: new Set(data.map(s => s.product_id)).size,
      totalStock: data.reduce((sum, s) => sum + s.quantity, 0),
    }
    pendingDispatch.value = consPending.data.length + consProgress.data.length
    pendingArrival.value = arrPending.data.length + arrProgress.data.length
    pendingInventory.value = invRacksLeft
  } catch {
    /* ignore */
  } finally {
    loadingSummary.value = false
  }
}

onMounted(loadSummary)
onActivated(loadSummary)
</script>
