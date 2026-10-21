import { ref, onMounted, onUnmounted } from 'vue'
import { fetchClimateStatus, fetchInventory, fetchAlerts, fetchTelemetry } from './api'
import { normStatuses, normShelves, normAlerts, normTelemetry } from './adapters'
import { POLL_MS } from './config'

export function useIotData() {
  const statuses = ref({})
  const shelves = ref([])
  const alerts = ref([])
  const telemetry = ref([])
  const online = ref(false)
  const loading = ref(true)
  const updatedAt = ref(null)
  let timer = null

  async function load() {
    const res = await Promise.allSettled([
      fetchClimateStatus(), fetchInventory(), fetchAlerts(), fetchTelemetry(),
    ])
    if (res[0].status === 'fulfilled') statuses.value = normStatuses(res[0].value)
    if (res[1].status === 'fulfilled') shelves.value = normShelves(res[1].value)
    if (res[2].status === 'fulfilled') alerts.value = normAlerts(res[2].value)
    if (res[3].status === 'fulfilled') telemetry.value = normTelemetry(res[3].value)
    online.value = res.some(r => r.status === 'fulfilled')
    if (online.value) updatedAt.value = new Date()
    loading.value = false
  }

  onMounted(() => {
    load()
    timer = setInterval(load, POLL_MS)
  })
  onUnmounted(() => clearInterval(timer))

  return { statuses, shelves, alerts, telemetry, online, loading, updatedAt, reload: load }
}