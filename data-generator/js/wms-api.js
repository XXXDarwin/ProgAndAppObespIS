/**

 * Клиент WMS API для загрузки сгенерированных данных.

 */



function apiRoot(baseUrl) {

  return baseUrl.replace(/\/$/, '')

}



function wrapFetchError(err, baseUrl, phase) {

  const msg = err?.message || String(err)

  if (msg === 'Failed to fetch' || err?.name === 'TypeError') {

    return new Error(

      `${phase}: не удалось связаться с API (${apiRoot(baseUrl)}). `

      + 'Проверьте, что backend запущен (docker compose / uvicorn), URL верный, '

      + 'и перезапустите backend после обновления CORS (страница генератора: http://localhost:8765).',

    )

  }

  return err instanceof Error ? err : new Error(msg)

}



export async function login(baseUrl, username, password) {

  const base = apiRoot(baseUrl)

  const body = new URLSearchParams({ username, password })

  let res

  try {

    res = await fetch(`${base}/api/auth/login`, {

      method: 'POST',

      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },

      body,

    })

  } catch (err) {

    throw wrapFetchError(err, baseUrl, 'Вход')

  }

  const data = await res.json().catch(() => ({}))

  if (!res.ok) {

    const detail = data.detail || res.statusText

    throw new Error(typeof detail === 'string' ? detail : JSON.stringify(detail))

  }

  return data.access_token

}



export async function postBootstrap(baseUrl, token, payload, { onProgress } = {}) {

  const base = apiRoot(baseUrl)

  onProgress?.('Отправка пакета на сервер…')

  let res

  try {

    res = await fetch(`${base}/api/warehouse/bootstrap`, {

      method: 'POST',

      headers: {

        'Content-Type': 'application/json',

        Authorization: `Bearer ${token}`,

      },

      body: JSON.stringify(payload),

    })

  } catch (err) {

    throw wrapFetchError(err, baseUrl, 'Загрузка склада')

  }

  const data = await res.json().catch(() => ({}))

  if (!res.ok) {

    const detail = data.detail || res.statusText

    throw new Error(typeof detail === 'string' ? detail : JSON.stringify(detail))

  }

  return data

}



/** Разбивка очень большой истории на несколько bootstrap-вызовов (только история). */

export async function postHistoryChunks(baseUrl, token, records, comment, chunkSize, { onProgress } = {}) {

  const base = apiRoot(baseUrl)

  const chunks = []

  for (let i = 0; i < records.length; i += chunkSize) {

    chunks.push(records.slice(i, i + chunkSize))

  }

  let totalOrders = 0

  let totalItems = 0

  for (let i = 0; i < chunks.length; i++) {

    onProgress?.(`История: пакет ${i + 1} / ${chunks.length}…`)

    let res

    try {

      res = await fetch(`${base}/api/predictions/history/import`, {

      method: 'POST',

      headers: {

        'Content-Type': 'application/json',

        Authorization: `Bearer ${token}`,

      },

      body: JSON.stringify({

        comment: `${comment} (часть ${i + 1}/${chunks.length})`,

        records: chunks[i],

      }),

    })

    } catch (err) {

      throw wrapFetchError(err, baseUrl, 'Загрузка истории')

    }

    const data = await res.json().catch(() => ({}))

    if (!res.ok) throw new Error(data.detail || res.statusText)

    totalOrders += data.orders_created || 0

    totalItems += data.items_created || 0

  }

  return { orders_created: totalOrders, items_created: totalItems, chunks: chunks.length }

}



/**

 * Загрузка полного склада. При hugeHistory — сначала bootstrap без истории, потом чанки history.

 */

export async function uploadFullWarehouse(baseUrl, token, sim, options = {}) {

  const { onProgress, historyChunkSize = 15000, hugeHistoryThreshold = 40000 } = options

  const payload = { ...sim.bootstrapPayload }

  const recordCount = payload.demand_history?.records?.length || 0



  if (recordCount > hugeHistoryThreshold) {

    onProgress?.(`Большой объём истории (${recordCount} записей): загрузка в ${Math.ceil(recordCount / historyChunkSize)} частях…`)

    const history = payload.demand_history

    delete payload.demand_history

    const main = await postBootstrap(baseUrl, token, payload, { onProgress })

    const hist = await postHistoryChunks(

      baseUrl,

      token,

      history.records,

      history.comment,

      historyChunkSize,

      { onProgress },

    )

    return { ...main, history_orders: hist.orders_created, history_items: hist.items_created, history_chunks: hist.chunks }

  }



  return postBootstrap(baseUrl, token, payload, { onProgress })

}


