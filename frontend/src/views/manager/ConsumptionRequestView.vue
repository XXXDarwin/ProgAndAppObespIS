<template>
  <ManagerLayout>
    <div class="space-y-6 max-w-3xl">
      <p class="text-sm text-gray-500">
        Сформируйте заказ на расход вручную, загрузите Excel/CSV/JSON или вставьте JSON. Кладовщик выполнит его в разделе «Расход».
      </p>

      <div class="card">
        <label class="label">Комментарий к заказу (необязательно)</label>
        <input v-model="comment" type="text" class="input mt-1" placeholder="Например: отгрузка для цеха №2" />
      </div>

      <div class="card space-y-3">
        <h3 class="font-semibold text-gray-700">Загрузка из файла</h3>
        <p class="text-xs text-gray-500">
          Форматы: .xlsx, .xls, .csv, .json. Колонки: <span class="font-mono">sku</span>, <span class="font-mono">quantity</span>.
        </p>
        <input type="file" accept=".xlsx,.xls,.csv,.json" class="input" @change="onFileChange" />
        <button class="btn-primary" :disabled="!uploadFile || uploading" @click="submitUpload">
          {{ uploading ? 'Загрузка...' : 'Создать заказ из файла' }}
        </button>
      </div>

      <div class="card space-y-3">
        <h3 class="font-semibold text-gray-700">Импорт JSON</h3>
        <p class="text-xs text-gray-500 font-mono">
          { "comment": "...", "items": [{ "sku": "ABC-1", "quantity": 5 }] }
        </p>
        <textarea v-model="jsonText" class="input font-mono text-sm min-h-[120px]" placeholder='{"items":[{"sku":"...","quantity":1}]}' />
        <button class="btn-secondary" :disabled="!jsonText.trim() || importingJson" @click="submitJson">
          {{ importingJson ? 'Импорт...' : 'Создать заказ из JSON' }}
        </button>
      </div>

      <div class="card">
        <h3 class="font-semibold text-gray-700 mb-3">Добавить товар вручную</h3>
        <label class="label">Поиск товара</label>
        <div class="relative mt-1">
          <div class="flex gap-2">
            <input
              v-model="query"
              @input="onQueryInput"
              @keydown.enter.prevent="addFirstSuggestion"
              type="text"
              class="input"
              placeholder="SKU или название…"
              :disabled="adding"
            />
            <button @click="addFirstSuggestion" class="btn-primary px-5" :disabled="!query || adding">
              {{ adding ? '...' : 'Добавить' }}
            </button>
          </div>

          <div
            v-if="showSuggest"
            class="absolute left-0 right-0 mt-2 bg-white border border-gray-200 rounded-xl shadow-lg overflow-hidden z-20"
          >
            <button
              v-for="p in suggestions"
              :key="p.id"
              type="button"
              class="w-full text-left px-4 py-2.5 hover:bg-gray-50"
              @click="addProduct(p)"
            >
              <div class="flex justify-between gap-3">
                <div class="min-w-0">
                  <div class="font-semibold text-gray-800 truncate">{{ p.name }}</div>
                  <div class="text-xs text-gray-400 font-mono">{{ p.sku }}</div>
                </div>
                <div class="text-xs text-gray-500 shrink-0">
                  на складе: <span class="font-semibold">{{ p.total_stock ?? 0 }}</span>
                </div>
              </div>
            </button>
            <div v-if="!suggestions.length" class="px-4 py-3 text-sm text-gray-400">Ничего не найдено</div>
          </div>
        </div>
        <p v-if="formError" class="text-red-500 text-sm mt-2">{{ formError }}</p>
      </div>

      <div v-if="items.length" class="space-y-3">
        <div v-for="(item, idx) in items" :key="idx" class="card flex items-center gap-3">
          <div class="flex-1 min-w-0">
            <div class="font-semibold text-gray-800 truncate">{{ item.product_name }}</div>
            <div class="text-xs text-gray-400">{{ item.sku }} · на складе: {{ item.total_stock }} ед.</div>
          </div>
          <div class="flex items-center gap-2 shrink-0">
            <button
              @click="item.quantity = Math.max(1, item.quantity - 1)"
              class="w-8 h-8 rounded-lg bg-gray-100 hover:bg-gray-200 font-bold text-lg flex items-center justify-center"
            >−</button>
            <input
              v-model.number="item.quantity"
              type="number"
              min="1"
              :max="item.total_stock"
              class="input w-20 text-center font-bold"
              @blur="item.quantity = clamp(item.quantity, 1, item.total_stock)"
            />
            <button
              @click="item.quantity = Math.min(item.total_stock, item.quantity + 1)"
              class="w-8 h-8 rounded-lg bg-gray-100 hover:bg-gray-200 font-bold text-lg flex items-center justify-center"
            >+</button>
          </div>
          <button @click="items.splice(idx, 1)" class="text-red-400 hover:text-red-600 ml-1">✕</button>
        </div>

        <button @click="submitRequest" class="btn-primary w-full btn-lg" :disabled="submitting">
          {{ submitting ? 'Создаём заказ...' : `Сформировать заказ (${items.length} поз.)` }}
        </button>
      </div>

      <p v-if="formError" class="text-red-500 text-sm">{{ formError }}</p>
      <div v-if="successMsg" class="bg-green-50 border border-green-200 rounded-xl p-4 text-green-700 text-sm font-medium">
        {{ successMsg }}
      </div>

      <div class="card p-0 overflow-hidden">
        <div class="px-4 py-3 border-b border-gray-100 flex items-center justify-between">
          <h3 class="font-semibold text-gray-700">Ожидают выполнения</h3>
          <button @click="loadPending" class="btn-secondary text-sm">Обновить</button>
        </div>
        <div v-if="loadingPending" class="p-4 space-y-2">
          <div v-for="i in 3" :key="i" class="skeleton h-10 w-full"></div>
        </div>
        <div v-else-if="!pendingOrders.length" class="p-6 text-center text-gray-400 text-sm">
          Нет заказов в ожидании
        </div>
        <ul v-else class="divide-y divide-gray-50">
          <li
            v-for="o in pendingOrders"
            :key="o.id"
            class="px-4 py-3 flex items-center justify-between gap-3 hover:bg-gray-50"
          >
            <div>
              <span class="font-mono text-gray-600">#{{ o.id }}</span>
              <span class="text-gray-500 text-sm ml-2">{{ o.items?.length ?? 0 }} поз.</span>
              <p v-if="o.comment" class="text-xs text-gray-400 mt-0.5 truncate max-w-md">{{ o.comment }}</p>
            </div>
            <button class="btn-secondary text-sm" :disabled="cancellingId === o.id" @click="cancelOrder(o.id)">
              {{ cancellingId === o.id ? '...' : 'Отменить' }}
            </button>
          </li>
        </ul>
      </div>
    </div>
  </ManagerLayout>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import ManagerLayout from '@/layouts/ManagerLayout.vue'
import { productsApi, warehouseApi } from '@/api'

const query = ref('')
const comment = ref('')
const formError = ref('')
const successMsg = ref('')
const adding = ref(false)
const submitting = ref(false)
const items = ref([])
const suggestions = ref([])
const showSuggest = ref(false)
const pendingOrders = ref([])
const loadingPending = ref(true)
const cancellingId = ref(null)
const uploadFile = ref(null)
const jsonText = ref('')
const uploading = ref(false)
const importingJson = ref(false)
let suggestTimer = null

function onFileChange(e) {
  uploadFile.value = e.target.files?.[0] || null
  formError.value = ''
}

async function submitUpload() {
  if (!uploadFile.value) return
  uploading.value = true
  formError.value = ''
  successMsg.value = ''
  try {
    const { data } = await warehouseApi.uploadConsumptionRequest(
      uploadFile.value,
      comment.value.trim() || undefined,
    )
    successMsg.value = `Заказ #${data.id} создан из файла «${uploadFile.value.name}».`
    uploadFile.value = null
    await loadPending()
  } catch (e) {
    formError.value = e.response?.data?.detail || 'Ошибка загрузки файла'
  } finally {
    uploading.value = false
  }
}

async function submitJson() {
  importingJson.value = true
  formError.value = ''
  successMsg.value = ''
  try {
    const payload = JSON.parse(jsonText.value)
    if (!payload.comment && comment.value.trim()) payload.comment = comment.value.trim()
    const { data } = await warehouseApi.importConsumptionRequestJson(payload)
    successMsg.value = `Заказ #${data.id} создан из JSON.`
    jsonText.value = ''
    await loadPending()
  } catch (e) {
    formError.value = e.response?.data?.detail || (e instanceof SyntaxError ? 'Некорректный JSON' : 'Ошибка импорта')
  } finally {
    importingJson.value = false
  }
}

function clamp(value, min, max) {
  const n = Number(value || 0)
  if (Number.isNaN(n)) return min
  return Math.max(min, Math.min(max, n))
}

function onQueryInput() {
  formError.value = ''
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
  adding.value = true
  try {
    const { data } = await productsApi.list({ search: q, active_only: true })
    suggestions.value = (data || []).slice(0, 10)
  } catch (e) {
    suggestions.value = []
    formError.value = e.response?.data?.detail || 'Ошибка поиска'
  } finally {
    adding.value = false
  }
}

function addFirstSuggestion() {
  if (suggestions.value.length) addProduct(suggestions.value[0])
}

function addProduct(p) {
  if (!p) return
  const total = p.total_stock ?? 0
  if (!total || total <= 0) {
    formError.value = `Товар «${p.sku}» отсутствует на складе`
    return
  }
  const existing = items.value.find(i => i.product_id === p.id)
  if (existing) existing.quantity = clamp(Number(existing.quantity || 1) + 1, 1, existing.total_stock)
  else {
    items.value.push({
      product_id: p.id,
      sku: p.sku,
      product_name: p.name,
      quantity: 1,
      total_stock: total,
    })
  }
  query.value = ''
  suggestions.value = []
  showSuggest.value = false
}

async function submitRequest() {
  submitting.value = true
  formError.value = ''
  successMsg.value = ''
  try {
    const { data } = await warehouseApi.createConsumptionRequest({
      comment: comment.value.trim() || 'Заказ на расход',
      items: items.value.map(i => ({ product_id: i.product_id, quantity: i.quantity })),
    })
    successMsg.value = `Заказ #${data.id} сформирован и передан кладовщикам.`
    items.value = []
    comment.value = ''
    await loadPending()
  } catch (e) {
    formError.value = e.response?.data?.detail || 'Ошибка создания заказа'
  } finally {
    submitting.value = false
  }
}

async function loadPending() {
  loadingPending.value = true
  try {
    const { data } = await warehouseApi.orders({ type: 'CONSUMPTION', status: 'PENDING', limit: 50 })
    pendingOrders.value = data
  } finally {
    loadingPending.value = false
  }
}

async function cancelOrder(id) {
  if (!confirm(`Отменить заказ #${id}?`)) return
  cancellingId.value = id
  try {
    await warehouseApi.deleteOrder(id)
    await loadPending()
  } catch (e) {
    formError.value = e.response?.data?.detail || 'Ошибка отмены'
  } finally {
    cancellingId.value = null
  }
}

onMounted(loadPending)
</script>
