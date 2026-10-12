<template>
  <ManagerLayout>
    <div class="space-y-4">
      <div class="flex gap-3 flex-wrap">
        <input v-model="search" type="text" class="input w-64" placeholder="Поиск по SKU или названию..." />
        <button @click="load" class="btn-secondary">Обновить</button>
        <button @click="openClearModal()" class="btn-secondary">Удалить остатки</button>
        <button @click="openMoveModal()" class="btn-secondary">Переместить</button>
        <router-link to="/inventory-requests" class="btn-secondary">Инвентаризация</router-link>
      </div>

      <div class="card p-0 overflow-hidden">
        <div v-if="loading" class="p-6 space-y-2">
          <div v-for="i in 6" :key="i" class="skeleton h-10 w-full"></div>
        </div>
        <div v-else class="overflow-x-auto">
          <table class="w-full text-sm">
            <thead class="bg-gray-50 border-b border-gray-100">
              <tr class="text-left text-gray-500">
                <th class="px-4 py-3 font-medium w-36">SKU</th>
                <th class="px-4 py-3 font-medium min-w-[200px]">Название</th>
                <th class="px-4 py-3 font-medium w-32">Ячейка</th>
                <th class="px-4 py-3 font-medium text-right w-24">Кол-во</th>
                <th class="px-4 py-3 font-medium text-right w-36">Действия</th>
              </tr>
            </thead>
            <tbody class="divide-y divide-gray-50">
              <tr v-for="row in filtered" :key="`${row.product_id}-${row.cell_id}`" class="hover:bg-gray-50">
                <td class="px-4 py-2.5 font-mono text-blue-700 font-medium whitespace-nowrap">
                  {{ stockSku(row) }}
                </td>
                <td class="px-4 py-2.5 text-gray-700" :title="stockName(row)">
                  <span class="line-clamp-2">{{ stockName(row) }}</span>
                </td>
                <td class="px-4 py-2.5 whitespace-nowrap">
                  <span class="badge badge-blue font-mono">{{ stockCellAddress(row) }}</span>
                </td>
                <td class="px-4 py-2.5 text-right font-semibold text-gray-800 whitespace-nowrap">{{ row.quantity }}</td>
                <td class="px-4 py-2.5 text-right whitespace-nowrap">
                  <div class="flex justify-end gap-2">
                    <button class="btn-secondary text-sm" @click="openMoveModal(row)">Переместить</button>
                    <button
                      class="btn-secondary text-sm"
                      :disabled="clearingRowKey === rowKey(row)"
                      @click="clearRow(row)"
                    >
                      {{ clearingRowKey === rowKey(row) ? '...' : 'Удалить' }}
                    </button>
                  </div>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
        <div v-if="!loading && !filtered.length" class="text-center text-gray-400 py-12 text-sm">Нет данных</div>
      </div>

      <!-- Clear stocks modal -->
      <div
        v-if="showClear"
        class="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4"
        @click.self="showClear=false"
      >
        <div class="bg-white rounded-2xl shadow-xl w-full max-w-md p-6">
          <h3 class="text-lg font-bold mb-4">Удалить остатки</h3>
          <div class="space-y-3 text-sm">
            <div>
              <label class="label">Товар (SKU или название)</label>
              <div class="relative">
                <input
                  v-model="clearProductQuery"
                  type="text"
                  class="input"
                  placeholder="Необязательно — все ячейки с этим товаром"
                  @input="onClearProductInput"
                  @keydown.enter.prevent="selectFirstClearProduct"
                />
                <div
                  v-if="showClearProductSuggest && clearProductSuggestions.length"
                  class="absolute left-0 right-0 mt-1 bg-white border border-gray-200 rounded-lg shadow-lg z-30 max-h-48 overflow-y-auto"
                >
                  <button
                    v-for="p in clearProductSuggestions"
                    :key="p.id"
                    type="button"
                    class="w-full text-left px-3 py-2 hover:bg-gray-50"
                    @click="selectClearProduct(p)"
                  >
                    <div class="font-mono text-sm text-blue-700">{{ p.sku }}</div>
                    <div class="text-gray-600 truncate">{{ p.name }}</div>
                  </button>
                </div>
              </div>
            </div>
            <div>
              <label class="label">Ячейка</label>
              <div class="relative">
                <input
                  v-model="clearCellQuery"
                  type="text"
                  class="input font-mono"
                  placeholder="Необязательно — все товары в ячейке"
                  @focus="showClearCellSuggest = true"
                  @input="showClearCellSuggest = true"
                />
                <div
                  v-if="showClearCellSuggest && filteredCells(clearCellQuery).length"
                  class="absolute left-0 right-0 mt-1 bg-white border border-gray-200 rounded-lg shadow-lg z-30 max-h-40 overflow-y-auto"
                >
                  <button
                    v-for="c in filteredCells(clearCellQuery)"
                    :key="c.id"
                    type="button"
                    class="w-full text-left px-3 py-2 hover:bg-gray-50 font-mono text-sm"
                    @click="selectClearCell(c)"
                  >
                    {{ c.address }}
                  </button>
                </div>
              </div>
            </div>
            <p class="text-xs text-gray-500">
              Укажите товар, ячейку или оба поля. Остатки обнуляются (запись в истории сохраняется).
            </p>
          </div>

          <p v-if="clearError" class="text-red-500 text-sm mt-2">{{ clearError }}</p>
          <div class="flex gap-3 mt-4">
            <button @click="clearStocks" class="btn-primary flex-1" :disabled="clearing">
              {{ clearing ? '...' : 'Удалить' }}
            </button>
            <button @click="showClear=false" class="btn-secondary flex-1">Отмена</button>
          </div>
        </div>
      </div>

      <!-- Move stock modal -->
      <div
        v-if="showMove"
        class="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4"
        @click.self="closeMoveModal"
      >
        <div class="bg-white rounded-2xl shadow-xl w-full max-w-lg p-6">
          <h3 class="text-lg font-bold mb-4">Перемещение товара</h3>
          <div class="space-y-3 text-sm">
            <div v-if="moveContext.sku" class="bg-gray-50 rounded-lg px-3 py-2">
              <div class="font-mono text-blue-700 font-medium">{{ moveContext.sku }}</div>
              <div class="text-gray-700 mt-0.5">{{ moveContext.name }}</div>
            </div>
            <div v-else>
              <label class="label">Товар (SKU или название)</label>
              <div class="relative">
                <input
                  v-model="productQuery"
                  type="text"
                  class="input"
                  placeholder="Начните вводить..."
                  @input="onProductQueryInput"
                  @keydown.enter.prevent="selectFirstProduct"
                />
                <div
                  v-if="showProductSuggest && productSuggestions.length"
                  class="absolute left-0 right-0 mt-1 bg-white border border-gray-200 rounded-lg shadow-lg z-30 max-h-48 overflow-y-auto"
                >
                  <button
                    v-for="p in productSuggestions"
                    :key="p.id"
                    type="button"
                    class="w-full text-left px-3 py-2 hover:bg-gray-50"
                    @click="selectProduct(p)"
                  >
                    <div class="font-mono text-sm text-blue-700">{{ p.sku }}</div>
                    <div class="text-gray-600 truncate">{{ p.name }}</div>
                  </button>
                </div>
              </div>
            </div>

            <div class="grid grid-cols-2 gap-3">
              <div>
                <label class="label">Откуда (ячейка)</label>
                <input
                  v-if="moveContext.fromLocked"
                  :value="fromCellQuery"
                  type="text"
                  class="input font-mono bg-gray-50"
                  disabled
                />
                <div v-else class="relative">
                  <input
                    v-model="fromCellQuery"
                    type="text"
                    class="input font-mono"
                    placeholder="Например A1-1-1"
                    @focus="showFromCellSuggest = true"
                    @input="showFromCellSuggest = true"
                  />
                  <div
                    v-if="showFromCellSuggest && filteredCells(fromCellQuery).length"
                    class="absolute left-0 right-0 mt-1 bg-white border border-gray-200 rounded-lg shadow-lg z-30 max-h-40 overflow-y-auto"
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
                    placeholder="Например A1-1-2"
                    @focus="showToCellSuggest = true"
                    @input="showToCellSuggest = true"
                  />
                  <div
                    v-if="showToCellSuggest && filteredCells(toCellQuery).length"
                    class="absolute left-0 right-0 mt-1 bg-white border border-gray-200 rounded-lg shadow-lg z-30 max-h-40 overflow-y-auto"
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

            <div>
              <label class="label">Количество</label>
              <input v-model.number="moveForm.quantity" type="number" class="input" min="1" :max="moveContext.maxQty || undefined" />
              <p v-if="moveContext.maxQty" class="text-xs text-gray-500 mt-1">
                Доступно в ячейке-источнике: {{ moveContext.maxQty }}
              </p>
            </div>
            <p class="text-xs text-gray-500">
              Укажите адреса ячеек в формате склада (например A1-1-1). Перемещение проверяет остаток и свободную вместимость.
            </p>
          </div>

          <p v-if="moveError" class="text-red-500 text-sm mt-2">{{ moveError }}</p>
          <div class="flex gap-3 mt-4">
            <button @click="moveStock" class="btn-primary flex-1" :disabled="moving">
              {{ moving ? '...' : 'Переместить' }}
            </button>
            <button @click="closeMoveModal" class="btn-secondary flex-1">Отмена</button>
          </div>
        </div>
      </div>
    </div>
  </ManagerLayout>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import ManagerLayout from '@/layouts/ManagerLayout.vue'
import { warehouseApi, cellsApi, productsApi } from '@/api'
import { parseApiDetail } from '@/utils/apiError'

const stocks = ref([])
const loading = ref(true)
const search = ref('')
const showClear = ref(false)
const clearing = ref(false)
const clearingRowKey = ref(null)
const clearError = ref('')
const clearProductId = ref(null)
const clearProductQuery = ref('')
const clearCellQuery = ref('')
const clearProductSuggestions = ref([])
const showClearProductSuggest = ref(false)
const showClearCellSuggest = ref(false)
let clearProductTimer = null

const showMove = ref(false)
const moving = ref(false)
const moveError = ref('')
const moveForm = ref({ product_id: null, quantity: 1 })
const moveContext = ref({ sku: '', name: '', fromLocked: false, maxQty: null })

const cells = ref([])
const productQuery = ref('')
const productSuggestions = ref([])
const showProductSuggest = ref(false)
let productSuggestTimer = null

const fromCellQuery = ref('')
const toCellQuery = ref('')
const showFromCellSuggest = ref(false)
const showToCellSuggest = ref(false)

function stockSku(row) {
  return row.product?.sku ?? `ID ${row.product_id}`
}

function stockName(row) {
  return row.product?.name ?? '—'
}

function stockCellAddress(row) {
  return row.cell?.address ?? '—'
}

function rowKey(row) {
  return `${row.product_id}-${row.cell_id}`
}

const filtered = computed(() => {
  const q = search.value.toLowerCase().trim()
  if (!q) return stocks.value
  return stocks.value.filter(s =>
    stockSku(s).toLowerCase().includes(q) ||
    stockName(s).toLowerCase().includes(q) ||
    stockCellAddress(s).toLowerCase().includes(q)
  )
})

async function load() {
  loading.value = true
  try {
    const { data } = await warehouseApi.stocks()
    stocks.value = data
  } finally { loading.value = false }
}

async function loadCells() {
  try {
    const { data } = await cellsApi.list()
    cells.value = (data || [])
      .filter(c => c.is_active !== false)
      .map(c => ({ id: c.id, address: c.address }))
      .sort((a, b) => String(a.address).localeCompare(String(b.address)))
  } catch {
    cells.value = []
  }
}

function filteredCells(query) {
  const q = String(query ?? '').trim().toLowerCase()
  const list = cells.value
  if (!q) return list.slice(0, 30)
  return list.filter(c => String(c.address).toLowerCase().includes(q)).slice(0, 30)
}

function resolveCellId(address) {
  const key = String(address ?? '').trim().toUpperCase()
  if (!key) return null
  const found = cells.value.find(c => String(c.address).toUpperCase() === key)
  return found?.id ?? null
}

function onProductQueryInput() {
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
  try {
    const { data } = await productsApi.list({ search: q, active_only: true })
    productSuggestions.value = (data || []).slice(0, 10)
  } catch {
    productSuggestions.value = []
  }
}

function selectFirstProduct() {
  if (productSuggestions.value.length) selectProduct(productSuggestions.value[0])
}

function selectProduct(p) {
  moveForm.value.product_id = p.id
  moveContext.value = { ...moveContext.value, sku: p.sku, name: p.name }
  productQuery.value = `${p.sku} — ${p.name}`
  showProductSuggest.value = false
}

function selectFromCell(c) {
  fromCellQuery.value = c.address
  showFromCellSuggest.value = false
}

function selectToCell(c) {
  toCellQuery.value = c.address
  showToCellSuggest.value = false
}

function resolveClearProductId() {
  if (clearProductId.value) return clearProductId.value
  const q = clearProductQuery.value.trim().toLowerCase()
  if (!q) return null
  const skuPart = q.split(/\s+—\s+/)[0].trim()
  const found = stocks.value.find(s => {
    const sku = stockSku(s).toLowerCase()
    return sku === skuPart || sku === q
  })
  return found?.product_id ?? null
}

function resolveClearParams() {
  const product_id = resolveClearProductId()
  const cell_id = resolveCellId(clearCellQuery.value)
  return { product_id, cell_id }
}

function clearParamsLabel({ product_id, cell_id }) {
  const parts = []
  if (product_id) {
    const row = stocks.value.find(s => s.product_id === product_id)
    parts.push(`товар «${row ? stockSku(row) : product_id}»`)
  }
  if (cell_id) {
    const cell = cells.value.find(c => c.id === cell_id)
    parts.push(`ячейка ${cell?.address || cell_id}`)
  }
  return parts.join(', ')
}

async function runClearStocks(params, { closeModal = false } = {}) {
  const { product_id, cell_id } = params
  if (!product_id && !cell_id) {
    throw new Error('Укажите товар и/или ячейку')
  }

  const { data } = await warehouseApi.clearStocks({ product_id, cell_id })
  if (!data?.cleared_rows) {
    throw new Error('Ничего не найдено — проверьте товар и ячейку')
  }

  if (closeModal) {
    showClear.value = false
    resetClearForm()
  }
  await load()
}

function resetClearForm() {
  clearProductId.value = null
  clearProductQuery.value = ''
  clearCellQuery.value = ''
  clearProductSuggestions.value = []
  showClearProductSuggest.value = false
  showClearCellSuggest.value = false
}

async function openClearModal(row = null) {
  clearError.value = ''
  await loadCells()
  resetClearForm()
  if (row) {
    clearProductId.value = row.product_id
    clearProductQuery.value = `${stockSku(row)} — ${stockName(row)}`
    const addr = stockCellAddress(row)
    if (addr !== '—') clearCellQuery.value = addr
  }
  showClear.value = true
}

function onClearProductInput() {
  clearProductId.value = null
  showClearProductSuggest.value = true
  if (clearProductTimer) clearTimeout(clearProductTimer)
  clearProductTimer = setTimeout(loadClearProductSuggestions, 250)
}

async function loadClearProductSuggestions() {
  const q = clearProductQuery.value.trim()
  if (!q) {
    clearProductSuggestions.value = []
    return
  }
  try {
    const { data } = await productsApi.list({ search: q, active_only: true })
    clearProductSuggestions.value = (data || []).slice(0, 10)
  } catch {
    clearProductSuggestions.value = []
  }
}

function selectFirstClearProduct() {
  if (clearProductSuggestions.value.length) selectClearProduct(clearProductSuggestions.value[0])
}

function selectClearProduct(p) {
  clearProductId.value = p.id
  clearProductQuery.value = `${p.sku} — ${p.name}`
  showClearProductSuggest.value = false
}

function selectClearCell(c) {
  clearCellQuery.value = c.address
  showClearCellSuggest.value = false
}

async function clearStocks() {
  clearError.value = ''
  const params = resolveClearParams()

  if (clearProductQuery.value.trim() && !params.product_id) {
    clearError.value = 'Выберите товар из списка подсказок'
    return
  }
  if (clearCellQuery.value.trim() && !params.cell_id) {
    clearError.value = 'Укажите корректный адрес ячейки'
    return
  }
  if (!params.product_id && !params.cell_id) {
    clearError.value = 'Укажите товар и/или ячейку'
    return
  }

  const ok = confirm(`Удалить остатки: ${clearParamsLabel(params)}?`)
  if (!ok) return

  clearing.value = true
  try {
    await runClearStocks(params, { closeModal: true })
  } catch (e) {
    clearError.value = parseApiDetail(e, e.message || 'Ошибка удаления остатков')
  } finally {
    clearing.value = false
  }
}

async function clearRow(row) {
  const addr = stockCellAddress(row)
  const ok = confirm(
    `Удалить остаток ${row.quantity} ед. «${stockSku(row)}»` +
    (addr !== '—' ? ` в ячейке ${addr}` : '') + '?',
  )
  if (!ok) return

  const key = rowKey(row)
  clearingRowKey.value = key
  try {
    await runClearStocks({ product_id: row.product_id, cell_id: row.cell_id })
  } catch (e) {
    alert(parseApiDetail(e, e.message || 'Ошибка удаления остатков'))
  } finally {
    clearingRowKey.value = null
  }
}

function closeMoveModal() {
  showMove.value = false
  moveError.value = ''
}

async function openMoveModal(row = null) {
  moveError.value = ''
  await loadCells()

  if (row) {
    moveForm.value = {
      product_id: row.product_id,
      quantity: 1,
    }
    moveContext.value = {
      sku: stockSku(row),
      name: stockName(row),
      fromLocked: true,
      maxQty: row.quantity,
    }
    fromCellQuery.value = stockCellAddress(row)
    toCellQuery.value = ''
  } else {
    moveForm.value = { product_id: null, quantity: 1 }
    moveContext.value = { sku: '', name: '', fromLocked: false, maxQty: null }
    fromCellQuery.value = ''
    toCellQuery.value = ''
    productQuery.value = ''
    productSuggestions.value = []
  }

  showFromCellSuggest.value = false
  showToCellSuggest.value = false
  showProductSuggest.value = false
  showMove.value = true
}

async function moveStock() {
  moveError.value = ''

  const product_id = moveForm.value.product_id
  const from_cell_id = resolveCellId(fromCellQuery.value)
  const to_cell_id = resolveCellId(toCellQuery.value)
  const quantity = Number(moveForm.value.quantity || 0)

  if (!product_id) {
    moveError.value = 'Выберите товар'
    return
  }
  if (!from_cell_id) {
    moveError.value = 'Укажите корректный адрес ячейки-источника'
    return
  }
  if (!to_cell_id) {
    moveError.value = 'Укажите корректный адрес ячейки-назначения'
    return
  }
  if (quantity <= 0) {
    moveError.value = 'Количество должно быть больше 0'
    return
  }
  if (moveContext.value.maxQty != null && quantity > moveContext.value.maxQty) {
    moveError.value = `В ячейке доступно не более ${moveContext.value.maxQty} ед.`
    return
  }
  if (from_cell_id === to_cell_id) {
    moveError.value = 'Ячейки источника и назначения должны отличаться'
    return
  }

  const sku = moveContext.value.sku || `ID ${product_id}`
  const ok = confirm(
    `Переместить ${quantity} ед. «${sku}» из ${fromCellQuery.value.trim()} в ${toCellQuery.value.trim()}?`
  )
  if (!ok) return

  moving.value = true
  try {
    await warehouseApi.moveStock({ product_id, from_cell_id, to_cell_id, quantity })
    closeMoveModal()
    await load()
  } catch (e) {
    moveError.value = parseApiDetail(e, 'Ошибка перемещения')
  } finally {
    moving.value = false
  }
}

onMounted(async () => {
  await Promise.all([load(), loadCells()])
})
</script>
