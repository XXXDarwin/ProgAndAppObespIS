export function downloadText(filename, text, mime = 'application/json') {
  const blob = new Blob([text], { type: mime })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}

export function downloadJson(filename, data) {
  downloadText(filename, JSON.stringify(data, null, 2), 'application/json')
}

export function rowsToCsv(rows, columns) {
  const header = columns.join(',')
  const lines = rows.map(row =>
    columns.map(col => {
      const v = row[col] ?? ''
      const s = String(v)
      return s.includes(',') || s.includes('"') ? `"${s.replace(/"/g, '""')}"` : s
    }).join(','),
  )
  return [header, ...lines].join('\n')
}

export function downloadCsv(filename, rows, columns) {
  const csv = '\uFEFF' + rowsToCsv(rows, columns)
  downloadText(filename, csv, 'text/csv;charset=utf-8')
}

export function downloadXlsx(filename, rows, columns, sheetName = 'Sheet1') {
  if (!window.XLSX) throw new Error('Библиотека XLSX не загружена')
  const data = [columns, ...rows.map(r => columns.map(c => r[c] ?? ''))]
  const ws = window.XLSX.utils.aoa_to_sheet(data)
  const wb = window.XLSX.utils.book_new()
  window.XLSX.utils.book_append_sheet(wb, ws, sheetName)
  window.XLSX.writeFile(wb, filename)
}
