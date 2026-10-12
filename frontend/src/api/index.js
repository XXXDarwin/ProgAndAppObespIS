import axios from 'axios'

const api = axios.create({
  baseURL: '/api',
  timeout: 15000,
})

// ── Attach access token ────────────────────────────────────────────────────────
api.interceptors.request.use(config => {
  const token = localStorage.getItem('access_token')
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

// ── Auto-refresh on 401 ────────────────────────────────────────────────────────
let isRefreshing = false
let failedQueue = []

const processQueue = (error, token = null) => {
  failedQueue.forEach(p => (error ? p.reject(error) : p.resolve(token)))
  failedQueue = []
}

api.interceptors.response.use(
  res => res,
  async err => {
    const original = err.config
    if (err.response?.status !== 401 || original._retry) {
      return Promise.reject(err)
    }
    if (isRefreshing) {
      return new Promise((resolve, reject) => {
        failedQueue.push({ resolve, reject })
      }).then(token => {
        original.headers.Authorization = `Bearer ${token}`
        return api(original)
      })
    }
    original._retry = true
    isRefreshing = true

    const refreshToken = localStorage.getItem('refresh_token')
    if (!refreshToken) {
      isRefreshing = false
      window.location.href = '/login'
      return Promise.reject(err)
    }

    try {
      const { data } = await axios.post('/api/auth/refresh', { refresh_token: refreshToken })
      localStorage.setItem('access_token', data.access_token)
      processQueue(null, data.access_token)
      original.headers.Authorization = `Bearer ${data.access_token}`
      return api(original)
    } catch (e) {
      processQueue(e, null)
      localStorage.clear()
      window.location.href = '/login'
      return Promise.reject(e)
    } finally {
      isRefreshing = false
    }
  }
)

// ── Auth ───────────────────────────────────────────────────────────────────────
export const authApi = {
  login: (username, password) =>
    api.post('/auth/login', new URLSearchParams({ username, password }), {
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    }),
  me: () => api.get('/auth/me'),
  users: () => api.get('/auth/users'),
  createUser: data => api.post('/auth/users', data),
  deactivateUser: id => api.put(`/auth/users/${id}/deactivate`),
  deleteUser: id => api.delete(`/auth/users/${id}`),
  purgeUser: id => api.delete(`/auth/users/${id}/permanent`),
  resetWarehouse: data => api.post('/auth/system/reset-warehouse', data ?? {}),
}

// ── Products ───────────────────────────────────────────────────────────────────
export const productsApi = {
  list: (params = {}) => api.get('/products/', { params }),
  get: id => api.get(`/products/${id}`),
  bySku: sku => api.get(`/products/by-sku/${sku}`),
  create: data => api.post('/products/', data),
  update: (id, data) => api.patch(`/products/${id}`, data),
  delete: id => api.delete(`/products/${id}`),
  importProductsJson: data => api.post('/products/import', data),
  uploadProducts: (file, skipDuplicates = true) => {
    const form = new FormData()
    form.append('file', file)
    return api.post('/products/upload', form, {
      params: { skip_duplicates: skipDuplicates },
      headers: { 'Content-Type': 'multipart/form-data' },
    })
  },
  categories: () => api.get('/products/categories'),
  createCategory: data => api.post('/products/categories', data),
}

// ── Cells ──────────────────────────────────────────────────────────────────────
export const cellsApi = {
  list: () => api.get('/cells/'),
  create: data => api.post('/cells/', data),
  bulkCreate: data => api.post('/cells/bulk', data),
  deactivate: id => api.delete(`/cells/${id}`),
  deactivateRack: (zone, rack, params = {}) => api.delete(`/cells/zone/${zone}/rack/${rack}`, { params }),
}

// ── Warehouse ──────────────────────────────────────────────────────────────────
export const warehouseApi = {
  stocks: (params = {}) => api.get('/warehouse/stocks', { params }),
  clearStocks: ({ product_id, cell_id } = {}) => {
    const params = {}
    if (product_id != null && Number(product_id) > 0) params.product_id = Number(product_id)
    if (cell_id != null && Number(cell_id) > 0) params.cell_id = Number(cell_id)
    return api.delete('/warehouse/stocks', { params })
  },
  moveStock: data => api.post('/warehouse/move', data),
  orders: (params = {}) => api.get('/warehouse/orders', { params }),
  deleteOrder: id => api.delete(`/warehouse/orders/${id}`),
  deleteOrderHistory: id => api.delete(`/warehouse/orders/${id}/history`),
  getOrder: id => api.get(`/warehouse/orders/${id}`),
  moves: (params = {}) => api.get('/warehouse/moves', { params }),
  deleteMove: id => api.delete(`/warehouse/moves/${id}`),

  createArrivalRequest: data => api.post('/warehouse/arrival/requests', data),
  importArrivalRequestJson: data => api.post('/warehouse/arrival/requests/import', data),
  uploadArrivalRequest: (file, comment) => {
    const form = new FormData()
    form.append('file', file)
    if (comment) form.append('comment', comment)
    return api.post('/warehouse/arrival/requests/upload', form, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
  },
  startArrival: id => api.post(`/warehouse/arrival/${id}/start`),
  completeArrival: (id, data) => api.post(`/warehouse/arrival/${id}/complete`, data),

  createConsumptionRequest: data => api.post('/warehouse/consumption/requests', data),
  importConsumptionRequestJson: data => api.post('/warehouse/consumption/requests/import', data),
  uploadConsumptionRequest: (file, comment) => {
    const form = new FormData()
    form.append('file', file)
    if (comment) form.append('comment', comment)
    return api.post('/warehouse/consumption/requests/upload', form, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
  },
  startConsumption: id => api.post(`/warehouse/consumption/${id}/start`),
  completeConsumption: id => api.post(`/warehouse/consumption/${id}/complete`),
  routeSheet: id => api.get(`/warehouse/consumption/${id}/route`),

  createInventoryRequest: data => api.post('/warehouse/inventory/requests', data),
  createInventory: data => api.post('/warehouse/inventory/requests', data),
  inventoryTasks: id => api.get(`/warehouse/inventory/${id}/tasks`),
  startInventoryTask: (orderId, taskId) => api.post(`/warehouse/inventory/${orderId}/tasks/${taskId}/start`),
  inventoryTaskRoute: (orderId, taskId) => api.get(`/warehouse/inventory/${orderId}/tasks/${taskId}/route`),
  completeInventoryTask: (orderId, taskId, data) =>
    api.post(`/warehouse/inventory/${orderId}/tasks/${taskId}/complete`, data),
  inventoryLosses: id => api.get(`/warehouse/inventory/${id}/losses`),
  startInventory: id => api.post(`/warehouse/inventory/${id}/start`),
  completeInventory: (id, data) => api.post(`/warehouse/inventory/${id}/complete`, data),
  confirmInventory: (id, data) => api.post(`/warehouse/inventory/${id}/confirm`, data),
  inventoryRouteSheet: id => api.get(`/warehouse/inventory/${id}/route`),
}

// ── ML / Predictions ───────────────────────────────────────────────────────────
export const mlApi = {
  methods: () => api.get('/predictions/methods'),
  train: data => api.post('/predictions/train', data),
  trainStatus: () => api.get('/predictions/train/status'),
  forecast: (productId, days = 14, method = 'xgboost') =>
    api.get(`/predictions/forecast/${productId}`, { params: { days, method } }),
  overview: () => api.get('/predictions/overview'),
  models: (params = {}) => api.get('/predictions/models', { params }),
  importHistory: data => api.post('/predictions/history/import', data),
  validate: data => api.post('/predictions/validate', data, { timeout: 300000 }),
  validateCompare: data => api.post('/predictions/validate/compare', data, { timeout: 600000 }),
}

export default api
