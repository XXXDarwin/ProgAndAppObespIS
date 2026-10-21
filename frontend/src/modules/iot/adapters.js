// Единственное место, которое знает имена полей ответов IoT-API.
const asList = d => (Array.isArray(d) ? d : d?.items ?? d?.data ?? [])

export function normStatuses(d) {
  if (Array.isArray(d)) {
    return Object.fromEntries(d.map(x => [x.zone, x.status ?? x.level]))
  }
  const out = {}
  for (const [zone, v] of Object.entries(d ?? {})) {
    out[zone] = typeof v === 'string' ? v : v?.status ?? v?.level
  }
  return out
}

export const normShelves = d => asList(d)
export const normAlerts = d => asList(d)
export const normTelemetry = d => asList(d)

export function fmtTime(ts) {
  if (!ts) return '—'
  const d = new Date(ts)
  return isNaN(d) ? String(ts) : d.toLocaleTimeString('ru-RU')
}

export function fmtDateTime(ts) {
  if (!ts) return '—'
  const d = new Date(ts)
  return isNaN(d) ? String(ts) : d.toLocaleString('ru-RU')
}