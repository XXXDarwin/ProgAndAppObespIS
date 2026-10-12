<template>
  <ManagerLayout>
    <div class="space-y-6">

      <!-- KPI Cards -->
      <div class="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <KpiCard label="Видов товаров"  :value="stats.products"    color="blue"   :loading="loading" />
        <KpiCard label="Ед. на складе"  :value="stats.totalStock"  color="green"  :loading="loading" />
        <KpiCard :label="kpiOrdersLabel" :value="stats.ordersInPeriod" color="yellow" :loading="loading" />
        <KpiCard label="Ячеек занято"   :value="stats.cellsUsed"   color="purple" :loading="loading" />
      </div>

      <!-- График заказов слева; категории и сводка справа -->
      <div class="grid grid-cols-1 lg:grid-cols-2 gap-4 items-stretch">
        <div class="card flex flex-col">
          <div class="flex flex-wrap items-center justify-between gap-3 mb-5">
            <h3 class="font-semibold text-gray-700">Активность заказов</h3>
            <div class="flex gap-1 bg-gray-100 rounded-lg p-1">
              <button
                v-for="p in periods" :key="p.key"
                @click="setPeriod(p.key)"
                class="px-4 py-1.5 text-sm font-medium rounded-md transition-all"
                :class="period === p.key
                  ? 'bg-white text-blue-700 shadow-sm'
                  : 'text-gray-500 hover:text-gray-700'"
              >{{ p.label }}</button>
            </div>
          </div>

          <div v-if="chartLoading" class="skeleton flex-1 min-h-[220px] w-full"></div>
          <Bar
            v-else-if="ordersChart.labels.length"
            :data="ordersChart"
            :options="barOptions"
            class="flex-1 min-h-[220px] max-h-80"
          />
          <div v-else class="flex-1 flex items-center justify-center text-gray-400 text-sm py-16">
            Нет данных за период
          </div>
        </div>

        <div class="flex flex-col gap-4">
          <div class="card">
            <h3 class="font-semibold text-gray-700 mb-1">Товары по категориям</h3>
            <p class="text-xs text-gray-500 mb-4">Суммарный остаток по всем товарам в каждой категории</p>
            <div v-if="loading" class="skeleton h-48 w-full"></div>
            <Doughnut
              v-else-if="categoryChart.labels.length"
              :data="categoryChart"
              :options="doughnutOptions"
              class="max-h-56"
            />
            <div v-else class="text-center text-gray-400 text-sm py-12">Нет данных по остаткам</div>
          </div>

          <div class="card flex flex-col justify-between flex-1">
            <h3 class="font-semibold text-gray-700 mb-4">Сводка за период</h3>
            <div v-if="chartLoading" class="space-y-3">
              <div v-for="i in 3" :key="i" class="skeleton h-10 w-full"></div>
            </div>
            <div v-else class="space-y-3">
              <div class="flex justify-between items-center bg-blue-50 rounded-lg px-4 py-3">
                <span class="text-sm text-blue-700 font-medium">Приёмок</span>
                <span class="text-xl font-bold text-blue-700">{{ periodSummary.arrivals }}</span>
              </div>
              <div class="flex justify-between items-center bg-green-50 rounded-lg px-4 py-3">
                <span class="text-sm text-green-700 font-medium">Расходов</span>
                <span class="text-xl font-bold text-green-700">{{ periodSummary.consumptions }}</span>
              </div>
              <div class="flex justify-between items-center bg-yellow-50 rounded-lg px-4 py-3">
                <span class="text-sm text-yellow-700 font-medium">Инвентаризаций</span>
                <span class="text-xl font-bold text-yellow-700">{{ periodSummary.inventories }}</span>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Recent orders -->
      <div class="card">
        <h3 class="font-semibold text-gray-700 mb-4">Последние заказы</h3>
        <div v-if="loading" class="space-y-2">
          <div v-for="i in 4" :key="i" class="skeleton h-10 w-full"></div>
        </div>
        <table v-else-if="recentOrders.length" class="w-full text-sm">
          <thead>
            <tr class="text-left text-gray-400 border-b border-gray-100">
              <th class="pb-2 font-medium">№</th>
              <th class="pb-2 font-medium">Тип</th>
              <th class="pb-2 font-medium">Статус</th>
              <th class="pb-2 font-medium">Позиций</th>
              <th class="pb-2 font-medium">Дата</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-gray-50">
            <tr v-for="order in recentOrders" :key="order.id" class="hover:bg-gray-50">
              <td class="py-2.5 font-mono text-gray-500">#{{ order.id }}</td>
              <td class="py-2.5"><OrderTypeBadge :type="order.type" /></td>
              <td class="py-2.5"><OrderStatusBadge :status="order.status" /></td>
              <td class="py-2.5 text-gray-600">{{ order.items?.length ?? 0 }}</td>
              <td class="py-2.5 text-gray-500">{{ formatDate(order.created_at) }}</td>
            </tr>
          </tbody>
        </table>
        <div v-else class="text-center text-gray-400 text-sm py-8">Нет заказов</div>
      </div>

    </div>
  </ManagerLayout>
</template>

<script setup>
import { ref, computed, watch, onMounted } from 'vue'
import { Bar, Doughnut } from 'vue-chartjs'
import {
  Chart as ChartJS, ArcElement, Tooltip, Legend,
  CategoryScale, LinearScale, BarElement,
} from 'chart.js'
import ManagerLayout from '@/layouts/ManagerLayout.vue'
import KpiCard from '@/components/KpiCard.vue'
import OrderTypeBadge from '@/components/OrderTypeBadge.vue'
import OrderStatusBadge from '@/components/OrderStatusBadge.vue'
import { warehouseApi, productsApi } from '@/api'

ChartJS.register(ArcElement, Tooltip, Legend, CategoryScale, LinearScale, BarElement)

// ── State ─────────────────────────────────────────────────────────────────────
const loading     = ref(true)
const chartLoading = ref(false)
const period      = ref('year')   // 'week' | 'month' | 'year'

const allOrders  = ref([])
const allStocks  = ref([])
const allProducts = ref([])
const recentOrders = ref([])

const stats = ref({ products: 0, totalStock: 0, ordersInPeriod: 0, cellsUsed: 0 })
const ordersChart = ref({ labels: [], datasets: [] })
const categoryChart = ref({ labels: [], datasets: [] })
const periodSummary = ref({ arrivals: 0, consumptions: 0, inventories: 0 })

// ── Periods config ─────────────────────────────────────────────────────────────
const periods = [
  { key: 'week',  label: 'Неделя' },
  { key: 'month', label: 'Месяц'  },
  { key: 'year',  label: 'Год'    },
]

const kpiOrdersLabel = computed(() => ({
  week:  'Заказов за неделю',
  month: 'Заказов за месяц',
  year:  'Заказов за год',
}[period.value]))

// ── Chart options ─────────────────────────────────────────────────────────────
const barOptions = {
  responsive: true,
  plugins: { legend: { position: 'top' } },
  scales: { x: { grid: { display: false } }, y: { beginAtZero: true, ticks: { stepSize: 1 } } },
}
const CATEGORY_CHART_COLORS = [
  '#3B82F6', '#10B981', '#F59E0B', '#8B5CF6', '#EF4444',
  '#06B6D4', '#EC4899', '#84CC16', '#F97316', '#6366F1',
  '#14B8A6', '#A855F7', '#64748B',
]

const doughnutOptions = {
  responsive: true,
  maintainAspectRatio: true,
  plugins: {
    legend: { position: 'right' },
    tooltip: {
      callbacks: {
        label(ctx) {
          const value = ctx.parsed ?? 0
          const total = ctx.dataset.data.reduce((s, v) => s + v, 0)
          const pct = total ? ((value / total) * 100).toFixed(1) : 0
          return ` ${ctx.label}: ${value} ед. (${pct}%)`
        },
      },
    },
  },
}

function buildCategoryChart() {
  const productById = Object.fromEntries(allProducts.value.map(p => [p.id, p]))
  const byCategory = {}

  allStocks.value.forEach(s => {
    const product = productById[s.product_id]
    const name = product?.category?.name?.trim() || 'Без категории'
    byCategory[name] = (byCategory[name] || 0) + Number(s.quantity || 0)
  })

  const entries = Object.entries(byCategory)
    .filter(([, qty]) => qty > 0)
    .sort((a, b) => b[1] - a[1])

  categoryChart.value = {
    labels: entries.map(([name]) => name),
    datasets: [{
      data: entries.map(([, qty]) => qty),
      backgroundColor: entries.map((_, i) => CATEGORY_CHART_COLORS[i % CATEGORY_CHART_COLORS.length]),
    }],
  }
}

function formatDate(dt) {
  return new Date(dt).toLocaleDateString('ru-RU', {
    day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit',
  })
}

function toIsoDate(d) {
  const y = d.getFullYear()
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${y}-${m}-${day}`
}

// ── Period helpers ─────────────────────────────────────────────────────────────
function getPeriodStart(p) {
  const now = new Date()
  if (p === 'week')  { const d = new Date(now); d.setDate(d.getDate() - 6);   d.setHours(0,0,0,0); return d }
  if (p === 'month') { const d = new Date(now); d.setDate(d.getDate() - 29);  d.setHours(0,0,0,0); return d }
  if (p === 'year')  { const d = new Date(now); d.setDate(d.getDate() - 364); d.setHours(0,0,0,0); return d }
}

// Генерирует массив меток и bucket-функцию для группировки дат
function buildTimeline(p) {
  const now = new Date()

  if (p === 'week') {
    const labels = Array.from({ length: 7 }, (_, i) => {
      const d = new Date(); d.setDate(d.getDate() - (6 - i))
      return d.toLocaleDateString('ru-RU', { weekday: 'short', day: '2-digit' })
    })
    const bucket = (dt) => {
      const diff = Math.floor((now - new Date(dt)) / 86400000)
      return diff >= 0 && diff < 7 ? 6 - diff : -1
    }
    return { labels, bucket, n: 7 }
  }

  if (p === 'month') {
    // Последние 30 дней по 5-дневным блокам (6 блоков)
    const labels = Array.from({ length: 6 }, (_, i) => {
      const to = new Date(); to.setDate(to.getDate() - (5 - i) * 5)
      const from = new Date(to); from.setDate(from.getDate() - 4)
      return `${from.toLocaleDateString('ru-RU',{day:'2-digit',month:'2-digit'})}–${to.toLocaleDateString('ru-RU',{day:'2-digit',month:'2-digit'})}`
    })
    const bucket = (dt) => {
      const diff = Math.floor((now - new Date(dt)) / 86400000)
      if (diff < 0 || diff >= 30) return -1
      return 5 - Math.floor(diff / 5)
    }
    return { labels, bucket, n: 6 }
  }

  if (p === 'year') {
    const labels = Array.from({ length: 12 }, (_, i) => {
      const d = new Date(now.getFullYear(), now.getMonth() - (11 - i), 1)
      return d.toLocaleDateString('ru-RU', { month: 'short', year: '2-digit' })
    })
    const ranges = Array.from({ length: 12 }, (_, i) => {
      const start = new Date(now.getFullYear(), now.getMonth() - (11 - i), 1)
      const end = new Date(now.getFullYear(), now.getMonth() - (11 - i) + 1, 0, 23, 59, 59, 999)
      return { start, end }
    })
    const bucket = (dt) => {
      const d = new Date(dt)
      const idx = ranges.findIndex(r => d >= r.start && d <= r.end)
      return idx
    }
    return { labels, bucket, n: 12 }
  }
}

// ── Build chart from allOrders ─────────────────────────────────────────────────
function rebuildChart() {
  const start = getPeriodStart(period.value)
  const { labels, bucket, n } = buildTimeline(period.value)

  const ordersInPeriod = allOrders.value.filter(o => new Date(o.created_at) >= start)

  stats.value.ordersInPeriod = ordersInPeriod.length

  periodSummary.value = {
    arrivals:     ordersInPeriod.filter(o => o.type === 'ARRIVAL').length,
    consumptions: ordersInPeriod.filter(o => o.type === 'CONSUMPTION').length,
    inventories:  ordersInPeriod.filter(o => o.type === 'INVENTORY').length,
  }

  const arrivals     = new Array(n).fill(0)
  const consumptions = new Array(n).fill(0)
  const inventories  = new Array(n).fill(0)

  ordersInPeriod.forEach(o => {
    const b = bucket(o.created_at)
    if (b < 0) return
    if (o.type === 'ARRIVAL')     arrivals[b]++
    if (o.type === 'CONSUMPTION') consumptions[b]++
    if (o.type === 'INVENTORY')   inventories[b]++
  })

  ordersChart.value = {
    labels,
    datasets: [
      { label: 'Приёмка',        data: arrivals,     backgroundColor: '#3B82F6' },
      { label: 'Расход',         data: consumptions, backgroundColor: '#10B981' },
      { label: 'Инвентаризация', data: inventories,  backgroundColor: '#F59E0B' },
    ],
  }
}

async function fetchOrdersForPeriod() {
  chartLoading.value = true
  try {
    const start = getPeriodStart(period.value)
    const { data } = await warehouseApi.orders({
      limit: 5000,
      date_from: toIsoDate(start),
    })
    allOrders.value = data
    recentOrders.value = data.slice(0, 8)
    rebuildChart()
  } finally {
    chartLoading.value = false
  }
}

function setPeriod(p) {
  period.value = p
  fetchOrdersForPeriod()
}

// ── Load data ─────────────────────────────────────────────────────────────────
onMounted(async () => {
  try {
    const [stocksRes, productsRes] = await Promise.all([
      warehouseApi.stocks(),
      productsApi.list(),
    ])

    allStocks.value    = stocksRes.data
    allProducts.value  = productsRes.data

    stats.value.products   = allProducts.value.length
    stats.value.totalStock = allStocks.value.reduce((s, r) => s + r.quantity, 0)
    stats.value.cellsUsed  = new Set(allStocks.value.map(s => s.cell_id)).size

    buildCategoryChart()
    await fetchOrdersForPeriod()
  } finally { loading.value = false }
})
</script>
