/** Генератор дневного спроса для обучения прогноза WMS */



export const RU_HOLIDAYS = [

  [1, 1], [1, 2], [1, 3], [1, 4], [1, 5], [1, 6], [1, 7], [1, 8],

  [2, 23], [3, 8], [5, 1], [5, 9], [6, 12], [11, 4],

]



export const DEFAULT_WEEKDAY = [1.05, 1.1, 1.08, 1.05, 1.0, 0.92, 0.88]

/** Пн–Вс: пик в пятницу, спад в выходные — плохо для MA, хорошо для бустинга */
export const XGBOOST_WINS_WEEKDAY = [1.02, 1.04, 1.03, 1.02, 1.28, 0.78, 0.72]



/** Значения по умолчанию для «расширенных» параметров (сложнее для прогноза) */

export const ADVANCED_DEFAULTS = {

  spikeChance: 0,

  spikeMultiplier: 2.5,

  dropChance: 0,

  dropMultiplier: 0.4,

  outlierChance: 0,

  outlierMultiplier: 4,

  autocorr: 0,

  trendBreakChance: 0,

  trendBreakJitter: 0.6,

  skuScaleMin: 0.6,

  skuScaleMax: 1.4,

  perSkuTrendFlip: false,

}



export function isRuHoliday(d) {

  return RU_HOLIDAYS.some(([m, day]) => m === d.getMonth() + 1 && day === d.getDate())

}



export function parseDateInput(value) {

  if (value instanceof Date) {

    if (Number.isNaN(value.getTime())) throw new Error('Некорректная дата')

    return value

  }

  const raw = String(value ?? '').trim()

  const d = new Date(raw.includes('T') ? raw : `${raw}T12:00:00`)

  if (Number.isNaN(d.getTime())) throw new Error('Некорректная дата')

  return d

}



export function formatDateISO(d) {

  return d.toISOString().slice(0, 10)

}



function gaussianRandom() {

  let u = 0

  let v = 0

  while (u === 0) u = Math.random()

  while (v === 0) v = Math.random()

  return Math.sqrt(-2.0 * Math.log(u)) * Math.cos(2.0 * Math.PI * v)

}



function pickTrendBreakDay(days, chance) {

  if (chance <= 0 || days < 30) return null

  if (Math.random() >= chance) return null

  const margin = Math.floor(days * 0.15)

  return margin + Math.floor(Math.random() * (days - 2 * margin))

}



/**

 * @param {object} opts — базовые + расширенные (см. ADVANCED_DEFAULTS)

 */

export function generateDailySeries(opts) {

  const {

    startDate,

    days,

    baseMean,

    trendPerDay,

    noisePct,

    weekendFactor,

    holidayFactor,

    monthlyAmp,

    weekdayFactors,

    zeroDayChance,

    spikeChance = 0,

    spikeMultiplier = 2.5,

    dropChance = 0,

    dropMultiplier = 0.4,

    outlierChance = 0,

    outlierMultiplier = 4,

    autocorr = 0,

    trendBreakChance = 0,

    trendBreakJitter = 0.6,

    fridayBoost = 1,

    septemberBoost = 1,

  } = opts



  const ac = Math.max(0, Math.min(0.95, Number(autocorr) || 0))

  const innovScale = Math.sqrt(Math.max(0.05, 1 - ac * ac))

  const breakDay = pickTrendBreakDay(days, trendBreakChance)

  let arShock = 0

  let trendFactor = 1



  const points = []

  for (let t = 0; t < days; t++) {

    const d = new Date(startDate)

    d.setDate(d.getDate() + t)

    const dow = (d.getDay() + 6) % 7



    if (breakDay !== null && t === breakDay) {

      trendFactor *= 1 + (Math.random() * 2 - 1) * trendBreakJitter

    }



    if (zeroDayChance > 0 && Math.random() < zeroDayChance) {

      points.push({ date: formatDateISO(d), quantity: 0, meta: { dow, holiday: isRuHoliday(d) } })

      arShock *= ac

      continue

    }



    let v = baseMean + trendPerDay * trendFactor * t

    v *= weekdayFactors[dow] ?? 1

    if (dow >= 5) v *= weekendFactor

    if (isRuHoliday(d)) v *= holidayFactor

    if (monthlyAmp > 0) {

      v *= 1 + monthlyAmp * Math.sin((2 * Math.PI * t) / 30.4)

    }

    if (dow === 4 && fridayBoost > 1) {

      v *= fridayBoost

    }

    const monthNum = d.getMonth() + 1

    if (monthNum === 9 && septemberBoost > 1) {

      v *= septemberBoost

    }



    arShock = ac * arShock + innovScale * gaussianRandom()

    v += (noisePct / 100) * baseMean * arShock



    if (spikeChance > 0 && Math.random() < spikeChance) {

      v *= spikeMultiplier

    }

    if (dropChance > 0 && Math.random() < dropChance) {

      v *= dropMultiplier

    }

    if (outlierChance > 0 && Math.random() < outlierChance) {

      v = baseMean * outlierMultiplier * (0.8 + Math.random() * 0.4)

    }



    v = Math.max(0, Math.round(v))



    points.push({

      date: formatDateISO(d),

      quantity: v,

      meta: { dow, holiday: isRuHoliday(d) },

    })

  }

  return points

}



function yieldToMain() {

  return new Promise(resolve => setTimeout(resolve, 0))

}



/** Случайный масштаб SKU в диапазоне heterogeneity */

function skuScale(params) {

  const lo = params.skuScaleMin ?? ADVANCED_DEFAULTS.skuScaleMin

  const hi = params.skuScaleMax ?? ADVANCED_DEFAULTS.skuScaleMax

  return lo + Math.random() * (hi - lo)

}



export async function generateMultiSkuHistory(catalog, params, skuCount, onProgress) {

  const pool = [...catalog]

  const picked = []

  while (picked.length < skuCount && pool.length) {

    const i = Math.floor(Math.random() * pool.length)

    picked.push(pool.splice(i, 1)[0])

  }



  const startDate = parseDateInput(params.startDate)

  const allRecords = []

  const total = picked.length



  for (let idx = 0; idx < picked.length; idx++) {

    const product = picked[idx]

    onProgress?.({

      current: idx + 1,

      total,

      message: `История спроса: ${product.sku} (${idx + 1}/${total})`,

    })



    const scale = skuScale(params)

    let trend = params.trendPerDay * scale

    if (params.perSkuTrendFlip && Math.random() < 0.35) {

      trend *= -1

    }



    const series = generateDailySeries({

      startDate,

      days: params.days,

      baseMean: params.baseMean * scale,

      trendPerDay: trend,

      noisePct: params.noisePct,

      weekendFactor: params.weekendFactor,

      holidayFactor: params.holidayFactor,

      monthlyAmp: params.monthlyAmp,

      weekdayFactors: params.weekdayFactors,

      zeroDayChance: params.zeroDayChance,

      spikeChance: params.spikeChance,

      spikeMultiplier: params.spikeMultiplier,

      dropChance: params.dropChance,

      dropMultiplier: params.dropMultiplier,

      outlierChance: params.outlierChance,

      outlierMultiplier: params.outlierMultiplier,

      autocorr: params.autocorr,

      trendBreakChance: params.trendBreakChance,

      trendBreakJitter: params.trendBreakJitter,

      fridayBoost: params.fridayBoost ?? 1,

      septemberBoost: params.septemberBoost ?? 1,

    })

    for (const p of series) {

      if (p.quantity > 0) {

        allRecords.push({ sku: product.sku, date: p.date, quantity: p.quantity })

      }

    }

    if (total > 3) await yieldToMain()

  }

  return { records: allRecords, products: picked, seriesBySku: groupBySku(allRecords) }

}



function groupBySku(records) {

  const map = {}

  for (const r of records) {

    if (!map[r.sku]) map[r.sku] = []

    map[r.sku].push({ date: r.date, quantity: r.quantity })

  }

  for (const sku of Object.keys(map)) {

    map[sku].sort((a, b) => a.date.localeCompare(b.date))

  }

  return map

}



export function aggregateByDate(records) {

  const map = {}

  for (const r of records) {

    map[r.date] = (map[r.date] || 0) + r.quantity

  }

  return Object.entries(map)

    .sort(([a], [b]) => a.localeCompare(b))

    .map(([date, quantity]) => ({ date, quantity }))

}



export function historyImportPayload(records, comment) {

  return {

    comment: comment || 'Синтетическая история спроса',

    records,

  }

}



/** Плоский объект пресета (без weekdayFactors) */

export function presetParams(name) {

  const p = PRESETS[name]

  if (!p) return { ...PRESETS.stable }

  const { label, description, ...rest } = p

  return { ...rest }

}



export function buildDemandParams({ preset, overrides = {}, weekdayFactors = DEFAULT_WEEKDAY, startDate, days }) {

  const base = presetParams(preset)

  const adv = { ...ADVANCED_DEFAULTS, ...(overrides.advanced || {}) }

  return {

    startDate,

    days,

    weekdayFactors: overrides.weekdayFactors || base.weekdayFactors || weekdayFactors,

    fridayBoost: overrides.fridayBoost ?? base.fridayBoost ?? 1,

    septemberBoost: overrides.septemberBoost ?? base.septemberBoost ?? 1,

    ...base,

    ...overrides,

    ...adv,

  }

}



export const PRESETS = {

  stable: {

    label: 'Стабильный спрос',

    description: 'Ровный ряд — метрики ML часто завышены.',

    baseMean: 15,

    trendPerDay: 0,

    noisePct: 15,

    weekendFactor: 0.85,

    holidayFactor: 0.7,

    monthlyAmp: 0.1,

    zeroDayChance: 0.05,

    spikeChance: 0,

    dropChance: 0,

    outlierChance: 0,

    autocorr: 0,

    trendBreakChance: 0,

    skuScaleMin: 0.75,

    skuScaleMax: 1.25,

    perSkuTrendFlip: false,

  },

  growth: {

    label: 'Рост спроса',

    description: 'Линейный рост, умеренный шум.',

    baseMean: 10,

    trendPerDay: 0.08,

    noisePct: 20,

    weekendFactor: 0.9,

    holidayFactor: 0.75,

    monthlyAmp: 0.08,

    zeroDayChance: 0.03,

    spikeChance: 0.02,

    dropChance: 0.01,

    outlierChance: 0.005,

    autocorr: 0.15,

    trendBreakChance: 0.05,

    skuScaleMin: 0.5,

    skuScaleMax: 1.6,

    perSkuTrendFlip: true,

  },

  decline: {

    label: 'Снижение спроса',

    description: 'Спад с сезонностью.',

    baseMean: 25,

    trendPerDay: -0.06,

    noisePct: 18,

    weekendFactor: 0.88,

    holidayFactor: 0.8,

    monthlyAmp: 0.12,

    zeroDayChance: 0.04,

    spikeChance: 0.02,

    dropChance: 0.02,

    outlierChance: 0.01,

    autocorr: 0.2,

    trendBreakChance: 0.08,

    skuScaleMin: 0.45,

    skuScaleMax: 1.5,

    perSkuTrendFlip: true,

  },

  seasonal: {

    label: 'Яркая сезонность',

    description: 'Сильная месячная волна и праздники.',

    baseMean: 12,

    trendPerDay: 0.02,

    noisePct: 25,

    weekendFactor: 0.7,

    holidayFactor: 1.4,

    monthlyAmp: 0.35,

    zeroDayChance: 0.02,

    spikeChance: 0.03,

    dropChance: 0.02,

    outlierChance: 0.015,

    autocorr: 0.25,

    trendBreakChance: 0.1,

    skuScaleMin: 0.4,

    skuScaleMax: 1.8,

    perSkuTrendFlip: true,

  },

  volatile: {

    label: 'Сильные колебания',

    description: 'Высокий шум и нулевые дни.',

    baseMean: 18,

    trendPerDay: 0,

    noisePct: 45,

    weekendFactor: 1,

    holidayFactor: 1,

    monthlyAmp: 0.2,

    zeroDayChance: 0.08,

    spikeChance: 0.06,

    dropChance: 0.05,

    outlierChance: 0.02,

    autocorr: 0.35,

    trendBreakChance: 0.12,

    skuScaleMin: 0.35,

    skuScaleMax: 2,

    perSkuTrendFlip: true,

  },

  irregular: {

    label: 'Нерегулярный (для ML)',

    description: 'Всплески, провалы, смена тренда — реалистичнее для сравнения моделей.',

    baseMean: 14,

    trendPerDay: 0.03,

    noisePct: 35,

    weekendFactor: 0.75,

    holidayFactor: 0.65,

    monthlyAmp: 0.22,

    zeroDayChance: 0.1,

    spikeChance: 0.08,

    dropChance: 0.06,

    outlierChance: 0.025,

    autocorr: 0.4,

    trendBreakChance: 0.25,

    trendBreakJitter: 0.8,

    skuScaleMin: 0.25,

    skuScaleMax: 2.2,

    perSkuTrendFlip: true,

  },

  spiky: {

    label: 'Редкие пики',

    description: 'Резкие всплески спроса, иначе спокойный фон.',

    baseMean: 12,

    trendPerDay: 0,

    noisePct: 20,

    weekendFactor: 0.9,

    holidayFactor: 0.85,

    monthlyAmp: 0.15,

    zeroDayChance: 0.06,

    spikeChance: 0.12,

    spikeMultiplier: 3.5,

    dropChance: 0.03,

    outlierChance: 0.04,

    outlierMultiplier: 5,

    autocorr: 0.3,

    trendBreakChance: 0.15,

    skuScaleMin: 0.3,

    skuScaleMax: 2.5,

    perSkuTrendFlip: true,

  },

  ml_benchmark: {

    label: 'Бенчмарк прогнозов',

    description: 'Сбалансированная сложность: не «идеальный» стабильный ряд.',

    baseMean: 16,

    trendPerDay: 0.04,

    noisePct: 30,

    weekendFactor: 0.82,

    holidayFactor: 0.72,

    monthlyAmp: 0.18,

    zeroDayChance: 0.07,

    spikeChance: 0.05,

    dropChance: 0.04,

    outlierChance: 0.02,

    autocorr: 0.45,

    trendBreakChance: 0.2,

    trendBreakJitter: 0.7,

    skuScaleMin: 0.3,

    skuScaleMax: 2,

    perSkuTrendFlip: true,

  },

  xgboost_wins: {

    label: 'Выйграет Бустинг',

    description:
      'Длинная история (~900 дн.), пятничные всплески, сентябрьская сезонность, автокорреляция — под глобальный XGBoost.',

    baseMean: 14,

    trendPerDay: 0.05,

    noisePct: 22,

    weekendFactor: 0.7,

    holidayFactor: 0.65,

    monthlyAmp: 0.34,

    fridayBoost: 1.35,

    septemberBoost: 1.5,

    zeroDayChance: 0.04,

    spikeChance: 0.04,

    spikeMultiplier: 2.8,

    dropChance: 0.02,

    outlierChance: 0.015,

    outlierMultiplier: 3.5,

    autocorr: 0.58,

    trendBreakChance: 0.12,

    trendBreakJitter: 0.5,

    skuScaleMin: 0.4,

    skuScaleMax: 1.8,

    perSkuTrendFlip: true,

    weekdayFactors: XGBOOST_WINS_WEEKDAY,

    recommendedHistoryDays: 900,

  },

  ml_benchmark_super: {

    label: 'Бенчмарк прогнозов Супер',

    description:
      'Реалистичный микс: нерегулярность (провалы, смена тренда, автокорреляция) + редкие пики и выбросы. Для честного сравнения моделей.',

    baseMean: 15,

    trendPerDay: 0.035,

    noisePct: 33,

    weekendFactor: 0.78,

    holidayFactor: 0.68,

    monthlyAmp: 0.21,

    zeroDayChance: 0.09,

    spikeChance: 0.1,

    spikeMultiplier: 3.2,

    dropChance: 0.055,

    dropMultiplier: 0.38,

    outlierChance: 0.032,

    outlierMultiplier: 4.5,

    autocorr: 0.43,

    trendBreakChance: 0.22,

    trendBreakJitter: 0.78,

    skuScaleMin: 0.22,

    skuScaleMax: 2.4,

    perSkuTrendFlip: true,

  },

}


