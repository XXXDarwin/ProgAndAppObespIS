<template>
  <ManagerLayout>
    <div class="space-y-4">
      <div class="flex gap-3 flex-wrap">
        <button @click="load" class="btn-secondary">Обновить</button>
        <select v-model.number="limit" class="input w-40">
          <option :value="100">100</option>
          <option :value="200">200</option>
          <option :value="500">500</option>
          <option :value="1000">1000</option>
        </select>
      </div>

      <div class="card p-0 overflow-hidden">
        <div v-if="loading" class="p-6 space-y-2"><div v-for="i in 6" :key="i" class="skeleton h-10 w-full"></div></div>

        <table v-else class="w-full text-sm">
          <thead class="bg-gray-50 border-b border-gray-100">
            <tr class="text-left text-gray-500">
              <th class="px-4 py-3 font-medium">Дата</th>
              <th class="px-4 py-3 font-medium">Пользователь</th>
              <th class="px-4 py-3 font-medium">Товар</th>
              <th class="px-4 py-3 font-medium">Откуда</th>
              <th class="px-4 py-3 font-medium">Куда</th>
              <th class="px-4 py-3 font-medium text-right">Кол-во</th>
              <th class="px-4 py-3 font-medium text-right">Действия</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-gray-50">
            <tr v-for="m in moves" :key="m.id" class="hover:bg-gray-50">
              <td class="px-4 py-2.5 text-gray-500 text-xs">{{ fmt(m.created_at) }}</td>
              <td class="px-4 py-2.5 text-gray-700">{{ m.username ?? '—' }}</td>
              <td class="px-4 py-2.5">
                <div class="font-mono font-semibold text-blue-700">{{ m.product_sku ?? `#${m.product_id}` }}</div>
                <div class="text-xs text-gray-400 truncate max-w-[260px]">{{ m.product_name ?? '—' }}</div>
              </td>
              <td class="px-4 py-2.5 font-mono text-gray-700">{{ m.from_cell_address ?? `#${m.from_cell_id}` }}</td>
              <td class="px-4 py-2.5 font-mono text-gray-700">{{ m.to_cell_address ?? `#${m.to_cell_id}` }}</td>
              <td class="px-4 py-2.5 text-right font-semibold text-gray-800">{{ m.quantity }}</td>
              <td class="px-4 py-2.5 text-right">
                <button
                  class="btn-secondary"
                  :disabled="deletingId === m.id"
                  @click="deleteMoveRow(m)"
                >
                  {{ deletingId === m.id ? '...' : 'Удалить' }}
                </button>
              </td>
            </tr>
          </tbody>
        </table>

        <div v-if="!loading && !moves.length" class="text-center text-gray-400 py-12 text-sm">Перемещений нет</div>
      </div>
    </div>
  </ManagerLayout>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import ManagerLayout from '@/layouts/ManagerLayout.vue'
import { warehouseApi } from '@/api'

const moves = ref([])
const loading = ref(true)
const limit = ref(200)
const deletingId = ref(null)

function fmt(dt) {
  return new Date(dt).toLocaleString('ru-RU', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' })
}

async function load() {
  loading.value = true
  try {
    const { data } = await warehouseApi.moves({ limit: limit.value })
    moves.value = data
  } finally {
    loading.value = false
  }
}

async function deleteMoveRow(move) {
  const ok = confirm(`Удалить запись перемещения #${move.id} из истории?`)
  if (!ok) return

  deletingId.value = move.id
  try {
    await warehouseApi.deleteMove(move.id)
    await load()
  } catch (e) {
    alert(e.response?.data?.detail || 'Ошибка удаления записи перемещения')
  } finally {
    deletingId.value = null
  }
}

onMounted(load)
</script>

