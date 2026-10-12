<template>
  <div class="card flex items-center gap-4">
    <div class="w-10 h-10 rounded-lg shrink-0" :class="accentClass"></div>
    <div class="flex-1 min-w-0">
      <div class="text-xs text-gray-400 font-medium uppercase tracking-wide">{{ label }}</div>
      <div v-if="loading" class="skeleton h-7 w-16 mt-1"></div>
      <div v-else class="text-2xl font-bold" :class="colorClass">{{ value }}</div>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
const props = defineProps({ label: String, value: [Number, String], color: String, loading: Boolean })
const colorClass = computed(() => ({
  blue: 'text-blue-700', green: 'text-green-700', yellow: 'text-yellow-700', purple: 'text-purple-700', red: 'text-red-700'
}[props.color] ?? 'text-gray-800'))
const accentClass = computed(() => ({
  blue: 'bg-blue-100', green: 'bg-green-100', yellow: 'bg-yellow-100', purple: 'bg-purple-100', red: 'bg-red-100'
}[props.color] ?? 'bg-gray-100'))
</script>
