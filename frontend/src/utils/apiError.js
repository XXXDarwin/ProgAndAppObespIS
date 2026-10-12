export function parseApiDetail(err, fallback = 'Ошибка операции') {
  const detail = err?.response?.data?.detail
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) {
    return detail.map(item => (typeof item === 'string' ? item : item?.msg || JSON.stringify(item))).join('; ')
  }
  if (detail && typeof detail === 'object') return JSON.stringify(detail)
  return err?.message || fallback
}
