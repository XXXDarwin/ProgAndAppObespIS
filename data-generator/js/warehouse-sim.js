/**
 * Согласованная генерация полного склада: товары, ячейки, остатки, история спроса.
 */

import { DEMO_CATEGORIES } from './catalog.js'
import { generateProducts } from './generators.js'
import {
  buildDemandParams,
  generateMultiSkuHistory,
  formatDateISO,
  DEFAULT_WEEKDAY,
} from './history.js'
import { buildOrderSchedule } from './order-schedule.js'

function yieldToMain() {
  return new Promise(resolve => setTimeout(resolve, 0))
}

export function enumerateCellAddresses(cellsConfig) {
  const { zones, racks_per_zone, shelves_per_rack, positions_per_shelf } = cellsConfig
  const list = []
  for (const zone of zones) {
    for (let rack = 1; rack <= racks_per_zone; rack++) {
      for (let shelf = 1; shelf <= shelves_per_rack; shelf++) {
        for (let pos = 1; pos <= positions_per_shelf; pos++) {
          list.push(`${zone}${rack}-${shelf}-${pos}`)
        }
      }
    }
  }
  return list
}

export function parseCellAddress(addr) {
  const m = /^([A-Z]{1,8})(\d+)-(\d+)-(\d+)$/i.exec(String(addr || '').trim())
  if (!m) return null
  return {
    zone: m[1].toUpperCase(),
    rack: Number(m[2]),
    shelf: Number(m[3]),
    position: Number(m[4]),
  }
}

/** Распределение SKU по ячейкам с обходом всех зон (A → B → C …). */
export function assignSkuToCells(products, addresses) {
  const map = {}
  if (!addresses.length) return map
  const byZone = {}
  for (const addr of addresses) {
    const z = parseCellAddress(addr)?.zone || '?'
    if (!byZone[z]) byZone[z] = []
    byZone[z].push(addr)
  }
  const flat = Object.keys(byZone).sort().flatMap(z => byZone[z])
  for (let i = 0; i < products.length; i++) {
    map[products[i].sku] = flat[i % flat.length]
  }
  return map
}

function randomInt(min, max) {
  return min + Math.floor(Math.random() * (max - min + 1))
}

/**
 * @param {object} opts
 * @param {(p: { percent: number, message: string }) => void} [onProgress]
 */
export async function generateFullWarehouse(opts, onProgress) {
  const report = (percent, message) => onProgress?.({ percent, message })

  const productCount = opts.productCount ?? 50
  const zones = (opts.zones || 'A,B,C').split(',').map(z => z.trim().toUpperCase()).filter(Boolean)
  const racks = opts.racksPerZone ?? 4
  const shelves = opts.shelvesPerRack ?? 4
  const positions = opts.positionsPerShelf ?? 4
  const maxCapacity = opts.maxCapacity ?? 200
  const historyDays = opts.historyDays ?? 365
  const stockMin = opts.stockMin ?? 20
  const stockMax = opts.stockMax ?? 120
  const historySkuMode = opts.historySkuMode ?? 'all' // all | sample
  const historySampleSize = opts.historySampleSize ?? 30
  const presetName = opts.historyPreset ?? 'stable'

  report(5, 'Генерация товаров…')
  await yieldToMain()

  const products = generateProducts({
    count: productCount,
    skuPrefix: opts.skuPrefix || 'GEN',
    mode: opts.productMode || 'random',
    startIndex: opts.productStart ?? 1,
  })

  report(12, 'Формирование сетки ячеек…')
  await yieldToMain()

  const cells = {
    zones: zones.length ? zones : ['A', 'B', 'C'],
    racks_per_zone: racks,
    shelves_per_rack: shelves,
    positions_per_shelf: positions,
    max_capacity: maxCapacity,
  }

  const addresses = enumerateCellAddresses(cells)
  const skuToCell = assignSkuToCells(products, addresses)

  const end = new Date()
  const start = new Date(end)
  start.setDate(start.getDate() - historyDays + 1)

  const skuCount = historySkuMode === 'all'
    ? products.length
    : Math.min(historySampleSize, products.length)

  const historyParams = opts.demandParams
    ? { ...opts.demandParams, startDate: start, days: historyDays }
    : buildDemandParams({
      preset: presetName,
      startDate: start,
      days: historyDays,
      weekdayFactors: opts.weekdayFactors || DEFAULT_WEEKDAY,
    })

  report(18, `История спроса: ${skuCount} SKU × ${historyDays} дн.…`)
  const { records } = await generateMultiSkuHistory(products, historyParams, skuCount, p => {
    const pct = 18 + Math.round((p.current / p.total) * 72)
    report(pct, p.message)
  })

  report(88, 'Планирование приёмок, расходов и инвентаризаций…')
  await yieldToMain()

  const arrivalsPerMonth = opts.arrivalsPerMonth ?? 8
  const consumptionsPerMonth = opts.consumptionsPerMonth ?? 12
  const movesPerMonth = opts.movesPerMonth ?? 6
  const { timed_orders, stats: orderStats } = buildOrderSchedule({
    startDate: formatDateISO(start),
    days: historyDays,
    arrivalsPerMonth,
    consumptionsPerMonth,
    movesPerMonth,
    products,
    skuToCell,
    stockMin,
    stockMax,
    demandRecords: records,
    parseCellAddress,
    cellAddresses: addresses,
    maxItemsPerArrival: opts.maxItemsPerArrival ?? 18,
    minItemsPerArrival: opts.minItemsPerArrival ?? 4,
    maxItemsPerConsumption: opts.maxItemsPerConsumption ?? 10,
    maxCapacity,
  })

  report(95, 'Сборка данных для загрузки…')
  await yieldToMain()

  const bootstrapPayload = {
    comment: opts.comment || 'Полная генерация склада (data-generator)',
    cells,
    products: products.map(p => ({
      sku: p.sku,
      name: p.name,
      unit: p.unit || 'шт',
      category: p.category || DEMO_CATEGORIES[0],
      weight: p.weight,
      description: p.description,
    })),
    skip_existing_products: opts.skipDuplicates !== false,
    initial_stock: [],
    timed_orders,
    run_ml_training: !!opts.runMlTraining,
  }

  const cellCount = addresses.length
  const historySkus = new Set(records.map(r => r.sku)).size

  report(100, 'Генерация завершена')

  return {
    products,
    cells,
    addresses,
    records,
    bootstrapPayload,
    stats: {
      products: products.length,
      categories: new Set(products.map(p => p.category)).size,
      cells: cellCount,
      arrivals: orderStats.arrivals,
      consumptions: orderStats.consumptions,
      moves: orderStats.moves,
      inventories: orderStats.inventories,
      movesPerMonth: orderStats.movesPerMonth,
      historyRecords: records.length,
      historySkus,
      historyDays,
      arrivalsPerMonth: orderStats.arrivalsPerMonth,
      consumptionsPerMonth: orderStats.consumptionsPerMonth,
      inventoriesPerMonth: orderStats.inventoriesPerMonth,
      periodFrom: formatDateISO(start),
      periodTo: formatDateISO(end),
    },
  }
}
