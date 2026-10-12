/**
 * Планирование приёмок и расходов: в каждом месяце есть оба типа операций.
 * Внутри месяца приёмки чаще в первой половине, расходы — во второй (с перекрытием).
 */

import { formatDateISO, parseDateInput } from './history.js'

function addDays(base, offset) {
  const d = new Date(base)
  d.setDate(d.getDate() + offset)
  return formatDateISO(d)
}

/** Случайное целое вокруг среднего (±40%). */
export function varyAround(mean, min = 1) {
  const spread = Math.max(1, Math.round(mean * 0.4))
  const v = mean + Math.floor((Math.random() * 2 - 1) * spread)
  return Math.max(min, v)
}

function sampleDatesInWindow(startDate, dayFrom, dayTo, count) {
  const span = Math.max(0, dayTo - dayFrom)
  if (span <= 0 || count <= 0) return []
  const want = Math.min(count, span + 1)
  const picked = new Set()
  let guard = 0
  while (picked.size < want && guard < want * 50) {
    guard++
    const off = dayFrom + Math.floor(Math.random() * (span + 1))
    picked.add(addDays(startDate, off))
  }
  return [...picked].sort()
}

function groupRecordsByDate(records) {
  const map = {}
  for (const r of records) {
    if (!map[r.date]) map[r.date] = []
    map[r.date].push(r)
  }
  return map
}

function pickRandomProducts(products, count) {
  const pool = [...products]
  const out = []
  const n = Math.min(count, pool.length)
  while (out.length < n && pool.length) {
    const i = Math.floor(Math.random() * pool.length)
    out.push(pool.splice(i, 1)[0])
  }
  return out
}

function randomInt(min, max) {
  return min + Math.floor(Math.random() * (max - min + 1))
}

/** Уменьшает учёт занятости ячеек после расхода (для планирования приёмок). */
function applyConsumptionToCellLoad(order, skuToCell, cellLoad) {
  for (const item of order.items) {
    const cell_address = skuToCell[item.sku]
    if (!cell_address) continue
    const used = cellLoad[cell_address] || 0
    cellLoad[cell_address] = Math.max(0, used - item.quantity)
  }
}

/** Остатки по ячейкам: address → { sku → qty } */
function initCellStock() {
  return {}
}

function applyArrivalToStock(order, cellStock) {
  for (const item of order.items) {
    const addr = item.cell_address
    if (!addr) continue
    if (!cellStock[addr]) cellStock[addr] = {}
    cellStock[addr][item.sku] = (cellStock[addr][item.sku] || 0) + item.quantity
  }
}

function applyConsumptionToStock(order, skuToCell, cellStock) {
  for (const item of order.items) {
    let left = item.quantity
    const primary = skuToCell[item.sku]
    const tryAddrs = primary
      ? [primary, ...Object.keys(cellStock).filter(a => a !== primary && cellStock[a]?.[item.sku])]
      : Object.keys(cellStock).filter(a => cellStock[a]?.[item.sku])
    for (const addr of tryAddrs) {
      if (left <= 0) break
      const have = cellStock[addr]?.[item.sku] || 0
      if (have <= 0) continue
      const take = Math.min(have, left)
      cellStock[addr][item.sku] = have - take
      if (cellStock[addr][item.sku] <= 0) delete cellStock[addr][item.sku]
      left -= take
    }
  }
}

function applyMoveToStock(order, cellStock) {
  const item = order.items[0]
  if (!item) return
  const from = item.cell_address
  const to = item.to_cell_address
  const sku = item.sku
  const qty = item.quantity
  if (!cellStock[from]?.[sku]) return
  cellStock[from][sku] -= qty
  if (cellStock[from][sku] <= 0) delete cellStock[from][sku]
  if (!cellStock[to]) cellStock[to] = {}
  cellStock[to][sku] = (cellStock[to][sku] || 0) + qty
}

function cellUsedQty(cellStock, addr) {
  const row = cellStock[addr]
  if (!row) return 0
  return Object.values(row).reduce((s, q) => s + q, 0)
}

function cellFreeCapacity(cellStock, addr, maxCapacity) {
  return Math.max(0, maxCapacity - cellUsedQty(cellStock, addr))
}

function cellsByZone(addresses, parseCellAddress) {
  const map = {}
  for (const addr of addresses) {
    const z = parseCellAddress?.(addr)?.zone || '?'
    if (!map[z]) map[z] = []
    map[z].push(addr)
  }
  return map
}

function zoneStockTotal(cellStock, zoneCells) {
  return zoneCells.reduce((sum, addr) => sum + cellUsedQty(cellStock, addr), 0)
}

function findMoveCandidate(cellStock, zoneCells) {
  let best = null
  for (const addr of zoneCells) {
    const row = cellStock[addr]
    if (!row) continue
    for (const [sku, qty] of Object.entries(row)) {
      if (qty >= 2 && (!best || qty > best.qty)) {
        best = { addr, sku, qty }
      }
    }
  }
  return best
}

function findTargetCell(cellStock, zoneCells, qty, maxCapacity, excludeAddr) {
  let best = null
  for (const addr of zoneCells) {
    if (addr === excludeAddr) continue
    const free = cellFreeCapacity(cellStock, addr, maxCapacity)
    if (free >= qty && (!best || free > best.free)) {
      best = { addr, free }
    }
  }
  return best?.addr || null
}

function planZoneMove(cellStock, byZone, zones, maxCapacity) {
  if (zones.length < 2) return null
  const totals = zones
    .map(z => ({ z, total: zoneStockTotal(cellStock, byZone[z]) }))
    .sort((a, b) => b.total - a.total)
  const donor = totals[0]
  const receiver = totals[totals.length - 1]
  if (donor.z === receiver.z || donor.total < 8) return null
  if (receiver.total >= donor.total * 0.9) return null

  const candidate = findMoveCandidate(cellStock, byZone[donor.z])
  if (!candidate) return null

  const gap = donor.total - receiver.total
  const moveQty = Math.max(
    1,
    Math.min(
      Math.floor(candidate.qty * 0.4),
      Math.floor(gap / 4),
      Math.max(1, Math.floor(candidate.qty - 1)),
    ),
  )
  const toAddr = findTargetCell(cellStock, byZone[receiver.z], moveQty, maxCapacity, candidate.addr)
  if (!toAddr) return null

  return {
    fromAddr: candidate.addr,
    toAddr,
    sku: candidate.sku,
    qty: moveQty,
  }
}

function buildMoveOrder(date, plan, parseCellAddress) {
  const fromParts = parseCellAddress?.(plan.fromAddr)
  const toParts = parseCellAddress?.(plan.toAddr)
  return {
    type: 'MOVE',
    date,
    comment: `Перемещение ${fromParts?.zone || '?'} → ${toParts?.zone || '?'}`,
    items: [{
      sku: plan.sku,
      quantity: plan.qty,
      cell_address: plan.fromAddr,
      to_cell_address: plan.toAddr,
      cell_zone: fromParts?.zone,
      cell_rack: fromParts?.rack,
      cell_shelf: fromParts?.shelf,
      cell_position: fromParts?.position,
      to_cell_zone: toParts?.zone,
      to_cell_rack: toParts?.rack,
      to_cell_shelf: toParts?.shelf,
      to_cell_position: toParts?.position,
    }],
  }
}

function buildArrivalOrder(date, products, skuToCell, stockMin, stockMax, opts, limits, cellLoad) {
  const maxCapacity = opts.maxCapacity ?? 200
  const nItems = randomInt(limits.min, Math.min(limits.max, products.length))
  const picked = pickRandomProducts(products, nItems)
  const items = []
  for (const p of picked) {
    const cell_address = skuToCell[p.sku]
    const used = cellLoad[cell_address] || 0
    const free = maxCapacity - used
    if (free <= 0) continue
    const qty = Math.min(randomInt(stockMin, stockMax), free)
    cellLoad[cell_address] = used + qty
    const parts = opts.parseCellAddress?.(cell_address)
    items.push({
      sku: p.sku,
      quantity: qty,
      cell_address,
      cell_zone: parts?.zone,
      cell_rack: parts?.rack,
      cell_shelf: parts?.shelf,
      cell_position: parts?.position,
    })
  }
  if (!items.length) return null
  return {
    type: 'ARRIVAL',
    date,
    comment: 'Приёмка (симуляция)',
    items,
  }
}

function buildConsumptionOrder(date, products, recordsByDate, allDemandDates, stockMin, maxItems) {
  let lines = recordsByDate[date]
  if (!lines?.length && allDemandDates.length) {
    let idx = allDemandDates.findIndex(d => d >= date)
    if (idx < 0) idx = allDemandDates.length - 1
    lines = recordsByDate[allDemandDates[idx]] || []
  }
  let items
  if (lines?.length) {
    const shuffled = [...lines].sort(() => Math.random() - 0.5)
    const take = shuffled.slice(0, Math.min(maxItems, shuffled.length))
    items = take.map(r => ({ sku: r.sku, quantity: r.quantity }))
  } else {
    const picked = pickRandomProducts(products, randomInt(2, maxItems))
    items = picked.map(p => ({
      sku: p.sku,
      quantity: randomInt(1, Math.max(3, Math.floor(stockMin / 3))),
    }))
  }
  if (!items.length) return null
  return {
    type: 'CONSUMPTION',
    date,
    comment: 'Расход (симуляция)',
    items,
  }
}

function buildInventoryOrder(date) {
  return {
    type: 'INVENTORY',
    date,
    comment: 'Инвентаризация (симуляция)',
    items: [],
  }
}

/**
 * @param {object} opts
 * @returns {{ timed_orders: object[], stats: object }}
 */
export function buildOrderSchedule(opts) {
  const startDate = parseDateInput(opts.startDate)
  const days = opts.days ?? 365
  const arrivalsPerMonth = Math.max(1, opts.arrivalsPerMonth ?? 8)
  const consumptionsPerMonth = Math.max(1, opts.consumptionsPerMonth ?? 12)
  const products = opts.products ?? []
  const skuToCell = opts.skuToCell ?? {}
  const stockMin = opts.stockMin ?? 30
  const stockMax = opts.stockMax ?? 100
  const demandRecords = opts.demandRecords ?? []
  const maxItemsPerArrival = opts.maxItemsPerArrival ?? 18
  const minItemsPerArrival = opts.minItemsPerArrival ?? 4
  const maxItemsPerConsumption = opts.maxItemsPerConsumption ?? 10
  const movesPerMonth = Math.max(0, opts.movesPerMonth ?? 6)
  const cellAddresses = opts.cellAddresses ?? []

  const months = Math.max(1, Math.ceil(days / 30.437))
  const recordsByDate = groupRecordsByDate(demandRecords)
  const allDemandDates = Object.keys(recordsByDate).sort()
  const cellLoad = {}
  const cellStock = initCellStock()
  const scheduleOpts = { ...opts, maxCapacity: opts.maxCapacity ?? 200 }
  const byZone = cellsByZone(cellAddresses, opts.parseCellAddress)
  const zones = Object.keys(byZone).sort()

  const timed_orders = []
  let arrivalCount = 0
  let consumptionCount = 0
  let inventoryCount = 0
  let moveCount = 0

  for (let m = 0; m < months; m++) {
    const monthStart = Math.floor(m * 30.437)
    const monthEnd = Math.min(days - 1, Math.floor((m + 1) * 30.437) - 1)
    const span = Math.max(0, monthEnd - monthStart)

    // Приёмки: первая ~70% месяца; расходы: последние ~70% (перекрытие в середине)
    const arrTo = monthStart + Math.max(0, Math.floor(span * 0.7))
    const moveFrom = monthStart + Math.max(0, Math.floor(span * 0.25))
    const moveTo = monthStart + Math.max(0, Math.floor(span * 0.75))
    const conFrom = monthStart + Math.max(0, Math.floor(span * 0.3))

    const nArr = varyAround(arrivalsPerMonth, 1)
    const nCon = varyAround(consumptionsPerMonth, 1)
    const nMoveDays = movesPerMonth > 0 ? varyAround(Math.max(1, Math.ceil(movesPerMonth / 2)), 1) : 0

    const arrDates = sampleDatesInWindow(startDate, monthStart, arrTo, nArr)
    const moveDates = sampleDatesInWindow(startDate, moveFrom, moveTo, nMoveDays)
    const conDates = sampleDatesInWindow(startDate, conFrom, monthEnd, nCon)

    const monthEvents = [
      ...arrDates.map(date => ({ kind: 'arr', date })),
      ...moveDates.map(date => ({ kind: 'move', date })),
      ...conDates.map(date => ({ kind: 'con', date })),
    ].sort((a, b) => {
      const byDate = a.date.localeCompare(b.date)
      if (byDate !== 0) return byDate
      const order = { arr: 0, move: 1, con: 2 }
      return (order[a.kind] ?? 9) - (order[b.kind] ?? 9)
    })

    const arrivalLimits = { min: minItemsPerArrival, max: maxItemsPerArrival }

    for (const ev of monthEvents) {
      if (ev.kind === 'arr') {
        let order = buildArrivalOrder(
          ev.date, products, skuToCell, stockMin, stockMax, scheduleOpts,
          arrivalLimits, cellLoad,
        )
        if (!order) {
          order = buildArrivalOrder(
            ev.date, products, skuToCell, stockMin, stockMax, scheduleOpts,
            { min: 2, max: Math.max(2, Math.floor(maxItemsPerArrival / 3)) },
            cellLoad,
          )
        }
        if (order) {
          timed_orders.push(order)
          applyArrivalToStock(order, cellStock)
          arrivalCount++
        }
      } else if (ev.kind === 'move') {
        const maxPerDay = Math.max(1, Math.ceil(movesPerMonth / Math.max(1, nMoveDays)))
        for (let i = 0; i < maxPerDay; i++) {
          const plan = planZoneMove(
            cellStock, byZone, zones, scheduleOpts.maxCapacity,
          )
          if (!plan) break
          const order = buildMoveOrder(ev.date, plan, opts.parseCellAddress)
          timed_orders.push(order)
          applyMoveToStock(order, cellStock)
          moveCount++
        }
      } else {
        const order = buildConsumptionOrder(
          ev.date, products, recordsByDate, allDemandDates, stockMin, maxItemsPerConsumption,
        )
        if (order) {
          applyConsumptionToCellLoad(order, skuToCell, cellLoad)
          applyConsumptionToStock(order, skuToCell, cellStock)
          timed_orders.push(order)
          consumptionCount++
        }
      }
    }

    timed_orders.push(buildInventoryOrder(addDays(startDate, monthEnd)))
    inventoryCount++
  }

  const typeOrder = { ARRIVAL: 0, MOVE: 1, CONSUMPTION: 2, INVENTORY: 3 }
  timed_orders.sort((a, b) => {
    const byDate = a.date.localeCompare(b.date)
    if (byDate !== 0) return byDate
    return (typeOrder[a.type] ?? 9) - (typeOrder[b.type] ?? 9)
  })

  return {
    timed_orders,
    stats: {
      arrivals: arrivalCount,
      consumptions: consumptionCount,
      inventories: inventoryCount,
      moves: moveCount,
      months,
      arrivalsPerMonth,
      consumptionsPerMonth,
      movesPerMonth,
      inventoriesPerMonth: 1,
    },
  }
}
