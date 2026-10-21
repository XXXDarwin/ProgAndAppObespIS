// Нормы должны совпадать с iot_server/config.py (SEED). Меняются только вместе с серверным конфигом.
export const NORMS = { tMin: 18, tMax: 25, hMin: 40, hMax: 60 }

export const POLL_MS = 5000
export const CHART_POINTS = 60

export const STATUS_STYLE = {
  NORMAL: { label: 'Норма', cls: 'bg-green-100 text-green-700' },
  WARNING: { label: 'Предупреждение', cls: 'bg-amber-100 text-amber-700' },
  CRITICAL: { label: 'Критично', cls: 'bg-red-100 text-red-700' },
}

export const SEVERITY_STYLE = {
  WARNING: 'bg-amber-100 text-amber-700',
  CRITICAL: 'bg-red-100 text-red-700',
  HIGH: 'bg-red-100 text-red-700',
  MEDIUM: 'bg-blue-100 text-blue-700',
}