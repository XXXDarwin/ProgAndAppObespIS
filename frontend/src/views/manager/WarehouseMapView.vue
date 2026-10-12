<template>
  <ManagerLayout>
    <div class="space-y-4">

      <!-- Controls -->
      <div class="flex flex-wrap items-center gap-3">
        <!-- Zone tabs -->
        <div class="flex gap-1 bg-gray-100 rounded-lg p-1">
          <button
            v-for="zone in zones" :key="zone"
            @click="selectedZone = zone"
            class="px-4 py-1.5 text-sm font-semibold rounded-md transition-all"
            :class="selectedZone === zone
              ? 'bg-white text-blue-700 shadow-sm'
              : 'text-gray-500 hover:text-gray-700'"
          >Зона {{ zone }}</button>
        </div>

        <button @click="load" class="btn-secondary text-sm">Обновить</button>
      </div>

      <!-- Legend -->
      <div class="flex flex-wrap gap-4 text-xs font-medium">
        <div class="flex items-center gap-1.5"><div class="w-4 h-4 rounded bg-gray-100 border border-gray-200"></div> Свободна</div>
        <div class="flex items-center gap-1.5"><div class="w-4 h-4 rounded bg-blue-200 border border-blue-300"></div> Заполнена &lt;50%</div>
        <div class="flex items-center gap-1.5"><div class="w-4 h-4 rounded bg-blue-400 border border-blue-500"></div> Заполнена 50–80%</div>
        <div class="flex items-center gap-1.5"><div class="w-4 h-4 rounded bg-blue-600 border border-blue-700"></div> Заполнена &gt;80%</div>
        <div class="flex items-center gap-1.5"><div class="w-4 h-4 rounded bg-red-200 border border-red-300"></div> Переполнена</div>
      </div>

      <!-- Loading -->
      <div v-if="loading" class="card flex items-center justify-center h-72">
        <div class="text-center">
          <div class="skeleton w-12 h-12 rounded-lg mx-auto mb-3"></div>
          <div class="text-sm text-gray-400">Загрузка карты склада...</div>
        </div>
      </div>

      <!-- Map grids: all racks in zone -->
      <div v-else-if="zoneCells.length" class="space-y-4">
        <div class="grid gap-4" :class="racks.length > 1 ? 'grid-cols-1 xl:grid-cols-2' : 'grid-cols-1'">
          <div v-for="rack in racks" :key="rack" class="card p-4 overflow-x-auto">
            <div class="flex items-center justify-between mb-3">
              <div class="font-semibold text-gray-700">Зона {{ selectedZone }} · Стеллаж {{ rack }}</div>
              <div class="text-xs text-gray-400">ячееек: {{ rackCellsCount(rack) }}</div>
            </div>

            <!-- Полки — строки, позиции — столбцы -->
            <div class="min-w-max" v-if="rackPositions(rack).length && rackShelves(rack).length">
              <!-- Column headers (positions) -->
              <div class="flex mb-2 ml-14">
                <div
                  v-for="pos in rackPositions(rack)" :key="pos"
                  class="w-16 text-center text-xs font-semibold text-gray-400"
                >П-{{ pos }}</div>
              </div>

              <!-- Rows (shelves) -->
              <div v-for="shelf in rackShelves(rack)" :key="shelf" class="flex items-center mb-2">
                <!-- Row header -->
                <div class="w-14 shrink-0 text-xs font-semibold text-gray-500 text-right pr-3">
                  Полка {{ shelf }}
                </div>

                <!-- Cells -->
                <div
                  v-for="pos in rackPositions(rack)" :key="pos"
                  class="w-16 h-14 mx-0.5 rounded-lg border-2 cursor-pointer transition-all hover:scale-105 hover:shadow-md flex flex-col items-center justify-center relative"
                  :class="cellClass(getCell(rack, shelf, pos))"
                  @click="selectCell(getCell(rack, shelf, pos))"
                >
                  <template v-if="getCell(rack, shelf, pos)">
                    <div class="text-xs font-bold leading-none">
                      {{ getCell(rack, shelf, pos).current_stock }}
                    </div>
                    <div class="text-[10px] opacity-70 leading-none mt-0.5">
                      / {{ getCell(rack, shelf, pos).max_capacity }}
                    </div>
                    <!-- Fill bar -->
                    <div class="absolute bottom-0 left-0 right-0 h-1 rounded-b-lg bg-black/10 overflow-hidden">
                      <div
                        class="h-full bg-white/50 transition-all"
                        :style="{ width: fillPct(getCell(rack, shelf, pos)) + '%' }"
                      ></div>
                    </div>
                  </template>
                  <template v-else>
                    <div class="text-gray-200 text-lg">—</div>
                  </template>
                </div>
              </div>
            </div>
            <div v-else class="text-center text-gray-400 text-sm py-10">
              В этом стеллаже нет ячеек.
            </div>
          </div>
        </div>
      </div>

      <div v-else class="card text-center py-16 text-gray-400 text-sm">
        В зоне {{ selectedZone }} нет ячеек.<br/>
        <router-link to="/cells" class="text-blue-500 hover:underline mt-1 inline-block">Создать ячейки →</router-link>
      </div>

      <!-- Stats bar -->
      <div v-if="!loading && zoneCells.length" class="grid grid-cols-4 gap-3">
        <div class="card text-center py-3">
          <div class="text-lg font-bold text-gray-700">{{ zoneCells.length }}</div>
          <div class="text-xs text-gray-400">Всего ячеек</div>
        </div>
        <div class="card text-center py-3">
          <div class="text-lg font-bold text-green-600">{{ emptyCells }}</div>
          <div class="text-xs text-gray-400">Свободных</div>
        </div>
        <div class="card text-center py-3">
          <div class="text-lg font-bold text-blue-600">{{ occupiedCells }}</div>
          <div class="text-xs text-gray-400">Занятых</div>
        </div>
        <div class="card text-center py-3">
          <div class="text-lg font-bold text-gray-700">{{ Math.round(avgFill) }}%</div>
          <div class="text-xs text-gray-400">Загрузка</div>
        </div>
      </div>

      <!-- Cell detail popup -->
      <div
        v-if="selectedCell"
        class="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4"
        @click.self="selectedCell = null"
      >
        <div class="bg-white rounded-2xl shadow-xl w-full max-w-sm p-6">
          <div class="flex justify-between items-start mb-4">
            <div>
              <h3 class="text-xl font-bold text-gray-800">{{ selectedCell.address }}</h3>
              <div class="text-sm text-gray-400 mt-0.5">Зона {{ selectedCell.zone }} · Стеллаж {{ selectedCell.rack }} · Полка {{ selectedCell.shelf }}</div>
            </div>
            <button @click="selectedCell = null" class="text-gray-300 hover:text-gray-500 text-2xl">✕</button>
          </div>

          <!-- Fill indicator -->
          <div class="mb-4">
            <div class="flex justify-between text-sm mb-1">
              <span class="text-gray-500">Заполненность</span>
              <span class="font-semibold" :class="fillPct(selectedCell) > 80 ? 'text-red-600' : 'text-blue-600'">
                {{ Math.round(fillPct(selectedCell)) }}%
              </span>
            </div>
            <div class="w-full h-3 bg-gray-100 rounded-full overflow-hidden">
              <div
                class="h-full rounded-full transition-all"
                :class="fillPct(selectedCell) > 100 ? 'bg-red-500' : fillPct(selectedCell) > 80 ? 'bg-orange-400' : 'bg-blue-500'"
                :style="{ width: Math.min(100, fillPct(selectedCell)) + '%' }"
              ></div>
            </div>
            <div class="flex justify-between text-xs text-gray-400 mt-1">
              <span>{{ selectedCell.current_stock }} ед.</span>
              <span>макс. {{ selectedCell.max_capacity }}</span>
            </div>
            <p v-if="fillPct(selectedCell) > 100" class="text-xs text-red-600 mt-1">
              Превышен лимит ячейки — сумма всех товаров больше вместимости (часто после многократных приёмок при генерации данных).
            </p>
            <p v-else class="text-xs text-gray-400 mt-1">
              Лимит {{ selectedCell.max_capacity }} ед. — на все SKU в ячейке вместе.
            </p>
          </div>

          <!-- Stock by product in this cell -->
          <div v-if="cellStocks.length" class="space-y-2">
            <div class="text-sm font-semibold text-gray-600 mb-2">Содержимое:</div>
            <div
              v-for="s in cellStocks" :key="s.product_id"
              class="flex justify-between items-center bg-gray-50 rounded-lg px-3 py-2 text-sm"
            >
              <div>
                <div class="font-mono font-semibold text-blue-700">{{ s.product?.sku }}</div>
                <div class="text-xs text-gray-400 truncate max-w-[160px]">{{ s.product?.name }}</div>
              </div>
              <div class="font-bold text-gray-700">{{ s.quantity }} <span class="text-gray-400 font-normal text-xs">ед.</span></div>
            </div>
          </div>
          <div v-else class="text-center text-gray-300 text-sm py-4">Ячейка пуста</div>
        </div>
      </div>

    </div>
  </ManagerLayout>
</template>

<script setup>
import { ref, computed, watch, onMounted } from 'vue'
import ManagerLayout from '@/layouts/ManagerLayout.vue'
import { cellsApi, warehouseApi } from '@/api'

const loading      = ref(true)
const allCells     = ref([])
const allStocks    = ref([])
const selectedZone = ref('')
const selectedCell = ref(null)

// ── Derived dimensions ────────────────────────────────────────────────────────
const zones = computed(() => [...new Set(allCells.value.map(c => c.zone))].sort())
const racks = computed(() => {
  const r = allCells.value
    .filter(c => c.zone === selectedZone.value)
    .map(c => c.rack)
  return [...new Set(r)].sort((a, b) => a - b)
})
const zoneCells = computed(() => allCells.value.filter(c => c.zone === selectedZone.value))

// ── Stats ─────────────────────────────────────────────────────────────────────
const emptyCells    = computed(() => zoneCells.value.filter(c => c.current_stock === 0).length)
const occupiedCells = computed(() => zoneCells.value.filter(c => c.current_stock > 0).length)
const avgFill       = computed(() => {
  if (!zoneCells.value.length) return 0
  const total = zoneCells.value.reduce((s, c) => s + fillPct(c), 0)
  return total / zoneCells.value.length
})

// Stocks в выбранной ячейке
const cellStocks = computed(() => {
  if (!selectedCell.value) return []
  return allStocks.value.filter(s => s.cell_id === selectedCell.value.id)
})

// ── Helpers ───────────────────────────────────────────────────────────────────
function getCell(rack, shelf, pos) {
  return zoneCells.value.find(c => c.rack === rack && c.shelf === shelf && c.position === pos) ?? null
}

function rackShelves(rack) {
  const s = zoneCells.value.filter(c => c.rack === rack).map(c => c.shelf)
  return [...new Set(s)].sort((a, b) => a - b)
}

function rackPositions(rack) {
  const p = zoneCells.value.filter(c => c.rack === rack).map(c => c.position)
  return [...new Set(p)].sort((a, b) => a - b)
}

function rackCellsCount(rack) {
  return zoneCells.value.filter(c => c.rack === rack).length
}

function fillPct(cell) {
  if (!cell || cell.max_capacity === 0) return 0
  return (cell.current_stock / cell.max_capacity) * 100
}

function cellClass(cell) {
  if (!cell) return 'bg-transparent border-transparent cursor-default'
  const pct = fillPct(cell)
  if (pct === 0)    return 'bg-gray-50 border-gray-200 hover:border-gray-300 text-gray-400'
  if (pct > 100)    return 'bg-red-100 border-red-300 text-red-700'
  if (pct > 80)     return 'bg-blue-500 border-blue-600 text-white'
  if (pct > 50)     return 'bg-blue-300 border-blue-400 text-blue-900'
  return               'bg-blue-100 border-blue-200 text-blue-800'
}

function selectCell(cell) {
  if (!cell) return
  selectedCell.value = cell
}

// ── Watch zone → reset rack ───────────────────────────────────────────────────
watch(selectedZone, () => {
  selectedCell.value = null
})

// ── Load ──────────────────────────────────────────────────────────────────────
async function load() {
  loading.value = true
  try {
    const [cellsRes, stocksRes] = await Promise.all([
      cellsApi.list(),
      warehouseApi.stocks(),
    ])

    // Обогащаем ячейки данными об остатках по продуктам
    const stocksByCell = {}
    stocksRes.data.forEach(s => {
      if (!stocksByCell[s.cell_id]) stocksByCell[s.cell_id] = []
      stocksByCell[s.cell_id].push(s)
    })

    allCells.value  = cellsRes.data
    allStocks.value = stocksRes.data

    // Устанавливаем зону по умолчанию
    if (zones.value.length && !selectedZone.value) {
      selectedZone.value = zones.value[0]
    }
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>
