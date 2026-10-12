<template>
  <div v-if="summary" class="space-y-3">
    <div class="grid grid-cols-2 sm:grid-cols-4 gap-3 text-sm">
      <div class="bg-red-50 rounded-lg px-3 py-2 border border-red-100">
        <div class="text-xs text-red-600">Потери (ед.)</div>
        <div class="text-xl font-bold text-red-700">{{ summary.total_loss_units }}</div>
      </div>
      <div class="bg-green-50 rounded-lg px-3 py-2 border border-green-100">
        <div class="text-xs text-green-600">Излишки (ед.)</div>
        <div class="text-xl font-bold text-green-700">{{ summary.total_surplus_units }}</div>
      </div>
      <div class="bg-gray-50 rounded-lg px-3 py-2 border border-gray-100">
        <div class="text-xs text-gray-500">Стеллажей</div>
        <div class="text-xl font-bold text-gray-800">{{ summary.tasks_completed }}/{{ summary.tasks_total }}</div>
      </div>
      <div class="bg-amber-50 rounded-lg px-3 py-2 border border-amber-100">
        <div class="text-xs text-amber-700">Расхождений</div>
        <div class="text-xl font-bold text-amber-800">{{ summary.discrepancies?.length ?? 0 }}</div>
      </div>
    </div>

    <div v-if="lossesOnly.length" class="overflow-x-auto">
      <table class="w-full text-sm">
        <thead>
          <tr class="text-left text-gray-400 border-b">
            <th class="pb-2 font-medium">Ячейка</th>
            <th class="pb-2 font-medium">SKU</th>
            <th class="pb-2 font-medium">Название</th>
            <th class="pb-2 font-medium text-right">Учёт</th>
            <th class="pb-2 font-medium text-right">Факт</th>
            <th class="pb-2 font-medium text-right">Потеря</th>
          </tr>
        </thead>
        <tbody class="divide-y divide-gray-50">
          <tr v-for="d in lossesOnly" :key="d.order_item_id" class="hover:bg-red-50/40">
            <td class="py-2 font-mono text-gray-700">{{ d.cell_address }}</td>
            <td class="py-2 font-mono text-blue-700">{{ d.product_sku }}</td>
            <td class="py-2 text-gray-600 max-w-[180px] truncate" :title="d.product_name">{{ d.product_name }}</td>
            <td class="py-2 text-right">{{ d.expected }}</td>
            <td class="py-2 text-right">{{ d.fact }}</td>
            <td class="py-2 text-right font-semibold text-red-700">−{{ -d.delta }}</td>
          </tr>
        </tbody>
      </table>
    </div>
    <p v-else-if="!summary.discrepancies?.length" class="text-sm text-gray-500 text-center py-4">
      Расхождений нет — учёт совпал с фактом.
    </p>
    <p v-else class="text-sm text-gray-500 text-center py-2">Потерь нет. Есть только излишки.</p>

    <details v-if="surplusOnly.length" class="text-sm">
      <summary class="cursor-pointer text-gray-600 hover:text-gray-800">Излишки ({{ surplusOnly.length }})</summary>
      <table class="w-full text-sm mt-2">
        <tbody class="divide-y divide-gray-50">
          <tr v-for="d in surplusOnly" :key="'s-' + d.order_item_id">
            <td class="py-1.5 font-mono">{{ d.cell_address }}</td>
            <td class="py-1.5 font-mono text-blue-700">{{ d.product_sku }}</td>
            <td class="py-1.5 text-right text-green-700">+{{ d.delta }}</td>
          </tr>
        </tbody>
      </table>
    </details>
  </div>
  <div v-else-if="loading" class="text-sm text-gray-400 py-4">Загрузка...</div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  summary: { type: Object, default: null },
  loading: { type: Boolean, default: false },
})

const lossesOnly = computed(() =>
  (props.summary?.discrepancies || []).filter(d => d.kind === 'loss')
)
const surplusOnly = computed(() =>
  (props.summary?.discrepancies || []).filter(d => d.kind === 'surplus')
)
</script>
