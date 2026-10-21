import axios from 'axios'

// В разработке /iot-api проксирует Vite, в продакшене nginx. Код IoT-сервера не меняется.
const http = axios.create({
  baseURL: import.meta.env.VITE_IOT_API || '/iot-api',
  timeout: 4000,
})

export const fetchClimateStatus = () => http.get('/api/v1/climate/status').then(r => r.data)
export const fetchInventory = () => http.get('/api/v1/inventory').then(r => r.data)
export const fetchAlerts = (limit = 50) => http.get('/api/v1/alerts', { params: { limit } }).then(r => r.data)
export const fetchTelemetry = (limit = 300) => http.get('/api/v1/telemetry', { params: { limit } }).then(r => r.data)