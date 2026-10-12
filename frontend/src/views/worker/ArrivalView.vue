<template>
  <WorkerLayout>
    <div class="py-2">
      <div class="flex items-center gap-2 mb-5">
        <router-link to="/" class="text-gray-400 hover:text-gray-600">← Назад</router-link>
        <h2 class="text-xl font-bold text-gray-800">Приёмка товара</h2>
      </div>

      <div v-if="step === 'list'">
        <p class="text-sm text-gray-500 mb-4">Выполните заказ на приёмку, сформированный администратором.</p>
        <WorkerFeedback v-if="feedback.message" class="mb-4" :type="feedback.type" :title="feedback.title" :message="feedback.message" />

        <div v-if="loadingOrders" class="space-y-2">
          <div v-for="i in 4" :key="i" class="skeleton h-16 w-full"></div>
        </div>
        <div v-else-if="!activeOrders.length" class="card text-center py-10 text-gray-400 text-sm">
          Нет заказов к приёмке
        </div>
        <div v-else class="space-y-3">
          <button
            v-for="o in activeOrders"
            :key="o.id"
            type="button"
            class="card w-full text-left hover:border-blue-300 hover:shadow-md transition-all"
            :disabled="openingId === o.id"
            @click="openOrder(o)"
          >
            <div class="flex justify-between gap-3">
              <div>
                <div class="font-bold text-gray-800">Заказ #{{ o.id }}</div>
                <div class="text-sm text-gray-500">{{ o.items?.length ?? 0 }} поз. · {{ statusLabel(o.status) }}</div>
                <p v-if="o.comment" class="text-xs text-gray-400 mt-1">{{ o.comment }}</p>
              </div>
              <span class="text-blue-600 font-semibold text-sm shrink-0">
                {{ openingId === o.id ? 'Загрузка...' : 'Принять →' }}
              </span>
            </div>
          </button>
        </div>
      </div>

      <div v-if="step === 'execute' && currentOrder">
        <button type="button" class="text-sm text-gray-400 hover:text-gray-600 mb-4" @click="backToList">
          ← К списку заказов
        </button>
        <div class="card mb-4 bg-blue-50 border-blue-200">
          <div class="font-semibold text-blue-800">Приёмка #{{ currentOrder.id }}</div>
          <div class="text-sm text-blue-700 mt-0.5">{{ executeItems.length }} позиций · укажите ячейки</div>
        </div>

        <div class="space-y-3 mb-4 max-h-[55vh] overflow-y-auto">
          <div v-for="item in executeItems" :key="item.order_item_id" class="card">
            <div class="font-semibold text-gray-800">{{ item.product_name }}</div>
            <div class="text-xs text-gray-400 font-mono mb-2">{{ item.product_sku }}</div>
            <div class="flex gap-2 items-center mb-2">
              <label class="text-xs text-gray-500 shrink-0">Кол-во</label>
              <input v-model.number="item.quantity" type="number" min="1" class="input w-24 text-center font-bold" />
            </div>
            <div>
              <label class="text-xs text-gray-500">Ячейка</label>
              <select v-model="item.cell_id" class="input mt-1 text-sm">
                <option value="">Автоподбор</option>
                <option v-for="cell in cells" :key="cell.id" :value="String(cell.id)">
                  {{ cell.address }}{{ item.suggested_cell_id === cell.id ? ' (рекомендуется)' : '' }}
                </option>
              </select>
            </div>
          </div>
        </div>

        <button type="button" class="btn-success w-full btn-lg" :disabled="submitting" @click="submitComplete">
          {{ submitting ? 'Сохранение...' : 'Завершить приёмку' }}
        </button>
        <WorkerFeedback v-if="feedback.message && step === 'execute'" class="mt-4" :type="feedback.type" :title="feedback.title" :message="feedback.message" />
      </div>

      <div v-if="step === 'done'">
        <WorkerFeedback
          type="success"
          title="Приёмка завершена"
          :message="`Заказ #${doneOrderId} выполнен. Товар размещён на складе (${doneItemsCount} поз.).`"
          class="mb-4"
        />
        <div class="flex flex-col gap-2">
          <button type="button" class="btn-primary w-full btn-lg" @click="goHome">На главную</button>
          <button type="button" class="btn-secondary w-full" @click="backToList">Ещё заказы на приёмку</button>
        </div>
      </div>
    </div>
  </WorkerLayout>
</template>

<script setup>
import { ref, onMounted, onActivated } from 'vue'
import { useRouter } from 'vue-router'
import WorkerLayout from '@/layouts/WorkerLayout.vue'
import WorkerFeedback from '@/components/WorkerFeedback.vue'
import { cellsApi, warehouseApi } from '@/api'
import { parseApiDetail } from '@/utils/apiError'

const router = useRouter()
const step = ref('list')
const feedback = ref({ type: 'info', title: '', message: '' })
const loadingOrders = ref(true)
const openingId = ref(null)
const submitting = ref(false)
const activeOrders = ref([])
const currentOrder = ref(null)
const executeItems = ref([])
const cells = ref([])
const doneOrderId = ref(null)
const doneItemsCount = ref(0)

function clearFeedback() {
  feedback.value = { type: 'info', title: '', message: '' }
}

function showError(msg) {
  feedback.value = { type: 'error', title: 'Ошибка', message: msg }
}

function statusLabel(status) {
  return { PENDING: 'Ожидает', IN_PROGRESS: 'В работе' }[status] ?? status
}

async function loadOrders() {
  loadingOrders.value = true
  clearFeedback()
  try {
    const [pending, inProgress] = await Promise.all([
      warehouseApi.orders({ type: 'ARRIVAL', status: 'PENDING', limit: 50 }),
      warehouseApi.orders({ type: 'ARRIVAL', status: 'IN_PROGRESS', limit: 50 }),
    ])
    activeOrders.value = [...pending.data, ...inProgress.data].sort(
      (a, b) => new Date(a.created_at) - new Date(b.created_at),
    )
  } catch (e) {
    showError(parseApiDetail(e, 'Не удалось загрузить заказы'))
  } finally {
    loadingOrders.value = false
  }
}

async function openOrder(order) {
  openingId.value = order.id
  clearFeedback()
  try {
    if (order.status === 'PENDING') {
      await warehouseApi.startArrival(order.id)
    }
    const { data } = await warehouseApi.getOrder(order.id)
    currentOrder.value = data
    executeItems.value = (data.items || []).map(it => ({
      order_item_id: it.id,
      product_name: it.product_name,
      product_sku: it.product_sku,
      quantity: it.quantity,
      suggested_cell_id: it.cell_id,
      cell_id: it.cell_id ? String(it.cell_id) : '',
    }))
    step.value = 'execute'
  } catch (e) {
    showError(parseApiDetail(e, 'Не удалось открыть заказ'))
  } finally {
    openingId.value = null
  }
}

function backToList() {
  step.value = 'list'
  currentOrder.value = null
  executeItems.value = []
  clearFeedback()
  loadOrders()
}

async function submitComplete() {
  if (!currentOrder.value) return
  if (!confirm(`Завершить приёмку заказа #${currentOrder.value.id}?`)) return
  submitting.value = true
  clearFeedback()
  try {
    await warehouseApi.completeArrival(currentOrder.value.id, {
      items: executeItems.value.map(it => ({
        order_item_id: it.order_item_id,
        quantity: Math.max(1, Number(it.quantity || 1)),
        cell_id: it.cell_id ? Number(it.cell_id) : undefined,
      })),
    })
    doneOrderId.value = currentOrder.value.id
    doneItemsCount.value = executeItems.value.length
    step.value = 'done'
  } catch (e) {
    showError(parseApiDetail(e, 'Не удалось сохранить приёмку'))
  } finally {
    submitting.value = false
  }
}

function goHome() {
  router.push({ name: 'Home' })
}

onMounted(async () => {
  try {
    const { data } = await cellsApi.list()
    cells.value = (data || []).filter(c => c.is_active)
  } catch {
    cells.value = []
  }
  loadOrders()
})

onActivated(() => {
  if (step.value === 'list') loadOrders()
})
</script>
