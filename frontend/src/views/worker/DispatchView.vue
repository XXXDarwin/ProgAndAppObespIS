<template>
  <WorkerLayout>
    <div class="py-2">
      <div class="flex items-center gap-2 mb-5">
        <router-link to="/" class="text-gray-400 hover:text-gray-600">← Назад</router-link>
        <h2 class="text-xl font-bold text-gray-800">Расход товара</h2>
      </div>

      <div v-if="step === 'list'">
        <p class="text-sm text-gray-500 mb-4">
          Выберите заказ на расход и выполните его по маршрутному листу.
        </p>
        <WorkerFeedback v-if="feedback.message" class="mb-4" :type="feedback.type" :title="feedback.title" :message="feedback.message" />

        <div v-if="loadingOrders" class="space-y-2">
          <div v-for="i in 4" :key="i" class="skeleton h-16 w-full"></div>
        </div>
        <div v-else-if="!activeOrders.length" class="card text-center py-10 text-gray-400 text-sm">
          Нет заказов к выполнению
        </div>
        <div v-else class="space-y-3">
          <button
            v-for="o in activeOrders"
            :key="o.id"
            type="button"
            class="card w-full text-left hover:border-green-300 hover:shadow-md transition-all"
            :disabled="openingId === o.id"
            @click="openOrder(o)"
          >
            <div class="flex justify-between gap-3">
              <div>
                <div class="font-bold text-gray-800">Задание #{{ o.id }}</div>
                <div class="text-sm text-gray-500 mt-0.5">
                  {{ o.items?.length ?? 0 }} поз. · {{ statusLabel(o.status) }}
                </div>
                <p v-if="o.comment" class="text-xs text-gray-400 mt-1">{{ o.comment }}</p>
              </div>
              <span class="text-green-600 font-semibold text-sm shrink-0">
                {{ openingId === o.id ? 'Загрузка...' : 'Выполнить →' }}
              </span>
            </div>
          </button>
        </div>
      </div>

      <div v-if="step === 'route' && routeSheet">
        <button type="button" class="text-sm text-gray-400 hover:text-gray-600 mb-4" @click="backToList">
          ← К списку заказов
        </button>
        <div class="card mb-4 bg-green-50 border-green-200">
          <div class="font-semibold text-green-800">Маршрутный лист #{{ orderId }}</div>
          <div class="text-sm text-green-700 mt-0.5">
            {{ routeSheet.total_items }} позиций · пройдено {{ doneStep }}/{{ routeSheet.total_items }}
          </div>
        </div>

        <div class="space-y-3 mb-6">
          <div
            v-for="item in routeSheet.route"
            :key="item.step"
            class="card flex items-center gap-4 transition-opacity"
            :class="item.step <= doneStep ? 'opacity-50 border-green-200' : ''"
          >
            <div
              class="w-9 h-9 rounded-full flex items-center justify-center font-bold text-sm shrink-0"
              :class="item.step <= doneStep ? 'bg-green-100 text-green-700' : 'bg-blue-100 text-blue-700'"
            >
              {{ item.step <= doneStep ? '✓' : item.step }}
            </div>
            <div class="flex-1 min-w-0">
              <div class="font-bold text-gray-800">{{ item.cell_address }}</div>
              <div class="text-sm text-gray-600 truncate">{{ item.product_name }}</div>
              <div class="text-xs text-gray-400 font-mono">{{ item.product_sku }}</div>
            </div>
            <div class="text-right shrink-0">
              <div class="text-xl font-bold text-gray-800">{{ item.quantity }}</div>
              <div class="text-xs text-gray-400">ед.</div>
            </div>
          </div>
        </div>

        <div class="flex gap-3">
          <button
            type="button"
            class="btn-success flex-1 btn-lg"
            :disabled="doneStep >= routeSheet.total_items"
            @click="doneStep = Math.min(routeSheet.total_items, doneStep + 1)"
          >
            {{ doneStep >= routeSheet.total_items ? 'Маршрут пройден' : 'Следующая позиция' }}
          </button>
          <button
            v-if="doneStep >= routeSheet.total_items"
            type="button"
            class="btn-primary flex-1 btn-lg"
            :disabled="completing"
            @click="completeOrder"
          >
            {{ completing ? 'Завершение...' : 'Завершить расход' }}
          </button>
        </div>
        <WorkerFeedback v-if="feedback.message" class="mt-4" :type="feedback.type" :title="feedback.title" :message="feedback.message" />
      </div>

      <div v-if="step === 'done'">
        <WorkerFeedback
          type="success"
          title="Расход выполнен"
          :message="`Заказ #${orderId} завершён. Товар списан со склада.`"
          class="mb-4"
        />
        <div class="flex flex-col gap-2">
          <button type="button" class="btn-primary w-full btn-lg" @click="goHome">На главную</button>
          <button type="button" class="btn-secondary w-full" @click="backToList">Ещё заказы на расход</button>
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
import { warehouseApi } from '@/api'
import { parseApiDetail } from '@/utils/apiError'

const router = useRouter()
const step = ref('list')
const feedback = ref({ type: 'info', title: '', message: '' })
const loadingOrders = ref(true)
const openingId = ref(null)
const completing = ref(false)
const activeOrders = ref([])
const orderId = ref(null)
const routeSheet = ref(null)
const doneStep = ref(0)

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
      warehouseApi.orders({ type: 'CONSUMPTION', status: 'PENDING', limit: 50 }),
      warehouseApi.orders({ type: 'CONSUMPTION', status: 'IN_PROGRESS', limit: 50 }),
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
      await warehouseApi.startConsumption(order.id)
    }
    orderId.value = order.id
    const { data: rs } = await warehouseApi.routeSheet(order.id)
    routeSheet.value = rs
    doneStep.value = 0
    step.value = 'route'
  } catch (e) {
    showError(parseApiDetail(e, 'Не удалось открыть заказ'))
  } finally {
    openingId.value = null
  }
}

function backToList() {
  step.value = 'list'
  orderId.value = null
  routeSheet.value = null
  doneStep.value = 0
  clearFeedback()
  loadOrders()
}

async function completeOrder() {
  if (!confirm(`Завершить расход по заказу #${orderId.value}? Товар будет списан.`)) return
  completing.value = true
  clearFeedback()
  try {
    await warehouseApi.completeConsumption(orderId.value)
    step.value = 'done'
  } catch (e) {
    showError(parseApiDetail(e, 'Не удалось завершить расход'))
  } finally {
    completing.value = false
  }
}

function goHome() {
  router.push({ name: 'Home' })
}

onMounted(loadOrders)
onActivated(() => {
  if (step.value === 'list') loadOrders()
})
</script>
