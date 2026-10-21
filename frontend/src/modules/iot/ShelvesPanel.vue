<script setup>
defineProps({ shelves: { type: Array, default: () => [] } })
</script>

<template>
  <section class="bg-white border border-gray-200 rounded-xl p-4">
    <h3 class="font-semibold text-gray-800 mb-3">Умные полки</h3>
    <div class="overflow-x-auto">
      <table class="w-full text-sm">
        <thead>
          <tr class="text-left text-xs text-gray-500 border-b border-gray-200">
            <th class="py-2 pr-3">Полка</th>
            <th class="py-2 pr-3">Товар</th>
            <th class="py-2 pr-3 text-right">Остаток, шт</th>
            <th class="py-2 pr-3 text-right">Вес, г</th>
            <th class="py-2 text-right">Масса ед., г</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="s in shelves" :key="s.shelf_id" class="border-b border-gray-100">
            <td class="py-2 pr-3 font-medium text-gray-800">{{ s.shelf_id }}</td>
            <td class="py-2 pr-3 text-gray-600">{{ s.product_name ?? '—' }}</td>
            <td class="py-2 pr-3 text-right font-semibold text-blue-700">{{ s.quantity }}</td>
            <td class="py-2 pr-3 text-right text-gray-600">{{ s.last_weight_g ?? '—' }}</td>
            <td class="py-2 text-right text-gray-600">{{ s.unit_weight_g ?? '—' }}</td>
          </tr>
          <tr v-if="!shelves.length">
            <td colspan="5" class="py-6 text-center text-gray-400">В этой зоне нет умных полок</td>
          </tr>
        </tbody>
      </table>
    </div>
  </section>
</template>