<template>
  <ManagerLayout>
    <div class="space-y-4">
      <div class="flex flex-wrap gap-3 items-end">
        <select v-model="filterType" class="input w-44">
          <option value="">Все типы</option>
          <option value="ARRIVAL">Приёмка</option>
          <option value="CONSUMPTION">Расход</option>
          <option value="INVENTORY">Инвентаризация</option>
        </select>
        <select v-model="filterStatus" class="input w-44">
          <option value="">Все статусы</option>
          <option value="PENDING">Ожидает</option>
          <option value="IN_PROGRESS">В работе</option>
          <option value="COMPLETED">Завершён</option>
          <option value="CANCELLED">Отменён</option>
        </select>
        <label class="text-sm text-gray-600">
          С
          <input v-model="dateFrom" type="date" class="input ml-1" />
        </label>
        <label class="text-sm text-gray-600">
          По
          <input v-model="dateTo" type="date" class="input ml-1" />
        </label>
        <button @click="load" class="btn-secondary">Обновить</button>
      </div>
      <p class="text-xs text-gray-500">
        Показано до {{ orders.length }} заказов. История из генератора — заказы «Расход» (по одному на день за год).
      </p>

      <div class="card p-0 overflow-hidden">
        <div v-if="loading" class="p-6 space-y-2">
          <div v-for="i in 5" :key="i" class="skeleton h-12 w-full"></div>
        </div>
        <table v-else class="w-full text-sm">
          <thead class="bg-gray-50 border-b border-gray-100">
            <tr class="text-left text-gray-500">
              <th class="px-4 py-3 font-medium">№</th>
              <th class="px-4 py-3 font-medium">Тип</th>
              <th class="px-4 py-3 font-medium">Статус</th>
              <th class="px-4 py-3 font-medium">Позиций</th>
              <th class="px-4 py-3 font-medium">Создан</th>
              <th class="px-4 py-3 font-medium">Закрыт</th>
              <th class="px-4 py-3 font-medium">Пользователь</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-gray-50">
            <tr v-for="o in orders" :key="o.id" class="hover:bg-gray-50 cursor-pointer" @click="selected = o">
              <td class="px-4 py-3 font-mono text-gray-500">#{{ o.id }}</td>
              <td class="px-4 py-3"><OrderTypeBadge :type="o.type" /></td>
              <td class="px-4 py-3"><OrderStatusBadge :status="o.status" /></td>
              <td class="px-4 py-3 text-gray-600">{{ o.items?.length ?? 0 }}</td>
              <td class="px-4 py-3 text-gray-500">{{ fmt(o.created_at) }}</td>
              <td class="px-4 py-3 text-gray-500">{{ o.closed_at ? fmt(o.closed_at) : '—' }}</td>
              <td class="px-4 py-3 text-gray-500">{{ o.created_by ?? '—' }}</td>
            </tr>
          </tbody>
        </table>
        <div v-if="!loading && !orders.length" class="text-center text-gray-400 py-12 text-sm">Нет заказов</div>
      </div>

      <!-- Detail modal -->
      <div v-if="selected" class="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4" @click.self="selected = null">
        <div class="bg-white rounded-2xl shadow-xl w-full max-w-lg max-h-[80vh] overflow-y-auto p-6">
          <div class="flex justify-between items-start mb-4">
            <div>
              <h3 class="text-lg font-bold">Заказ #{{ selected.id }}</h3>
              <div class="flex gap-2 mt-1">
                <OrderTypeBadge :type="selected.type" />
                <OrderStatusBadge :status="selected.status" />
              </div>
            </div>
            <button @click="selected = null" class="text-gray-400 hover:text-gray-600 text-2xl">✕</button>
          </div>

          <div class="flex flex-wrap gap-2 mb-4">
            <router-link
              v-if="selected.type === 'INVENTORY' && (selected.status === 'PENDING' || selected.status === 'IN_PROGRESS')"
              to="/inventory"
              class="btn-primary text-sm"
              @click="selected = null"
            >
              Открыть пересчёт
            </router-link>
            <button
              class="btn-secondary"
              :disabled="deleting"
              @click="deleteSelected"
              :title="isHistoryStatus(selected.status) ? 'Удалить запись из истории заказов' : 'Удалить (отменить) заказ'"
            >
              {{ deleting ? '...' : (isHistoryStatus(selected.status) ? 'Удалить из истории' : 'Отменить заказ') }}
            </button>
          </div>
          <table class="w-full text-sm">
            <thead><tr class="text-gray-400 border-b text-left">
              <th class="pb-2">SKU</th><th class="pb-2">Ячейка</th>
              <th class="pb-2 text-right">{{ selected.type === 'INVENTORY' ? 'Учёт' : 'Кол-во' }}</th>
              <th class="pb-2 text-right">Факт</th>
            </tr></thead>
            <tbody class="divide-y">
              <tr v-for="it in selected.items" :key="it.id">
                <td class="py-2 font-mono text-blue-700">{{ it.product_sku }}</td>
                <td class="py-2 text-gray-600">{{ it.cell_address ?? '—' }}</td>
                <td class="py-2 text-right">{{ it.quantity }}</td>
                <td class="py-2 text-right text-gray-400">{{ it.quantity_fact ?? '—' }}</td>
              </tr>
            </tbody>
          </table>
          <p v-if="selected.comment" class="text-xs text-gray-400 mt-3">{{ selected.comment }}</p>

          <div v-if="selected.type === 'INVENTORY'" class="mt-4 pt-4 border-t border-gray-100">
            <h4 class="font-semibold text-gray-700 mb-2">Потери и излишки</h4>
            <InventoryLossesTable
              :summary="inventoryLosses"
              :loading="loadingInventoryLosses"
            />
          </div>
        </div>
      </div>
    </div>
  </ManagerLayout>
</template>

<script setup>
import { ref, watch, onMounted } from 'vue'
import ManagerLayout from '@/layouts/ManagerLayout.vue'
import OrderTypeBadge from '@/components/OrderTypeBadge.vue'
import OrderStatusBadge from '@/components/OrderStatusBadge.vue'
import InventoryLossesTable from '@/components/InventoryLossesTable.vue'
import { warehouseApi } from '@/api'

const orders = ref([])
const loading = ref(true)
const filterType = ref('')
const filterStatus = ref('')

function defaultDateRange() {
  const to = new Date()
  const from = new Date()
  from.setFullYear(from.getFullYear() - 1)
  const fmt = d => d.toISOString().slice(0, 10)
  return { from: fmt(from), to: fmt(to) }
}

const { from: defaultFrom, to: defaultTo } = defaultDateRange()
const dateFrom = ref(defaultFrom)
const dateTo = ref(defaultTo)
const selected = ref(null)
const deleting = ref(false)
const inventoryLosses = ref(null)
const loadingInventoryLosses = ref(false)

function fmt(dt) { return new Date(dt).toLocaleString('ru-RU', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' }) }

async function load() {
  loading.value = true
  try {
    const params = { limit: 1000 }
    if (filterType.value) params.type = filterType.value
    if (filterStatus.value) params.status = filterStatus.value
    if (dateFrom.value) params.date_from = dateFrom.value
    if (dateTo.value) params.date_to = dateTo.value
    const { data } = await warehouseApi.orders(params)
    orders.value = data
  } finally { loading.value = false }
}

async function deleteSelected() {
  if (!selected.value) return
  const id = selected.value.id
  const deletingHistory = isHistoryStatus(selected.value.status)
  const ok = deletingHistory
    ? confirm(`Удалить запись заказа #${id} из истории?`)
    : confirm(`Отменить заказ #${id}?`)
  if (!ok) return
  deleting.value = true
  try {
    if (deletingHistory) {
      await warehouseApi.deleteOrderHistory(id)
    } else {
      await warehouseApi.deleteOrder(id)
    }
    selected.value = null
    await load()
  } catch (e) {
    alert(e.response?.data?.detail || 'Ошибка удаления записи заказа')
  } finally {
    deleting.value = false
  }
}

function isHistoryStatus(status) {
  return status === 'COMPLETED' || status === 'CANCELLED'
}

watch(selected, async o => {
  inventoryLosses.value = null
  if (!o || o.type !== 'INVENTORY') return
  loadingInventoryLosses.value = true
  try {
    const { data } = await warehouseApi.inventoryLosses(o.id)
    inventoryLosses.value = data
  } catch {
    inventoryLosses.value = null
  } finally {
    loadingInventoryLosses.value = false
  }
})

onMounted(load)
</script>
