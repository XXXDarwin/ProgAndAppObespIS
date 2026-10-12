import {
  DEMO_CATEGORIES,
  DEMO_PRODUCTS,
  PRODUCT_NAMES,
  UNITS,
  randomCell,
  randomInt,
} from './catalog.js'

export function generateProducts({
  count,
  skuPrefix,
  mode,
  startIndex,
}) {
  if (mode === 'demo') {
    return DEMO_PRODUCTS.slice(0, Math.min(count, DEMO_PRODUCTS.length)).map(p => ({ ...p }))
  }

  const items = []
  for (let i = 0; i < count; i++) {
    const n = startIndex + i
    const sku = `${skuPrefix}-${String(n).padStart(3, '0')}`
    const category = DEMO_CATEGORIES[i % DEMO_CATEGORIES.length]
    const baseName = PRODUCT_NAMES[i % PRODUCT_NAMES.length]
    items.push({
      sku,
      name: `${baseName} ${sku}`,
      unit: UNITS[i % UNITS.length],
      category,
      weight: Math.round((0.1 + Math.random() * 5) * 100) / 100,
      description: `Сгенерированный товар ${sku}`,
    })
  }
  return items
}

function pickSkus(catalog, lineCount, allowRepeat) {
  if (!catalog.length) return []
  const picked = []
  const pool = [...catalog]
  for (let i = 0; i < lineCount; i++) {
    if (!pool.length) {
      if (!allowRepeat) break
      pool.push(...catalog)
    }
    const idx = Math.floor(Math.random() * pool.length)
    picked.push(pool[idx])
    if (!allowRepeat) pool.splice(idx, 1)
  }
  return picked
}

export function generateOrderLines(catalog, {
  lineCount,
  qtyMin,
  qtyMax,
  withCells,
  allowRepeatSku,
}) {
  const sources = pickSkus(catalog, lineCount, allowRepeatSku)
  return sources.map(src => {
    const row = {
      sku: src.sku,
      quantity: randomInt(qtyMin, qtyMax),
    }
    if (withCells) row.cell = randomCell()
    return row
  })
}

export function productsToImportJson(items, skipDuplicates = true) {
  return { skip_duplicates: skipDuplicates, items }
}

export function orderToImportJson(items, comment, type) {
  const payload = {
    comment: comment || (type === 'arrival' ? 'Сгенерированная приёмка' : 'Сгенерированный расход'),
    items: items.map(({ sku, quantity, cell }) => {
      const line = { sku, quantity }
      if (cell) line.cell_address = cell
      return line
    }),
  }
  return payload
}
