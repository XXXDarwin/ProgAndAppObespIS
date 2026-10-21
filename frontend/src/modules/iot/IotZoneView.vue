<script setup>
import { computed } from 'vue'
import { useIotData } from './useIotData'
import { fmtTime } from './adapters'
import { CHART_POINTS } from './config'
import ClimatePanel from './ClimatePanel.vue'
import ShelvesPanel from './ShelvesPanel.vue'
import AlertsPanel from './AlertsPanel.vue'

// iotZone: код зоны в IoT-сервере (связь WMS-зоны C с зоной IoT, без переименования).
const props = defineProps({
  iotZone: { type: String, default: 'A' },
  title: { type: String, default: 'Защищённая зона: IoT-мониторинг' },
})

const { statuses, shelves, alerts, telemetry, online, loading, updatedAt, reload } = useIotData()

const zoneShelves = computed(() => shelves.value.filter(s => s.zone === props.iotZone))

const zoneAlerts = computed(() => {
  const ids = new Set(zoneShelves.value.map(s => s.shelf_id))
  return alerts.value.filter(a => a.source === props.iotZone || ids.has(a.source))
})

// Телеметрия приходит от новых к старым: разворачиваем для графика.
const points = computed(() =>
  telemetry.value
    .filter(m => m.kind === 'climate' && m.zone === props.iotZone)
    .slice(0, CHART_POINTS)
    .reverse()
    .map(m => ({
      label: fmtTime(m.timestamp ?? m.ts),
      temperature: m.temperature,
      humidity: m.humidity,
    })),
)

const lastPacket = computed(() => {
  const m = telemetry.value[0]
  return m ? fmtTime(m.timestamp ?? m.ts) : '—'
})
</script>

<template>
  <div class="space-y-4">
    <div class="flex items-center justify-between bg-white border border-gray-200 rounded-xl p-4">
      <div>
        <h2 class="font-semibold text-gray-900">{{ title }}</h2>
        <p class="text-xs text-gray-500">
          Зона IoT: {{ iotZone }} · последний пакет: {{ lastPacket }}
          <span v-if="updatedAt"> · обновлено {{ updatedAt.toLocaleTimeString('ru-RU') }}</span>
        </p>
      </div>
      <div class="flex items-center gap-3">
        <span class="flex items-center gap-1.5 text-xs font-medium"
              :class="online ? 'text-green-700' : 'text-red-600'">
          <span class="w-2 h-2 rounded-full" :class="online ? 'bg-green-500' : 'bg-red-500'"></span>
          {{ online ? 'IoT-сервер на связи' : 'Нет связи с IoT-сервером' }}
        </span>
        <button class="px-3 py-1.5 text-sm rounded-lg bg-gray-100 hover:bg-gray-200" @click="reload">Обновить</button>
      </div>
    </div>

    <div v-if="loading" class="text-sm text-gray-400 p-6 text-center">Загрузка...</div>
    <template v-else>
      <div class="grid grid-cols-1 xl:grid-cols-2 gap-4">
        <ClimatePanel :status="statuses[iotZone]" :points="points" />
        <AlertsPanel :alerts="zoneAlerts" />
      </div>
      <ShelvesPanel :shelves="zoneShelves" />
    </template>
  </div>
</template>