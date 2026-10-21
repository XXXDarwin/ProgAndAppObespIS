<script setup>
import { computed } from 'vue'
import { Line } from 'vue-chartjs'
import {
  Chart as ChartJS, LineElement, PointElement, LinearScale, CategoryScale, Tooltip, Legend,
} from 'chart.js'
import { NORMS, STATUS_STYLE } from './config'

ChartJS.register(LineElement, PointElement, LinearScale, CategoryScale, Tooltip, Legend)

const props = defineProps({
  status: { type: String, default: null },
  points: { type: Array, default: () => [] },
})

const last = computed(() => props.points.at(-1) ?? null)
const st = computed(() => STATUS_STYLE[props.status] ?? { label: 'Нет данных', cls: 'bg-gray-100 text-gray-600' })

const data = computed(() => ({
  labels: props.points.map(p => p.label),
  datasets: [
    { label: 'Температура, °C', data: props.points.map(p => p.temperature),
      borderColor: '#2563eb', backgroundColor: '#2563eb', pointRadius: 1.5, tension: 0.25 },
    { label: 'Норма (мин)', data: props.points.map(() => NORMS.tMin),
      borderColor: '#9ca3af', borderDash: [6, 4], pointRadius: 0 },
    { label: 'Норма (макс)', data: props.points.map(() => NORMS.tMax),
      borderColor: '#9ca3af', borderDash: [6, 4], pointRadius: 0 },
  ],
}))

const options = {
  responsive: true,
  maintainAspectRatio: false,
  animation: false,
  plugins: { legend: { position: 'bottom', labels: { boxWidth: 12 } } },
  scales: { x: { ticks: { maxTicksLimit: 8 } } },
}
</script>

<template>
  <section class="bg-white border border-gray-200 rounded-xl p-4">
    <div class="flex items-center justify-between mb-3">
      <h3 class="font-semibold text-gray-800">Микроклимат</h3>
      <span class="text-xs font-medium px-2 py-1 rounded-full" :class="st.cls">{{ st.label }}</span>
    </div>

    <div class="grid grid-cols-2 gap-3 mb-4">
      <div class="rounded-lg bg-gray-50 p-3">
        <div class="text-xs text-gray-500">Температура (последнее измерение)</div>
        <div class="text-2xl font-semibold text-gray-900">{{ last ? last.temperature + ' °C' : '—' }}</div>
        <div class="text-xs text-gray-400">норма {{ NORMS.tMin }}–{{ NORMS.tMax }} °C</div>
      </div>
      <div class="rounded-lg bg-gray-50 p-3">
        <div class="text-xs text-gray-500">Влажность (последнее измерение)</div>
        <div class="text-2xl font-semibold text-gray-900">{{ last ? last.humidity + ' %' : '—' }}</div>
        <div class="text-xs text-gray-400">норма {{ NORMS.hMin }}–{{ NORMS.hMax }} %</div>
      </div>
    </div>

    <div class="h-64">
      <Line v-if="points.length" :data="data" :options="options" />
      <div v-else class="h-full flex items-center justify-center text-sm text-gray-400">
        Нет измерений. Запустите эмулятор.
      </div>
    </div>
  </section>
</template>