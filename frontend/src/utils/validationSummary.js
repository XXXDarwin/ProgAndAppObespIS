/**
 * Краткая JSON-сводка результатов holdout-валидации (одна модель или сравнение всех).
 */

function mapCategory(c) {
  return {
    category: c.category_name,
    sku_count: c.products_validated,
    mae: c.avg_mae,
    rmse: c.avg_rmse,
    mape: c.avg_mape,
    r2: c.avg_r2,
  }
}

function mapOkSku(r) {
  return {
    sku: r.product_sku,
    product_id: r.product_id,
    category: r.category?.name ?? null,
    mae: r.mae,
    rmse: r.rmse,
    mape: r.mape,
    r2: r.r2,
    train_days: r.train_days,
    test_days: r.test_days,
  }
}

function mapSkippedSku(r) {
  return { sku: r.product_sku, product_id: r.product_id, reason: r.skip_reason }
}

function mapModelRun(run) {
  const results = run.results || []
  return {
    method: run.forecast_method,
    label: run.forecast_method_label,
    validated: run.products_validated,
    total: run.products_total,
    skipped: run.products_skipped,
    avg_mae: run.avg_mae,
    avg_rmse: run.avg_rmse,
    avg_mape: run.avg_mape,
    avg_r2: run.avg_r2,
    categories: (run.categories || []).map(mapCategory),
    skus_ok: results.filter(r => r.status === 'ok').map(mapOkSku),
    skus_skipped: results.filter(r => r.status !== 'ok').map(mapSkippedSku),
  }
}

function mapSkuMaeMatrix(rows, methodRuns) {
  if (!rows?.length) return []
  return rows.map(row => ({
    sku: row.product_sku,
    product_id: row.product_id,
    mae_by_method: Object.fromEntries(
      (methodRuns || []).map(run => [
        run.forecast_method,
        row.metrics[run.forecast_method] ?? null,
      ]),
    ),
  }))
}

/**
 * @param {object} opts
 * @param {object|null} opts.compare — ответ validate/compare
 * @param {object|null} opts.single — ответ validate
 * @param {number} opts.testSize
 * @param {number|null} opts.productId
 * @param {string|null} opts.productSku
 */
export function buildValidationSummaryJson({
  compare = null,
  single = null,
  testSize = 0.2,
  productId = null,
  productSku = null,
}) {
  const scope = {
    summary_version: 1,
    test_size: testSize,
    scope: productId ? 'product' : 'catalog',
    product_id: productId,
    product_sku: productSku,
  }

  if (compare?.runs?.length) {
    const runs = compare.runs
    return {
      ...scope,
      kind: 'compare',
      validated_at: compare.validated_at,
      methods_total: compare.methods_total,
      best_by_avg_mae: {
        method: runs[0].forecast_method,
        label: runs[0].forecast_method_label,
        avg_mae: runs[0].avg_mae,
      },
      models: runs.map(mapModelRun),
      sku_mae_by_method: mapSkuMaeMatrix(
        buildSkuMatrixFromRuns(runs),
        runs,
      ),
    }
  }

  if (single) {
    return {
      ...scope,
      kind: 'single',
      validated_at: single.validated_at,
      method: single.forecast_method,
      label: single.forecast_method_label,
      validated: single.products_validated,
      total: single.products_total,
      skipped: single.products_skipped,
      categories: (single.categories || []).map(mapCategory),
      skus_ok: (single.results || []).filter(r => r.status === 'ok').map(mapOkSku),
      skus_skipped: (single.results || []).filter(r => r.status !== 'ok').map(mapSkippedSku),
    }
  }

  return null
}

/** Для sku_mae_by_method без дублирования логики Vue-компонента. */
function buildSkuMatrixFromRuns(runs) {
  const byProduct = new Map()
  for (const run of runs) {
    for (const r of run.results || []) {
      if (!byProduct.has(r.product_id)) {
        byProduct.set(r.product_id, {
          product_id: r.product_id,
          product_sku: r.product_sku,
          metrics: {},
        })
      }
      const row = byProduct.get(r.product_id)
      row.metrics[run.forecast_method] = r.status === 'ok' ? r.mae : null
    }
  }
  return [...byProduct.values()].sort((a, b) =>
    (a.product_sku || '').localeCompare(b.product_sku || ''),
  )
}

export function formatValidationSummaryJson(summary) {
  if (!summary) return ''
  return JSON.stringify(summary, null, 2)
}
