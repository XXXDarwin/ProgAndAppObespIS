import {
  generateProducts,
  generateOrderLines,
  productsToImportJson,
  orderToImportJson,
} from './generators.js'
import { downloadJson, downloadCsv, downloadXlsx } from './export.js'
import { DEMO_PRODUCTS } from './catalog.js'
import {
  PRESETS,
  generateMultiSkuHistory,
  aggregateByDate,
  historyImportPayload,
  parseDateInput,
  formatDateISO,
} from './history.js'
import { generateFullWarehouse } from './warehouse-sim.js'
import { login, uploadFullWarehouse } from './wms-api.js'

const state = {
  catalog: [...DEMO_PRODUCTS],
  productsPreview: [],
  arrivalPreview: [],
  consumptionPreview: [],
  historyRecords: [],
  historyChart: null,
  fullSim: null,
}

const DEFAULT_WEEKDAY = [1.05, 1.1, 1.08, 1.05, 1.0, 0.92, 0.88]

function $(id) { return document.getElementById(id) }

function setCatalog(items) {
  state.catalog = items
  updateCatalogBar()
}

function updateCatalogBar() {
  const el = $('catalogBar')
  if (!el) return
  const n = state.catalog.length
  el.textContent = n
    ? `Текущий каталог: ${n} товар(ов). Заказы на приёмку/расход берут SKU из этого списка.`
    : 'Каталог пуст. Сначала сгенерируйте товары или включите демо-каталог.'
}

function renderPreview(el, rows, columns) {
  if (!rows.length) {
    el.innerHTML = '<p class="hint">Нажмите «Сгенерировать» для предпросмотра</p>'
    return
  }
  const head = columns.map(c => `<th>${c}</th>`).join('')
  const body = rows.slice(0, 15).map(r =>
    `<tr>${columns.map(c => `<td>${r[c] ?? ''}</td>`).join('')}</tr>`,
  ).join('')
  const more = rows.length > 15 ? `<p class="hint">… и ещё ${rows.length - 15} строк</p>` : ''
  el.innerHTML = `<table><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table>${more}`
}

function initTabs() {
  document.querySelectorAll('.tab').forEach(tab => {
    tab.addEventListener('click', () => {
      document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'))
      document.querySelectorAll('.panel').forEach(p => p.classList.remove('active'))
      tab.classList.add('active')
      $(`panel-${tab.dataset.tab}`).classList.add('active')
    })
  })
}

function readProductsForm() {
  return {
    count: Number($('prodCount').value) || 10,
    skuPrefix: $('prodPrefix').value.trim() || 'GEN',
    mode: $('prodMode').value,
    startIndex: Number($('prodStart').value) || 1,
    skipDuplicates: $('prodSkipDup').checked,
  }
}

function readOrderForm(prefix) {
  return {
    lineCount: Number($(`${prefix}Lines`).value) || 5,
    qtyMin: Number($(`${prefix}QtyMin`).value) || 1,
    qtyMax: Number($(`${prefix}QtyMax`).value) || 10,
    withCells: $(`${prefix}Cells`).checked,
    allowRepeatSku: $(`${prefix}Repeat`).checked,
    comment: $(`${prefix}Comment`).value.trim(),
  }
}

function exportProducts(format) {
  const rows = state.productsPreview
  if (!rows.length) { alert('Сначала сгенерируйте данные'); return }
  const cols = ['sku', 'name', 'unit', 'category', 'weight', 'description']
  const form = readProductsForm()
  if (format === 'json') downloadJson('products.json', productsToImportJson(rows, form.skipDuplicates))
  else if (format === 'csv') downloadCsv('products.csv', rows, cols)
  else downloadXlsx('products.xlsx', rows, cols, 'Товары')
}

function exportOrder(type, format) {
  const rows = type === 'arrival' ? state.arrivalPreview : state.consumptionPreview
  if (!rows.length) { alert('Сначала сгенерируйте данные'); return }
  const cols = rows[0].cell ? ['sku', 'quantity', 'cell'] : ['sku', 'quantity']
  const opts = readOrderForm(type === 'arrival' ? 'arr' : 'con')
  const base = type === 'arrival' ? 'arrival_order' : 'consumption_order'
  if (format === 'json') {
    downloadJson(`${base}.json`, orderToImportJson(rows, opts.comment, type))
  } else if (format === 'csv') {
    downloadCsv(`${base}.csv`, rows, cols)
  } else {
    downloadXlsx(`${base}.xlsx`, rows, cols, 'Заказ')
  }
}

function bindProducts() {
  $('btnGenProducts').addEventListener('click', () => {
    const form = readProductsForm()
    const items = generateProducts(form)
    state.productsPreview = items
    setCatalog(items)
    renderPreview($('prodPreview'), items, ['sku', 'name', 'category', 'unit'])
  })

  $('btnUseDemoCatalog').addEventListener('click', () => {
    setCatalog([...DEMO_PRODUCTS])
    state.productsPreview = [...DEMO_PRODUCTS]
    renderPreview($('prodPreview'), DEMO_PRODUCTS, ['sku', 'name', 'category', 'unit'])
  })

  $('btnProdJson').addEventListener('click', () => exportProducts('json'))
  $('btnProdCsv').addEventListener('click', () => exportProducts('csv'))
  $('btnProdXlsx').addEventListener('click', () => exportProducts('xlsx'))
}

function bindOrder(type, prefix) {
  $(`btnGen${prefix}`).addEventListener('click', () => {
    if (!state.catalog.length) {
      alert('Каталог пуст. На вкладке «Товары» сгенерируйте список или загрузите демо-каталог.')
      return
    }
    const opts = readOrderForm(prefix === 'Arr' ? 'arr' : 'con')
    const lines = generateOrderLines(state.catalog, opts)
    if (type === 'arrival') {
      state.arrivalPreview = lines
      renderPreview($('arrPreview'), lines, lines[0]?.cell ? ['sku', 'quantity', 'cell'] : ['sku', 'quantity'])
    } else {
      state.consumptionPreview = lines
      renderPreview($('conPreview'), lines, lines[0]?.cell ? ['sku', 'quantity', 'cell'] : ['sku', 'quantity'])
    }
  })

  $(`btn${prefix}Json`).addEventListener('click', () => exportOrder(type, 'json'))
  $(`btn${prefix}Csv`).addEventListener('click', () => exportOrder(type, 'csv'))
  $(`btn${prefix}Xlsx`).addEventListener('click', () => exportOrder(type, 'xlsx'))
}

function initWeekdayGrid() {
  const grid = $('weekdayGrid')
  const labels = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс']
  grid.innerHTML = labels.map((lab, i) => `
    <div>
      <label>${lab}</label>
      <input type="number" class="wd-factor" data-i="${i}" min="0.1" max="2" step="0.05" value="${DEFAULT_WEEKDAY[i]}" />
    </div>
  `).join('')
}

function readWeekdayFactors() {
  return [...document.querySelectorAll('.wd-factor')].map(el => Number(el.value) || 1)
}

function updatePresetHint(name) {
  const el = $('histPresetHint')
  if (!el) return
  const p = PRESETS[name]
  el.textContent = p?.description || ''
}

function applyPreset(name) {
  const p = PRESETS[name]
  if (!p) return
  $('histMean').value = p.baseMean
  $('histTrend').value = p.trendPerDay
  $('histNoise').value = p.noisePct
  $('histWeekend').value = p.weekendFactor
  $('histHoliday').value = p.holidayFactor
  $('histMonthly').value = p.monthlyAmp
  $('histZero').value = p.zeroDayChance
  if ($('histSpikeChance')) $('histSpikeChance').value = p.spikeChance ?? 0
  if ($('histSpikeMult')) $('histSpikeMult').value = p.spikeMultiplier ?? 2.5
  if ($('histDropChance')) $('histDropChance').value = p.dropChance ?? 0
  if ($('histDropMult')) $('histDropMult').value = p.dropMultiplier ?? 0.4
  if ($('histOutlierChance')) $('histOutlierChance').value = p.outlierChance ?? 0
  if ($('histOutlierMult')) $('histOutlierMult').value = p.outlierMultiplier ?? 4
  if ($('histAutocorr')) $('histAutocorr').value = p.autocorr ?? 0
  if ($('histTrendBreak')) $('histTrendBreak').value = p.trendBreakChance ?? 0
  if ($('histSkuScaleMin')) $('histSkuScaleMin').value = p.skuScaleMin ?? 0.6
  if ($('histSkuScaleMax')) $('histSkuScaleMax').value = p.skuScaleMax ?? 1.4
  if ($('histPerSkuTrendFlip')) $('histPerSkuTrendFlip').checked = !!p.perSkuTrendFlip
  if (p.weekdayFactors?.length === 7) {
    document.querySelectorAll('.wd-factor').forEach((el, i) => {
      el.value = p.weekdayFactors[i]
    })
  }
  if (p.recommendedHistoryDays && $('histDays')) {
    $('histDays').value = p.recommendedHistoryDays
  }
  updatePresetHint(name)
}

function readHistoryParams() {
  const days = Number($('histDays').value) || 365
  const end = parseDateInput($('histStart').value || formatDateISO(new Date()))
  const start = new Date(end)
  start.setDate(start.getDate() - days + 1)
  return {
    startDate: start,
    days,
    baseMean: Number($('histMean').value) || 10,
    trendPerDay: Number($('histTrend').value) || 0,
    noisePct: Number($('histNoise').value) || 15,
    weekendFactor: Number($('histWeekend').value) || 1,
    holidayFactor: Number($('histHoliday').value) || 1,
    monthlyAmp: Number($('histMonthly').value) || 0,
    zeroDayChance: Number($('histZero').value) || 0,
    weekdayFactors: readWeekdayFactors(),
    spikeChance: Number($('histSpikeChance')?.value) || 0,
    spikeMultiplier: Number($('histSpikeMult')?.value) || 2.5,
    dropChance: Number($('histDropChance')?.value) || 0,
    dropMultiplier: Number($('histDropMult')?.value) || 0.4,
    outlierChance: Number($('histOutlierChance')?.value) || 0,
    outlierMultiplier: Number($('histOutlierMult')?.value) || 4,
    autocorr: Number($('histAutocorr')?.value) || 0,
    trendBreakChance: Number($('histTrendBreak')?.value) || 0,
    trendBreakJitter: 0.7,
    skuScaleMin: Number($('histSkuScaleMin')?.value) || 0.6,
    skuScaleMax: Number($('histSkuScaleMax')?.value) || 1.4,
    perSkuTrendFlip: $('histPerSkuTrendFlip')?.checked ?? false,
  }
}

function renderHistoryChart(records) {
  const agg = aggregateByDate(records)
  const ctx = $('historyChart')
  if (state.historyChart) state.historyChart.destroy()
  state.historyChart = new Chart(ctx, {
    type: 'line',
    data: {
      labels: agg.map(p => p.date),
      datasets: [{
        label: 'Суммарный спрос (все SKU)',
        data: agg.map(p => p.quantity),
        borderColor: '#2563eb',
        backgroundColor: 'rgba(37, 99, 235, 0.1)',
        fill: true,
        tension: 0.25,
        pointRadius: 0,
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      scales: { y: { beginAtZero: true } },
    },
  })
}

function bindHistory() {
  $('histPreset').addEventListener('change', e => applyPreset(e.target.value))
  applyPreset($('histPreset').value || 'ml_benchmark_super')

  $('btnGenHistory').addEventListener('click', async () => {
    if (!state.catalog.length) {
      alert('Сначала сгенерируйте товары или загрузите демо-каталог.')
      return
    }
    const btn = $('btnGenHistory')
    btn.disabled = true
    try {
      const skuCount = Math.min(Number($('histSkuCount').value) || 5, state.catalog.length)
      const params = readHistoryParams()
      const { records, products } = await generateMultiSkuHistory(state.catalog, params, skuCount)
      state.historyRecords = records

      $('histStats').textContent =
        `Записей: ${records.length} · SKU: ${products.length} · дней: ${params.days} · с ${formatDateISO(params.startDate)}`

      renderHistoryChart(records)
      renderPreview($('histPreview'), records.slice(0, 20), ['date', 'sku', 'quantity'])
    } catch (e) {
      alert(`Ошибка генерации: ${e.message}`)
    } finally {
      btn.disabled = false
    }
  })

  $('btnHistJson').addEventListener('click', () => {
    if (!state.historyRecords.length) { alert('Сначала сгенерируйте'); return }
    downloadJson('demand_history.json', historyImportPayload(state.historyRecords, 'Синтетическая история'))
  })
  $('btnHistCsv').addEventListener('click', () => {
    if (!state.historyRecords.length) return
    downloadCsv('demand_history.csv', state.historyRecords, ['date', 'sku', 'quantity'])
  })
  $('btnHistXlsx').addEventListener('click', () => {
    if (!state.historyRecords.length) return
    downloadXlsx('demand_history.xlsx', state.historyRecords, ['date', 'sku', 'quantity'], 'История')
  })

  $('btnHistUpload').addEventListener('click', async () => {
    if (!state.historyRecords.length) { alert('Сначала сгенерируйте'); return }
    $('histUploadMsg').textContent = 'Вход и отправка…'
    try {
      const token = await getApiToken()
      const base = $('apiBase').value.trim().replace(/\/$/, '')
      const res = await fetch(`${base}/api/predictions/history/import`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify(historyImportPayload(state.historyRecords)),
      })
      const data = await res.json()
      if (!res.ok) throw new Error(data.detail || res.statusText)
      $('histUploadMsg').textContent =
        `OK: заказов ${data.orders_created}, позиций ${data.items_created}, дней ${data.days_covered}`
    } catch (e) {
      $('histUploadMsg').textContent = `Ошибка: ${e.message}`
    }
  })
}

function getApiCredentials() {
  return {
    base: $('apiBase').value.trim(),
    user: $('apiUser').value.trim(),
    pass: $('apiPass').value,
  }
}

async function getApiToken() {
  const { base, user, pass } = getApiCredentials()
  if (!base || !user || !pass) throw new Error('Укажите URL, логин и пароль WMS')
  return login(base, user, pass)
}

function setFullLog(text, kind = '') {
  const el = $('fullLog')
  el.textContent = text
  el.className = 'log-box visible' + (kind ? ` ${kind}` : '')
}

function setFullProgress(visible, percent = 0, message = '') {
  const wrap = $('fullProgressWrap')
  wrap.classList.toggle('hidden', !visible)
  $('fullProgressBar').style.width = `${Math.min(100, Math.max(0, percent))}%`
  $('fullProgressPct').textContent = `${Math.round(percent)}%`
  $('fullProgressText').textContent = message || 'Подготовка…'
}

function readFullForm() {
  const useHistTabParams = $('fullHistCustom')?.checked
  return {
    productCount: Number($('fullProdCount').value) || 80,
    skuPrefix: $('fullSkuPrefix').value.trim() || 'GEN',
    zones: $('fullZones').value,
    racksPerZone: Number($('fullRacks').value) || 5,
    shelvesPerRack: Number($('fullShelves').value) || 4,
    positionsPerShelf: Number($('fullPositions').value) || 4,
    stockMin: Number($('fullStockMin').value) || 30,
    stockMax: Number($('fullStockMax').value) || 100,
    historyDays: Number($('fullHistDays').value) || 365,
    historyPreset: $('fullHistPreset').value,
    demandParams: useHistTabParams ? readHistoryParams() : null,
    historySkuMode: $('fullHistSkuMode').value,
    historySampleSize: Number($('fullHistSample').value) || 50,
    arrivalsPerMonth: Number($('fullArrPerMonth').value) || 8,
    consumptionsPerMonth: Number($('fullConPerMonth').value) || 12,
    movesPerMonth: Number($('fullMovesPerMonth')?.value) ?? 6,
    maxItemsPerArrival: Number($('fullArrItemsMax').value) || 18,
    maxItemsPerConsumption: Number($('fullConItemsMax').value) || 10,
    skipDuplicates: $('fullSkipDup').checked,
    runMlTraining: $('fullTrainMl').checked,
  }
}

function bindFullWarehouse() {
  $('btnGenFull').addEventListener('click', async () => {
    const btn = $('btnGenFull')
    btn.disabled = true
    $('btnUploadFull').disabled = true
    $('btnFullJson').disabled = true
    setFullProgress(true, 0, 'Запуск генерации…')
    setFullLog('Генерация полного склада…')

    try {
      const sim = await generateFullWarehouse(readFullForm(), ({ percent, message }) => {
        setFullProgress(true, percent, message)
      })
      state.fullSim = sim
      setCatalog(sim.products)

      const s = sim.stats
      $('fullStats').innerHTML = `
        <strong>Сгенерировано:</strong>
        товаров ${s.products} (${s.categories} категорий) ·
        ячеек ${s.cells} ·
        приёмок ~${s.arrivals} (${s.arrivalsPerMonth}/мес.) ·
        расходов ~${s.consumptions} (${s.consumptionsPerMonth}/мес.) ·
        перемещений ~${s.moves} (${s.movesPerMonth}/мес.) ·
        инвентаризаций ${s.inventories} (1 в конце каждого месяца) ·
        точек спроса для ML ${s.historyRecords} (${s.historySkus} SKU) ·
        период ${s.periodFrom} — ${s.periodTo}
      `
      $('fullStats').classList.add('visible')

      renderPreview($('fullPreview'), sim.products.slice(0, 8), ['sku', 'name', 'category'])
      $('btnUploadFull').disabled = false
      $('btnFullJson').disabled = false
      setFullProgress(true, 100, 'Готово')
      setFullLog('Готово к загрузке. Нажмите «Загрузить в WMS».', 'ok')
    } catch (e) {
      state.fullSim = null
      setFullProgress(false)
      setFullLog(`Ошибка генерации: ${e.message}`, 'error')
    } finally {
      btn.disabled = false
    }
  })

  $('btnFullJson').addEventListener('click', () => {
    if (!state.fullSim) return
    downloadJson('warehouse_bootstrap.json', state.fullSim.bootstrapPayload)
  })

  $('btnUploadFull').addEventListener('click', async () => {
    if (!state.fullSim) return
    $('btnUploadFull').disabled = true
    $('btnGenFull').disabled = true
    setFullProgress(true, 0, 'Вход в WMS…')
    setFullLog('Вход в WMS…')
    try {
      const token = await getApiToken()
      setFullProgress(true, 5, 'Загрузка склада…')
      setFullLog('Загрузка склада (может занять несколько минут)…')
      const result = await uploadFullWarehouse(
        $('apiBase').value.trim(),
        token,
        state.fullSim,
        {
          onProgress: (msg, pct) => {
            if (typeof pct === 'number') setFullProgress(true, pct, msg)
            setFullLog(msg)
          },
        },
      )
      const lines = [
        `Ячейки: +${result.cells_created} (уже были ${result.cells_skipped}${result.cells_reactivated ? `, активировано ${result.cells_reactivated}` : ''})`,
        `Товары: +${result.products_created} (пропущено ${result.products_skipped})`,
        `Приёмки: ${result.timed_arrivals ?? result.arrival_orders_completed} заказов, ${result.stock_lines_applied} поз.`,
        `Расходы: ${result.timed_consumptions ?? result.history_orders} заказов, ${result.history_items} поз.`,
        result.timed_moves != null ? `Перемещения: ${result.timed_moves} (история в разделе «Перемещения»)` : '',
        result.timed_inventories != null ? `Инвентаризации: ${result.timed_inventories} заказов, ${result.timed_inventory_items ?? 0} поз.` : '',
        result.ml_training_started ? 'Обучение ML запущено в фоне.' : '',
        result.warnings?.length ? `Предупреждения: ${result.warnings.join('; ')}` : '',
        result.history_chunks ? `История загружена частями: ${result.history_chunks}` : '',
      ].filter(Boolean).join('\n')
      setFullProgress(true, 100, 'Загрузка завершена')
      setFullLog(`Успешно:\n${lines}`, 'ok')
    } catch (e) {
      setFullProgress(false)
      setFullLog(`Ошибка: ${e.message}`, 'error')
    } finally {
      $('btnUploadFull').disabled = false
      $('btnGenFull').disabled = false
    }
  })
}

function initHistoryDefaults() {
  const d = new Date()
  $('histStart').value = formatDateISO(d)
  applyPreset('stable')
}

initTabs()
initWeekdayGrid()
initHistoryDefaults()
updateCatalogBar()
bindFullWarehouse()
bindProducts()
bindOrder('arrival', 'Arr')
bindOrder('consumption', 'Con')
bindHistory()

renderPreview($('prodPreview'), DEMO_PRODUCTS.slice(0, 5), ['sku', 'name', 'category', 'unit'])
