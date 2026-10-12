<template>
  <WorkerLayout>
    <div class="py-2">
      <div class="flex items-center gap-2 mb-5">
        <router-link to="/" class="text-gray-400 hover:text-gray-600">← Назад</router-link>
        <h2 class="text-xl font-bold text-gray-800">Инвентаризация</h2>
      </div>

      <WorkerFeedback
        v-if="feedback.message && step !== 'count'"
        class="mb-4"
        :type="feedback.type"
        :title="feedback.title"
        :message="feedback.message"
      />

      <!-- Список заданий -->
      <div v-if="step === 'list'">
        <p class="text-sm text-gray-500 mb-4">Выберите задание и пересчитайте стеллажи по одному.</p>
        <div v-if="loadingOrders" class="space-y-2">
          <div v-for="i in 4" :key="i" class="skeleton h-16 w-full"></div>
        </div>
        <div v-else-if="!activeOrders.length" class="card text-center py-10 text-gray-400 text-sm">
          Нет заданий к выполнению
        </div>
        <div v-else class="space-y-3">
          <button
            v-for="o in activeOrders"
            :key="o.id"
            type="button"
            class="card w-full text-left hover:border-yellow-300 hover:shadow-md transition-all"
            :disabled="openingOrderId === o.id"
            @click="openOrder(o)"
          >
            <div class="flex justify-between gap-3">
              <div>
                <div class="font-bold text-gray-800">Задание #{{ o.id }}</div>
                <div class="text-sm text-gray-500 mt-0.5">{{ o.progressLabel }}</div>
                <p v-if="o.comment" class="text-xs text-gray-400 mt-1">{{ o.comment }}</p>
              </div>
              <span class="text-yellow-700 font-semibold text-sm shrink-0">
                {{ openingOrderId === o.id ? 'Загрузка...' : 'Открыть →' }}
              </span>
            </div>
          </button>
        </div>
      </div>

      <!-- Стеллажи -->
      <div v-if="step === 'tasks'">
        <button type="button" class="text-sm text-gray-400 hover:text-gray-600 mb-4" @click="backToList">
          ← К списку заданий
        </button>
        <div class="card mb-4 bg-yellow-50 border-yellow-200">
          <div class="font-semibold text-yellow-900">Задание #{{ orderId }}</div>
          <div class="text-sm text-yellow-800 mt-0.5">
            {{ tasksDone }}/{{ tasks.length }} стеллажей готово
            <span v-if="totalLossSoFar"> · потери: {{ totalLossSoFar }} ед.</span>
          </div>
        </div>

        <div v-if="loadingTasks" class="space-y-2">
          <div v-for="i in 4" :key="i" class="skeleton h-14 w-full"></div>
        </div>
        <div v-else class="space-y-2 mb-4">
          <button
            v-for="t in tasks"
            :key="t.id"
            type="button"
            class="card w-full text-left py-3"
            :class="taskCardClass(t)"
            :disabled="openingTaskId === t.id"
            @click="openTask(t)"
          >
            <div class="flex justify-between items-center gap-2">
              <div>
                <div class="font-bold text-gray-800">{{ t.label }}</div>
                <div class="text-xs text-gray-500 mt-0.5">
                  {{ t.items_total }} поз. · {{ statusLabel(t.status) }}
                  <span v-if="t.loss_units" class="text-red-600 ml-1">потери: {{ t.loss_units }}</span>
                  <span v-if="t.surplus_units" class="text-green-600 ml-1">излишки: {{ t.surplus_units }}</span>
                </div>
              </div>
              <span
                class="text-sm font-semibold shrink-0"
                :class="t.status === 'COMPLETED' ? 'text-green-600' : 'text-yellow-700'"
              >
                {{ t.status === 'COMPLETED' ? 'Готово' : openingTaskId === t.id ? '...' : 'Пересчитать' }}
              </span>
            </div>
          </button>
        </div>

        <p v-if="tasksLeft > 0" class="text-xs text-gray-500 text-center">
          Осталось стеллажей: {{ tasksLeft }}
        </p>
      </div>

      <!-- Пересчёт стеллажа -->
      <div v-if="step === 'count' && currentTask">
        <button type="button" class="text-sm text-gray-400 hover:text-gray-600 mb-4" @click="backToTasks">
          ← К стеллажам
        </button>
        <div class="card mb-4 bg-yellow-50 border-yellow-200">
          <div class="font-semibold text-yellow-900">{{ currentTask.label }}</div>
          <div class="text-sm text-yellow-800 mt-0.5">{{ routeItems.length }} позиций для пересчёта</div>
        </div>
        <div class="flex gap-2 mb-3">
          <button type="button" class="btn-secondary text-sm flex-1" @click="fillAllExpected">
            Заполнить «как в учёте»
          </button>
        </div>
        <div class="space-y-2 mb-4 max-h-[50vh] overflow-y-auto">
          <div
            v-for="row in routeItems"
            :key="row.order_item_id"
            class="card py-3 px-4"
            :class="rowDelta(row) < 0 ? 'border-red-200 bg-red-50/30' : rowDelta(row) > 0 ? 'border-green-200 bg-green-50/30' : ''"
          >
            <div class="flex items-start gap-3">
              <div class="w-8 h-8 rounded-full bg-yellow-100 text-yellow-800 flex items-center justify-center text-sm font-bold shrink-0">
                {{ row.step }}
              </div>
              <div class="flex-1 min-w-0">
                <div class="font-mono font-bold text-gray-800">{{ row.cell_address }}</div>
                <div class="text-sm text-gray-600 truncate">{{ row.product_name }}</div>
                <div class="text-xs text-gray-400 font-mono">{{ row.product_sku }}</div>
                <div class="text-xs text-gray-500 mt-1">Учёт: <strong>{{ row.quantity }}</strong></div>
              </div>
              <div class="shrink-0 w-24">
                <label class="text-xs text-gray-500 block mb-0.5">Факт</label>
                <input v-model.number="facts[row.order_item_id]" type="number" min="0" class="input text-center font-bold py-1.5" />
              </div>
            </div>
          </div>
        </div>
        <button class="btn-primary w-full btn-lg" :disabled="completing" @click="completeTask">
          {{ completing ? 'Сохранение...' : 'Завершить стеллаж' }}
        </button>
      </div>

      <!-- Стеллаж завершён -->
      <div v-if="step === 'task-done' && lastTaskResult">
        <WorkerFeedback
          type="success"
          title="Стеллаж пересчитан"
          :message="taskDoneMessage"
          class="mb-4"
        />
        <div class="flex flex-col gap-2">
          <button class="btn-primary w-full btn-lg" @click="backToTasks">К списку стеллажей</button>
          <button v-if="tasksLeft > 0" class="btn-secondary w-full" @click="openNextPendingTask">
            Следующий стеллаж
          </button>
        </div>
      </div>

      <!-- Всё задание завершено -->
      <div v-if="step === 'order-done'">
        <WorkerFeedback
          type="success"
          title="Инвентаризация завершена"
          :message="`Задание #${orderId} полностью пересчитано. Остатки на складе обновлены.`"
          class="mb-4"
        />
        <div v-if="lossesSummary" class="card mb-4">
          <h3 class="font-semibold text-gray-700 mb-3">Итоги</h3>
          <InventoryLossesTable :summary="lossesSummary" />
        </div>
        <div v-else-if="loadingLosses" class="text-sm text-gray-500 py-4 text-center">Загрузка итогов...</div>
        <div class="flex flex-col gap-2">
          <button class="btn-primary w-full btn-lg" @click="goHome">На главную</button>
          <button class="btn-secondary w-full" @click="backToList">К другим заданиям</button>
        </div>
      </div>
    </div>
  </WorkerLayout>
</template>

<script setup>
import { ref, reactive, computed, onMounted, onActivated } from 'vue'
import { useRouter } from 'vue-router'
import WorkerLayout from '@/layouts/WorkerLayout.vue'
import WorkerFeedback from '@/components/WorkerFeedback.vue'
import InventoryLossesTable from '@/components/InventoryLossesTable.vue'
import { warehouseApi } from '@/api'
import { parseApiDetail } from '@/utils/apiError'

const router = useRouter()
const step = ref('list')
const feedback = ref({ type: 'info', title: '', message: '' })
const loadingOrders = ref(true)
const loadingTasks = ref(false)
const loadingLosses = ref(false)
const openingOrderId = ref(null)
const openingTaskId = ref(null)
const completing = ref(false)

const activeOrders = ref([])
const orderId = ref(null)
const tasks = ref([])
const currentTask = ref(null)
const routeItems = ref([])
const facts = reactive({})
const lastTaskResult = ref(null)
const lossesSummary = ref(null)

const tasksDone = computed(() => tasks.value.filter(t => t.status === 'COMPLETED').length)
const tasksLeft = computed(() => tasks.value.filter(t => t.status !== 'COMPLETED').length)
const totalLossSoFar = computed(() => tasks.value.reduce((s, t) => s + (t.loss_units || 0), 0))

const taskDoneMessage = computed(() => {
  const t = lastTaskResult.value
  if (!t) return ''
  const parts = [`Стеллаж «${t.label}» сохранён.`]
  if (t.loss_units) parts.push(`Потери: ${t.loss_units} ед.`)
  if (t.surplus_units) parts.push(`Излишки: ${t.surplus_units} ед.`)
  if (!t.loss_units && !t.surplus_units) parts.push('Расхождений нет.')
  return parts.join(' ')
})

function clearFeedback() {
  feedback.value = { type: 'info', title: '', message: '' }
}

function showError(msg) {
  feedback.value = { type: 'error', title: 'Ошибка', message: msg }
}

function statusLabel(s) {
  return { PENDING: 'Ожидает', IN_PROGRESS: 'В работе', COMPLETED: 'Готово' }[s] ?? s
}

function taskCardClass(t) {
  if (t.status === 'COMPLETED') return 'opacity-80 border-green-200 bg-green-50/30'
  if (t.status === 'IN_PROGRESS') return 'border-yellow-300'
  return 'hover:border-yellow-300 hover:shadow-md'
}

function rowDelta(row) {
  const fact = Number(facts[row.order_item_id])
  if (Number.isNaN(fact)) return 0
  return fact - row.quantity
}

async function loadOrders() {
  loadingOrders.value = true
  clearFeedback()
  try {
    const [pending, progress] = await Promise.all([
      warehouseApi.orders({ type: 'INVENTORY', status: 'PENDING', limit: 100 }),
      warehouseApi.orders({ type: 'INVENTORY', status: 'IN_PROGRESS', limit: 100 }),
    ])
    const orders = [...pending.data, ...progress.data]
    const enriched = await Promise.all(
      orders.map(async o => {
        try {
          const { data: taskList } = await warehouseApi.inventoryTasks(o.id)
          const left = taskList.filter(t => t.status !== 'COMPLETED').length
          const done = taskList.length - left
          if (left === 0 && taskList.length > 0) return null
          return {
            ...o,
            progressLabel: `${done}/${taskList.length} стеллажей`,
            _tasks: taskList,
          }
        } catch {
          return { ...o, progressLabel: '—', _tasks: [] }
        }
      }),
    )
    activeOrders.value = enriched.filter(Boolean).sort((a, b) => b.id - a.id)
  } catch (e) {
    showError(parseApiDetail(e, 'Не удалось загрузить задания'))
  } finally {
    loadingOrders.value = false
  }
}

async function openOrder(o) {
  openingOrderId.value = o.id
  clearFeedback()
  orderId.value = o.id
  try {
    await loadTasksForOrder()
    const allDone = tasks.value.length > 0 && tasks.value.every(t => t.status === 'COMPLETED')
    if (allDone) {
      step.value = 'order-done'
      await loadLosses()
    } else {
      step.value = 'tasks'
    }
  } catch (e) {
    showError(parseApiDetail(e, 'Не удалось открыть задание'))
  } finally {
    openingOrderId.value = null
  }
}

async function loadTasksForOrder() {
  loadingTasks.value = true
  const { data } = await warehouseApi.inventoryTasks(orderId.value)
  tasks.value = data
  loadingTasks.value = false
  return data
}

async function loadLosses() {
  loadingLosses.value = true
  try {
    const { data } = await warehouseApi.inventoryLosses(orderId.value)
    lossesSummary.value = data
  } catch (e) {
    lossesSummary.value = null
    showError(parseApiDetail(e, 'Не удалось загрузить итоги'))
  } finally {
    loadingLosses.value = false
  }
}

async function openTask(t) {
  clearFeedback()
  if (t.status === 'COMPLETED') {
    lastTaskResult.value = t
    step.value = 'task-done'
    return
  }
  openingTaskId.value = t.id
  try {
    if (t.status === 'PENDING') {
      const { data } = await warehouseApi.startInventoryTask(orderId.value, t.id)
      Object.assign(t, data)
      const idx = tasks.value.findIndex(x => x.id === t.id)
      if (idx >= 0) tasks.value[idx] = { ...tasks.value[idx], ...data }
    }
    const { data: route } = await warehouseApi.inventoryTaskRoute(orderId.value, t.id)
    currentTask.value = tasks.value.find(x => x.id === t.id) || t
    routeItems.value = route.route || []
    for (const row of routeItems.value) {
      facts[row.order_item_id] = row.quantity_fact ?? row.quantity
    }
    step.value = 'count'
  } catch (e) {
    showError(parseApiDetail(e, 'Не удалось открыть стеллаж'))
  } finally {
    openingTaskId.value = null
  }
}

function openNextPendingTask() {
  const next = tasks.value.find(t => t.status !== 'COMPLETED')
  if (next) openTask(next)
  else backToTasks()
}

function fillAllExpected() {
  for (const row of routeItems.value) {
    facts[row.order_item_id] = row.quantity
  }
}

async function completeTask() {
  clearFeedback()
  const fact_items = routeItems.value.map(row => ({
    order_item_id: row.order_item_id,
    quantity_fact: Number(facts[row.order_item_id]),
  }))
  if (fact_items.some(f => Number.isNaN(f.quantity_fact) || f.quantity_fact < 0)) {
    showError('Укажите факт для всех позиций (0 или больше)')
    return
  }
  const losses = routeItems.value.filter(row => rowDelta(row) < 0).reduce((s, row) => s - rowDelta(row), 0)
  const ok = confirm(
    losses
      ? `Завершить стеллаж? Потери: ${losses} ед. Остатки будут скорректированы.`
      : 'Завершить пересчёт стеллажа?',
  )
  if (!ok) return

  completing.value = true
  try {
    const { data } = await warehouseApi.completeInventoryTask(orderId.value, currentTask.value.id, { fact_items })
    lastTaskResult.value = data
    const idx = tasks.value.findIndex(x => x.id === data.id)
    if (idx >= 0) tasks.value[idx] = data

    await loadTasksForOrder()
    const allDone = tasks.value.every(t => t.status === 'COMPLETED')
    if (allDone) {
      step.value = 'order-done'
      await loadLosses()
    } else {
      step.value = 'task-done'
    }
  } catch (e) {
    showError(parseApiDetail(e, 'Не удалось завершить стеллаж'))
  } finally {
    completing.value = false
  }
}

function backToList() {
  step.value = 'list'
  orderId.value = null
  tasks.value = []
  lossesSummary.value = null
  lastTaskResult.value = null
  clearFeedback()
  loadOrders()
}

async function backToTasks() {
  clearFeedback()
  currentTask.value = null
  routeItems.value = []
  lastTaskResult.value = null
  try {
    await loadTasksForOrder()
    const allDone = tasks.value.length > 0 && tasks.value.every(t => t.status === 'COMPLETED')
    if (allDone) {
      step.value = 'order-done'
      await loadLosses()
    } else {
      step.value = 'tasks'
    }
  } catch (e) {
    showError(parseApiDetail(e, 'Ошибка обновления'))
    step.value = 'tasks'
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
