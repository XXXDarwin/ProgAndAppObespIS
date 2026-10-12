<template>
  <ManagerLayout>
    <div class="space-y-6 max-w-3xl">
      <p class="text-sm text-gray-500">
        Сформируйте заказ на приёмку вручную, загрузите Excel/CSV/JSON или вставьте JSON. Кладовщик выполнит приёмку в разделе «Приёмка».
      </p>

      <div class="card">
        <label class="label">Комментарий к заказу (необязательно)</label>
        <input v-model="comment" type="text" class="input mt-1" placeholder="Например: поставка от поставщика №15" />
      </div>

      <!-- Загрузка файла -->
      <div class="card space-y-3">
        <h3 class="font-semibold text-gray-700">Загрузка из файла</h3>
        <p class="text-xs text-gray-500">
          Форматы: .xlsx, .xls, .csv, .json. Колонки: <span class="font-mono">sku</span>, <span class="font-mono">quantity</span>, опционально <span class="font-mono">cell</span> (адрес ячейки).
        </p>
        <input type="file" accept=".xlsx,.xls,.csv,.json" class="input" @change="onFileChange" />
        <button class="btn-primary" :disabled="!uploadFile || uploading" @click="submitUpload">
          {{ uploading ? 'Загрузка...' : 'Создать заказ из файла' }}
        </button>
      </div>

      <!-- JSON -->
      <div class="card space-y-3">
        <h3 class="font-semibold text-gray-700">Импорт JSON</h3>
        <p class="text-xs text-gray-500 font-mono">
          { "comment": "...", "items": [{ "sku": "ABC-1", "quantity": 10, "cell_address": "A1-1-1" }] }
        </p>
        <textarea v-model="jsonText" class="input font-mono text-sm min-h-[120px]" placeholder='{"items":[{"sku":"...","quantity":1}]}' />
        <button class="btn-secondary" :disabled="!jsonText.trim() || importingJson" @click="submitJson">
          {{ importingJson ? 'Импорт...' : 'Создать заказ из JSON' }}
        </button>
      </div>

      <!-- Вручную -->
      <div class="card">
        <h3 class="font-semibold text-gray-700 mb-3">Добавить товар вручную</h3>
        <div class="relative">
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
              <div class="font-semibold text-gray-800 truncate">{{ p.name }}</div>
              <div class="text-xs text-gray-400 font-mono">{{ p.sku }}</div>
            </button>
          </div>
        </div>
      </div>

      <div v-if="items.length" class="space-y-3">
        <div v-for="(item, idx) in items" :key="idx" class="card flex items-center gap-3">
          <div class="flex-1 min-w-0">
            <div class="font-semibold text-gray-800 truncate">{{ item.product_name }}</div>
            <div class="text-xs text-gray-400">{{ item.sku }}</div>
            <div class="mt-2">
              <label class="text-xs text-gray-500">Ячейка (рекомендуемая)</label>
              <select v-model="item.cell_id" class="input mt-1 text-sm">
                <option value="">Автоподбор при приёмке</option>
                <option v-for="cell in cells" :key="cell.id" :value="cell.id">
                  {{ cell.address }}
                </option>
              </select>
            </div>
          </div>
          <div class="flex items-center gap-2 shrink-0">
            <button @click="item.quantity = Math.max(1, item.quantity - 1)" class="w-8 h-8 rounded-lg bg-gray-100 font-bold">−</button>
            <input v-model.number="item.quantity" type="number" min="1" class="input w-20 text-center font-bold" />
            <button @click="item.quantity++" class="w-8 h-8 rounded-lg bg-gray-100 font-bold">+</button>
          </div>
          <button @click="items.splice(idx, 1)" class="text-red-400">✕</button>
        </div>
        <button @click="submitManual" class="btn-primary w-full btn-lg" :disabled="submitting">
          {{ submitting ? 'Создаём...' : `Сформировать заказ (${items.length} поз.)` }}
        </button>
      </div>

      <p v-if="formError" class="text-red-500 text-sm">{{ formError }}</p>
      <div v-if="successMsg" class="bg-green-50 border border-green-200 rounded-xl p-4 text-green-700 text-sm font-medium">
        {{ successMsg }}
      </div>

      <div class="card p-0 overflow-hidden">
        <div class="px-4 py-3 border-b border-gray-100 flex items-center justify-between">
          <h3 class="font-semibold text-gray-700">Ожидают приёмки</h3>
          <button @click="loadPending" class="btn-secondary text-sm">Обновить</button>
        </div>
        <div v-if="loadingPending" class="p-4"><div class="skeleton h-10 w-full"></div></div>
        <div v-else-if="!pendingOrders.length" class="p-6 text-center text-gray-400 text-sm">Нет заказов</div>
        <ul v-else class="divide-y divide-gray-50">
          <li v-for="o in pendingOrders" :key="o.id" class="px-4 py-3 flex justify-between gap-3 hover:bg-gray-50">
            <div>
              <span class="font-mono text-gray-600">#{{ o.id }}</span>
              <span class="text-sm text-gray-500 ml-2">{{ o.items?.length ?? 0 }} поз.</span>
              <p v-if="o.comment" class="text-xs text-gray-400 mt-0.5">{{ o.comment }}</p>
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
import { cellsApi, productsApi, warehouseApi } from '@/api'

const comment = ref('')
const query = ref('')
const formError = ref('')
const successMsg = ref('')
const adding = ref(false)
const submitting = ref(false)
const uploading = ref(false)
const importingJson = ref(false)
const items = ref([])
const suggestions = ref([])
const showSuggest = ref(false)
const cells = ref([])
const uploadFile = ref(null)
const jsonText = ref('')
const pendingOrders = ref([])
const loadingPending = ref(true)
const cancellingId = ref(null)
let suggestTimer = null

function onQueryInput() {
  formError.value = ''
  showSuggest.value = true
  if (suggestTimer) clearTimeout(suggestTimer)
  suggestTimer = setTimeout(loadSuggestions, 250)
}

async function loadSuggestions() {
  const q = query.value.trim()
  if (!q) { suggestions.value = []; return }
  adding.value = true
  try {
    const { data } = await productsApi.list({ search: q, active_only: true })
    suggestions.value = (data || []).slice(0, 10)
  } finally { adding.value = false }
}

function addFirstSuggestion() {
  if (suggestions.value.length) addProduct(suggestions.value[0])
}

function addProduct(p) {
  if (!p) return
  const existing = items.value.find(i => i.product_id === p.id)
  if (existing) existing.quantity++
  else items.value.push({ product_id: p.id, sku: p.sku, product_name: p.name, quantity: 1, cell_id: '' })
  query.value = ''
  suggestions.value = []
  showSuggest.value = false
}

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
    const { data } = await warehouseApi.uploadArrivalRequest(uploadFile.value, comment.value.trim() || undefined)
    successMsg.value = `Заказ #${data.id} создан из файла «${uploadFile.value.name}».`
    uploadFile.value = null
    await loadPending()
  } catch (e) {
    formError.value = e.response?.data?.detail || 'Ошибка загрузки файла'
  } finally { uploading.value = false }
}

async function submitJson() {
  importingJson.value = true
  formError.value = ''
  successMsg.value = ''
  try {
    const payload = JSON.parse(jsonText.value)
    if (!payload.comment && comment.value.trim()) payload.comment = comment.value.trim()
    const { data } = await warehouseApi.importArrivalRequestJson(payload)
    successMsg.value = `Заказ #${data.id} создан из JSON.`
    jsonText.value = ''
    await loadPending()
  } catch (e) {
    formError.value = e.response?.data?.detail || (e instanceof SyntaxError ? 'Некорректный JSON' : 'Ошибка импорта')
  } finally { importingJson.value = false }
}

async function submitManual() {
  submitting.value = true
  formError.value = ''
  successMsg.value = ''
  try {
    const { data } = await warehouseApi.createArrivalRequest({
      comment: comment.value.trim() || 'Заказ на приёмку',
      items: items.value.map(i => ({
        product_id: i.product_id,
        quantity: i.quantity,
        cell_id: i.cell_id ? Number(i.cell_id) : undefined,
      })),
    })
    successMsg.value = `Заказ #${data.id} сформирован.`
    items.value = []
    await loadPending()
  } catch (e) {
    formError.value = e.response?.data?.detail || 'Ошибка создания'
  } finally { submitting.value = false }
}

async function loadPending() {
  loadingPending.value = true
  try {
    const { data } = await warehouseApi.orders({ type: 'ARRIVAL', status: 'PENDING', limit: 50 })
    pendingOrders.value = data
  } finally { loadingPending.value = false }
}

async function cancelOrder(id) {
  if (!confirm(`Отменить заказ #${id}?`)) return
  cancellingId.value = id
  try {
    await warehouseApi.deleteOrder(id)
    await loadPending()
  } catch (e) {
    formError.value = e.response?.data?.detail || 'Ошибка отмены'
  } finally { cancellingId.value = null }
}

onMounted(async () => {
  try {
    const { data } = await cellsApi.list()
    cells.value = (data || []).filter(c => c.is_active)
  } catch { cells.value = [] }
  loadPending()
})
</script>
