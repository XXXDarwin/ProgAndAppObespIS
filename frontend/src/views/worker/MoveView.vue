<template>
  <WorkerLayout>
    <div class="py-2">
      <div class="flex items-center gap-2 mb-5">
        <router-link to="/" class="text-gray-400 hover:text-gray-600">← Назад</router-link>
        <h2 class="text-xl font-bold text-gray-800">Перемещение товара</h2>
      </div>

      <WorkerFeedback
        v-if="feedback.message"
        class="mb-4"
        :type="feedback.type"
        :title="feedback.title"
        :message="feedback.message"
      />

      <div v-if="step === 'form'" class="card">
        <p class="text-sm text-gray-600 mb-4">
          Укажите товар, ячейки-источник и назначение. Система проверит остаток и вместимость.
        </p>

        <div class="space-y-3 text-sm">
          <div>
            <label class="label">Товар (SKU или название)</label>
            <div class="relative mt-1">
              <div class="flex gap-2">
                <input
                  v-model="productQuery"
                  type="text"
                  class="input"
                  placeholder="Начните вводить..."
                  :disabled="loadingProduct"
                  @input="onProductQueryInput"
                  @keydown.enter.prevent="selectFirstProduct"
                />
                <button type="button" class="btn-secondary px-4" :disabled="!productQuery || loadingProduct" @click="selectFirstProduct">
                  {{ loadingProduct ? '...' : 'Выбрать' }}
                </button>
              </div>
              <div
                v-if="showProductSuggest && productSuggestions.length"
                class="absolute left-0 right-0 mt-1 bg-white border rounded-lg shadow-lg z-20 max-h-48 overflow-y-auto"
              >
                <button
                  v-for="p in productSuggestions"
                  :key="p.id"
                  type="button"
                  class="w-full text-left px-3 py-2 hover:bg-gray-50"
                  @click="selectProduct(p)"
                >
                  <div class="font-mono text-blue-700 text-sm">{{ p.sku }}</div>
                  <div class="text-gray-600 truncate">{{ p.name }}</div>
                </button>
              </div>
            </div>
            <p v-if="selectedProduct" class="text-xs text-gray-500 mt-1">Выбран: {{ selectedProduct.sku }}</p>
          </div>

          <div>
            <label class="label">Количество</label>
            <input v-model.number="quantity" type="number" min="1" class="input w-32" />
          </div>

          <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div>
              <label class="label">Откуда (ячейка)</label>
              <div class="relative">
                <input
                  v-model="fromCellQuery"
                  type="text"
                  class="input font-mono"
                  placeholder="A1-1-1"
                  @focus="showFromSuggest = true"
                  @input="showFromSuggest = true"
                />
                <div
                  v-if="showFromSuggest && filteredCells(fromCellQuery).length"
                  class="absolute left-0 right-0 mt-1 bg-white border rounded-lg shadow-lg z-20 max-h-40 overflow-y-auto"
                >
                  <button
                    v-for="c in filteredCells(fromCellQuery)"
                    :key="c.id"
                    type="button"
                    class="w-full text-left px-3 py-2 hover:bg-gray-50 font-mono text-sm"
                    @click="selectFromCell(c)"
                  >
                    {{ c.address }}
                  </button>
                </div>
              </div>
            </div>
            <div>
              <label class="label">Куда (ячейка)</label>
              <div class="relative">
                <input
                  v-model="toCellQuery"
                  type="text"
                  class="input font-mono"
                  placeholder="A1-1-2"
                  @focus="showToSuggest = true"
                  @input="showToSuggest = true"
                />
                <div
                  v-if="showToSuggest && filteredCells(toCellQuery).length"
                  class="absolute left-0 right-0 mt-1 bg-white border rounded-lg shadow-lg z-20 max-h-40 overflow-y-auto"
                >
                  <button
                    v-for="c in filteredCells(toCellQuery)"
                    :key="c.id"
                    type="button"
                    class="w-full text-left px-3 py-2 hover:bg-gray-50 font-mono text-sm"
                    @click="selectToCell(c)"
                  >
                    {{ c.address }}
                  </button>
                </div>
              </div>
            </div>
          </div>

          <div class="flex gap-3 pt-2">
            <button type="button" class="btn-primary flex-1 btn-lg" :disabled="moving" @click="move">
              {{ moving ? 'Перемещение...' : 'Переместить' }}
            </button>
            <button type="button" class="btn-secondary flex-1" :disabled="moving" @click="resetForm">
              Сброс
            </button>
          </div>
        </div>
      </div>

      <div v-if="step === 'done'">
        <WorkerFeedback type="success" title="Перемещение выполнено" :message="doneMessage" class="mb-4" />
        <div class="flex flex-col gap-2">
          <button type="button" class="btn-primary w-full btn-lg" @click="resetForm">Ещё перемещение</button>
          <button type="button" class="btn-secondary w-full" @click="goHome">На главную</button>
        </div>
      </div>
    </div>
  </WorkerLayout>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import WorkerLayout from '@/layouts/WorkerLayout.vue'
import WorkerFeedback from '@/components/WorkerFeedback.vue'
import { productsApi, warehouseApi, cellsApi } from '@/api'
import { parseApiDetail } from '@/utils/apiError'

const router = useRouter()
const step = ref('form')
const feedback = ref({ type: 'info', title: '', message: '' })
const productQuery = ref('')
const selectedProduct = ref(null)
const loadingProduct = ref(false)
const moving = ref(false)
const doneMessage = ref('')

const productSuggestions = ref([])
const showProductSuggest = ref(false)
let productSuggestTimer = null

const cells = ref([])
const fromCellQuery = ref('')
const toCellQuery = ref('')
const fromCellId = ref(null)
const toCellId = ref(null)
const showFromSuggest = ref(false)
const showToSuggest = ref(false)
const quantity = ref(1)

function clearFeedback() {
  feedback.value = { type: 'info', title: '', message: '' }
}

function showError(msg) {
  feedback.value = { type: 'error', title: 'Ошибка', message: msg }
}

function onProductQueryInput() {
  clearFeedback()
  showProductSuggest.value = true
  if (productSuggestTimer) clearTimeout(productSuggestTimer)
  productSuggestTimer = setTimeout(loadProductSuggestions, 250)
}

async function loadProductSuggestions() {
  const q = productQuery.value.trim()
  if (!q) {
    productSuggestions.value = []
    return
  }
  loadingProduct.value = true
  try {
    const { data } = await productsApi.list({ search: q, active_only: true })
    productSuggestions.value = (data || []).slice(0, 10)
  } catch (e) {
    productSuggestions.value = []
    showError(parseApiDetail(e, 'Ошибка поиска'))
  } finally {
    loadingProduct.value = false
  }
}

function selectFirstProduct() {
  if (productSuggestions.value.length) selectProduct(productSuggestions.value[0])
}

function selectProduct(p) {
  selectedProduct.value = p
  productQuery.value = `${p.sku} — ${p.name}`
  showProductSuggest.value = false
}

function filteredCells(query) {
  const q = String(query ?? '').trim().toLowerCase()
  if (!q) return cells.value.slice(0, 30)
  return cells.value.filter(c => String(c.address).toLowerCase().includes(q)).slice(0, 30)
}

function selectFromCell(c) {
  fromCellId.value = c.id
  fromCellQuery.value = c.address
  showFromSuggest.value = false
}

function selectToCell(c) {
  toCellId.value = c.id
  toCellQuery.value = c.address
  showToSuggest.value = false
}

function resolveCellId(address) {
  const key = String(address ?? '').trim().toUpperCase()
  const found = cells.value.find(c => String(c.address).toUpperCase() === key)
  return found?.id ?? null
}

function resetForm() {
  clearFeedback()
  step.value = 'form'
  productQuery.value = ''
  selectedProduct.value = null
  fromCellQuery.value = ''
  toCellQuery.value = ''
  fromCellId.value = null
  toCellId.value = null
  quantity.value = 1
  doneMessage.value = ''
}

async function move() {
  clearFeedback()
  const product_id = selectedProduct.value?.id
  const from_cell_id = fromCellId.value || resolveCellId(fromCellQuery.value)
  const to_cell_id = toCellId.value || resolveCellId(toCellQuery.value)
  const qty = Number(quantity.value || 0)

  if (!product_id) {
    showError('Выберите товар')
    return
  }
  if (!from_cell_id) {
    showError('Укажите корректную ячейку «откуда»')
    return
  }
  if (!to_cell_id) {
    showError('Укажите корректную ячейку «куда»')
    return
  }
  if (qty <= 0) {
    showError('Количество должно быть больше 0')
    return
  }
  if (from_cell_id === to_cell_id) {
    showError('Ячейки должны отличаться')
    return
  }

  const ok = confirm(
    `Переместить ${qty} ед. «${selectedProduct.value.sku}» из ${fromCellQuery.value.trim()} в ${toCellQuery.value.trim()}?`,
  )
  if (!ok) return

  moving.value = true
  try {
    const { data } = await warehouseApi.moveStock({
      product_id,
      from_cell_id,
      to_cell_id,
      quantity: qty,
    })
    doneMessage.value = data?.detail || `Перемещено ${qty} ед. из ${fromCellQuery.value} в ${toCellQuery.value}.`
    step.value = 'done'
  } catch (e) {
    showError(parseApiDetail(e, 'Не удалось выполнить перемещение'))
  } finally {
    moving.value = false
  }
}

function goHome() {
  router.push({ name: 'Home' })
}

onMounted(async () => {
  try {
    const { data } = await cellsApi.list()
    cells.value = (data || [])
      .filter(c => c.is_active !== false)
      .map(c => ({ id: c.id, address: c.address }))
      .sort((a, b) => String(a.address).localeCompare(String(b.address)))
  } catch {
    cells.value = []
  }
})
</script>
