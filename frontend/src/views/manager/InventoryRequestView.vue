<template>
  <ManagerLayout>
    <div class="space-y-6 max-w-3xl">
      <p class="text-sm text-gray-500">
        Сформируйте задание на пересчёт. Кладовщик введёт фактические количества по ячейкам;
        система скорректирует остатки после завершения.
      </p>

      <div class="card space-y-4">
        <div>
          <label class="label">Комментарий (необязательно)</label>
          <input v-model="comment" type="text" class="input mt-1" placeholder="Например: плановая инвентаризация Q2" />
        </div>

        <div>
          <label class="label">Область пересчёта</label>
          <div class="flex flex-wrap gap-4 mt-2">
            <label class="flex items-center gap-2 text-sm cursor-pointer">
              <input v-model="scope" type="radio" value="all" class="rounded-full" />
              Весь склад (все позиции с остатком)
            </label>
            <label class="flex items-center gap-2 text-sm cursor-pointer">
              <input v-model="scope" type="radio" value="products" class="rounded-full" />
              Выбранные товары
            </label>
          </div>
        </div>

        <div v-if="scope === 'products'" class="space-y-2">
          <label class="label">Добавить товар</label>
          <div class="relative">
            <div class="flex gap-2">
              <input
                v-model="query"
                type="text"
                class="input"
                placeholder="SKU или название..."
                @input="onQueryInput"
                @keydown.enter.prevent="addFirst"
              />
              <button class="btn-secondary" :disabled="!query" @click="addFirst">Добавить</button>
            </div>
            <div
              v-if="showSuggest && suggestions.length"
              class="absolute left-0 right-0 mt-1 bg-white border rounded-lg shadow-lg z-20 max-h-48 overflow-y-auto"
            >
              <button
                v-for="p in suggestions"
                :key="p.id"
                type="button"
                class="w-full text-left px-3 py-2 hover:bg-gray-50"
                @click="addProduct(p)"
              >
                <span class="font-mono text-blue-700 text-sm">{{ p.sku }}</span>
                <span class="text-gray-600 text-sm ml-2">{{ p.name }}</span>
              </button>
            </div>
          </div>
          <div v-if="selectedProducts.length" class="flex flex-wrap gap-2">
            <span
              v-for="p in selectedProducts"
              :key="p.id"
              class="badge badge-yellow inline-flex items-center gap-1"
            >
              {{ p.sku }}
              <button type="button" class="hover:text-red-600" @click="removeProduct(p.id)">×</button>
            </span>
          </div>
        </div>

        <p v-if="previewCount != null" class="text-sm text-gray-600">
          Будет создано позиций для пересчёта: <strong>{{ previewCount }}</strong>
        </p>

        <button class="btn-primary w-full" :disabled="submitting || !canSubmit" @click="submit">
          {{ submitting ? 'Создание...' : 'Сформировать задание' }}
        </button>
        <p v-if="formError" class="text-red-500 text-sm">{{ formError }}</p>
      </div>

      <div v-if="successMsg" class="bg-green-50 border border-green-200 rounded-xl p-4 text-green-700 text-sm">
        {{ successMsg }}
      </div>

      <div class="card p-0 overflow-hidden">
        <div class="px-4 py-3 border-b flex items-center justify-between">
          <h3 class="font-semibold text-gray-700">Активные задания</h3>
          <button class="btn-secondary text-sm" @click="loadActive">Обновить</button>
        </div>
        <div v-if="loadingActive" class="p-4 space-y-2">
          <div v-for="i in 3" :key="i" class="skeleton h-10 w-full"></div>
        </div>
        <div v-else-if="!activeOrders.length" class="p-6 text-center text-gray-400 text-sm">
          Нет активных заданий
        </div>
        <ul v-else class="divide-y divide-gray-50">
          <li v-for="o in activeOrders" :key="o.id" class="px-4 py-3 hover:bg-gray-50">
            <div class="flex items-start justify-between gap-3">
              <div class="min-w-0 flex-1">
                <div class="font-semibold text-gray-800">#{{ o.id }} · {{ statusLabel(o.status) }}</div>
                <div class="text-xs text-gray-500">
                  {{ o.tasksLabel }} · {{ o.items?.length ?? 0 }} поз. · {{ o.created_by ?? '—' }}
                </div>
                <p v-if="o.comment" class="text-xs text-gray-400 truncate">{{ o.comment }}</p>
                <div v-if="o._tasks?.length" class="flex flex-wrap gap-1 mt-2">
                  <span
                    v-for="t in o._tasks"
                    :key="t.id"
                    class="text-xs px-2 py-0.5 rounded-full"
                    :class="t.status === 'COMPLETED' ? 'bg-green-100 text-green-800' : t.status === 'IN_PROGRESS' ? 'bg-yellow-100 text-yellow-800' : 'bg-gray-100 text-gray-600'"
                  >
                    {{ t.zone }}-{{ t.rack }}
                  </span>
                </div>
              </div>
              <div class="flex flex-col gap-1 shrink-0">
                <router-link to="/inventory" class="btn-primary text-sm">Пересчёт</router-link>
                <button
                  v-if="o.status === 'PENDING'"
                  class="btn-secondary text-sm"
                  :disabled="cancellingId === o.id"
                  @click="cancelOrder(o.id)"
                >
                  {{ cancellingId === o.id ? '...' : 'Отменить' }}
                </button>
              </div>
            </div>
          </li>
        </ul>
      </div>

      <div class="card p-0 overflow-hidden">
        <div class="px-4 py-3 border-b flex items-center justify-between">
          <h3 class="font-semibold text-gray-700">Завершённые — потери и излишки</h3>
          <button class="btn-secondary text-sm" @click="loadCompleted">Обновить</button>
        </div>
        <div v-if="loadingCompleted" class="p-4"><div class="skeleton h-20 w-full"></div></div>
        <div v-else-if="!completedOrders.length" class="p-6 text-center text-gray-400 text-sm">
          Нет завершённых инвентаризаций
        </div>
        <div v-else class="divide-y divide-gray-50">
          <div v-for="o in completedOrders" :key="o.id" class="px-4 py-3">
            <button
              type="button"
              class="w-full text-left flex justify-between items-center gap-2"
              @click="toggleLosses(o.id)"
            >
              <div>
                <span class="font-semibold text-gray-800">#{{ o.id }}</span>
                <span v-if="o._lossPreview" class="text-sm text-red-600 ml-2">
                  потери: {{ o._lossPreview.total_loss_units }} ед.
                </span>
              </div>
              <span class="text-gray-400 text-sm">{{ expandedLossId === o.id ? '▲' : '▼' }}</span>
            </button>
            <div v-if="expandedLossId === o.id" class="mt-3">
              <InventoryLossesTable :summary="lossesByOrder[o.id]" :loading="loadingLossId === o.id" />
            </div>
          </div>
        </div>
      </div>
    </div>
  </ManagerLayout>
</template>

<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import ManagerLayout from '@/layouts/ManagerLayout.vue'
import InventoryLossesTable from '@/components/InventoryLossesTable.vue'
import { warehouseApi, productsApi } from '@/api'

const comment = ref('')
const scope = ref('all')
const query = ref('')
const suggestions = ref([])
const showSuggest = ref(false)
const selectedProducts = ref([])
let suggestTimer = null

const submitting = ref(false)
const formError = ref('')
const successMsg = ref('')

const activeOrders = ref([])
const loadingActive = ref(false)
const cancellingId = ref(null)
const completedOrders = ref([])
const loadingCompleted = ref(false)
const expandedLossId = ref(null)
const lossesByOrder = ref({})
const loadingLossId = ref(null)

const previewCount = ref(null)

const canSubmit = computed(() => scope.value === 'all' || selectedProducts.value.length > 0)

function statusLabel(s) {
  return { PENDING: 'Ожидает', IN_PROGRESS: 'В работе' }[s] ?? s
}

function onQueryInput() {
  showSuggest.value = true
  if (suggestTimer) clearTimeout(suggestTimer)
  suggestTimer = setTimeout(loadSuggestions, 250)
}

async function loadSuggestions() {
  const q = query.value.trim()
  if (!q) {
    suggestions.value = []
    return
  }
  try {
    const { data } = await productsApi.list({ search: q, active_only: true })
    suggestions.value = (data || []).slice(0, 10)
  } catch {
    suggestions.value = []
  }
}

function addFirst() {
  if (suggestions.value.length) addProduct(suggestions.value[0])
}

function addProduct(p) {
  if (!selectedProducts.value.find(x => x.id === p.id)) {
    selectedProducts.value.push({ id: p.id, sku: p.sku, name: p.name })
  }
  query.value = ''
  suggestions.value = []
  showSuggest.value = false
  updatePreview()
}

function removeProduct(id) {
  selectedProducts.value = selectedProducts.value.filter(p => p.id !== id)
  updatePreview()
}

async function updatePreview() {
  if (scope.value === 'all') {
    try {
      const { data } = await warehouseApi.stocks()
      previewCount.value = data.length
    } catch {
      previewCount.value = null
    }
    return
  }
  if (!selectedProducts.value.length) {
    previewCount.value = 0
    return
  }
  try {
    const ids = new Set(selectedProducts.value.map(p => p.id))
    const { data } = await warehouseApi.stocks()
    previewCount.value = data.filter(s => ids.has(s.product_id)).length
  } catch {
    previewCount.value = null
  }
}

async function submit() {
  formError.value = ''
  successMsg.value = ''
  if (scope.value === 'products' && !selectedProducts.value.length) {
    formError.value = 'Выберите хотя бы один товар'
    return
  }
  submitting.value = true
  try {
    const payload = {
      comment: comment.value.trim() || undefined,
      product_ids: scope.value === 'products'
        ? selectedProducts.value.map(p => p.id)
        : null,
    }
    const { data } = await warehouseApi.createInventoryRequest(payload)
    let tasksHint = ''
    try {
      const { data: taskList } = await warehouseApi.inventoryTasks(data.id)
      tasksHint = `, ${taskList.length} стеллажей (подзаданий)`
    } catch { /* ignore */ }
    successMsg.value = `Задание #${data.id} создано: ${data.items?.length ?? 0} позиций${tasksHint}.`
    comment.value = ''
    selectedProducts.value = []
    scope.value = 'all'
    await loadActive()
    await updatePreview()
  } catch (e) {
    formError.value = e.response?.data?.detail || 'Ошибка создания задания'
  } finally {
    submitting.value = false
  }
}

async function enrichOrder(o) {
  try {
    const { data: taskList } = await warehouseApi.inventoryTasks(o.id)
    const done = taskList.filter(t => t.status === 'COMPLETED').length
    const loss = taskList.reduce((s, t) => s + (t.loss_units || 0), 0)
    return {
      ...o,
      _tasks: taskList,
      tasksLabel: `${done}/${taskList.length} стеллажей`,
      _lossSoFar: loss,
    }
  } catch {
    return { ...o, _tasks: [], tasksLabel: '—', _lossSoFar: 0 }
  }
}

async function loadActive() {
  loadingActive.value = true
  try {
    const [pending, progress] = await Promise.all([
      warehouseApi.orders({ type: 'INVENTORY', status: 'PENDING', limit: 50 }),
      warehouseApi.orders({ type: 'INVENTORY', status: 'IN_PROGRESS', limit: 50 }),
    ])
    const raw = [...pending.data, ...progress.data].sort((a, b) => b.id - a.id)
    activeOrders.value = await Promise.all(raw.map(enrichOrder))
  } finally {
    loadingActive.value = false
  }
}

async function loadCompleted() {
  loadingCompleted.value = true
  try {
    const { data } = await warehouseApi.orders({ type: 'INVENTORY', status: 'COMPLETED', limit: 30 })
    completedOrders.value = await Promise.all(
      data.map(async o => {
        try {
          const { data: loss } = await warehouseApi.inventoryLosses(o.id)
          return { ...o, _lossPreview: loss }
        } catch {
          return { ...o, _lossPreview: null }
        }
      })
    )
  } finally {
    loadingCompleted.value = false
  }
}

async function toggleLosses(id) {
  if (expandedLossId.value === id) {
    expandedLossId.value = null
    return
  }
  expandedLossId.value = id
  if (lossesByOrder.value[id]) return
  loadingLossId.value = id
  try {
    const { data } = await warehouseApi.inventoryLosses(id)
    lossesByOrder.value = { ...lossesByOrder.value, [id]: data }
  } finally {
    loadingLossId.value = null
  }
}

async function cancelOrder(id) {
  if (!confirm(`Отменить задание на инвентаризацию #${id}?`)) return
  cancellingId.value = id
  try {
    await warehouseApi.deleteOrder(id)
    await loadActive()
  } catch (e) {
    formError.value = e.response?.data?.detail || 'Ошибка отмены'
  } finally {
    cancellingId.value = null
  }
}

watch(scope, () => updatePreview())

onMounted(async () => {
  await loadActive()
  await loadCompleted()
  await updatePreview()
})
</script>
