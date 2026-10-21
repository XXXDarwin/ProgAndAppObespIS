<script setup>
import { SEVERITY_STYLE } from './config'
import { fmtDateTime } from './adapters'
defineProps({ alerts: { type: Array, default: () => [] } })
</script>

<template>
  <section class="bg-white border border-gray-200 rounded-xl p-4">
    <h3 class="font-semibold text-gray-800 mb-3">Журнал предупреждений</h3>
    <ul class="space-y-2 max-h-80 overflow-y-auto">
      <li v-for="a in alerts" :key="a.id ?? a.created + a.type"
          class="rounded-lg border border-gray-100 bg-gray-50 p-3">
        <div class="flex items-center justify-between gap-2">
          <span class="text-sm font-medium text-gray-800">{{ a.type }}</span>
          <span class="text-xs px-2 py-0.5 rounded-full"
                :class="SEVERITY_STYLE[a.severity] ?? 'bg-gray-100 text-gray-600'">{{ a.severity }}</span>
        </div>
        <div class="text-xs text-gray-500 mt-1">{{ a.source }} · {{ fmtDateTime(a.created) }}</div>
        <div v-if="a.details" class="text-sm text-gray-700 mt-1">{{ a.details }}</div>
      </li>
      <li v-if="!alerts.length" class="py-6 text-center text-sm text-gray-400">Предупреждений нет</li>
    </ul>
  </section>
</template>