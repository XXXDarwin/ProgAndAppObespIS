import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const routes = [
  { path: '/login', name: 'Login', component: () => import('@/views/LoginView.vue'), meta: { public: true } },

  // Кладовщик
  { path: '/',         name: 'Home',        component: () => import('@/views/worker/HomeView.vue'),        meta: { roles: ['WORKER', 'MANAGER', 'ADMIN'] } },
  { path: '/arrival',  name: 'Arrival',     component: () => import('@/views/worker/ArrivalView.vue'),     meta: { roles: ['WORKER', 'MANAGER', 'ADMIN'] } },
  { path: '/dispatch', name: 'Dispatch',    component: () => import('@/views/worker/DispatchView.vue'),    meta: { roles: ['WORKER', 'MANAGER', 'ADMIN'] } },
  { path: '/consumption-requests', name: 'ConsumptionRequests', component: () => import('@/views/manager/ConsumptionRequestView.vue'), meta: { roles: ['MANAGER', 'ADMIN'], title: 'Заказы на расход' } },
  { path: '/inventory-requests', name: 'InventoryRequests', component: () => import('@/views/manager/InventoryRequestView.vue'), meta: { roles: ['MANAGER', 'ADMIN'], title: 'Инвентаризация' } },
  { path: '/arrival-requests', name: 'ArrivalRequests', component: () => import('@/views/manager/ArrivalRequestView.vue'), meta: { roles: ['MANAGER', 'ADMIN'], title: 'Заказы на приёмку' } },
  { path: '/move',     name: 'Move',        component: () => import('@/views/worker/MoveView.vue'),        meta: { roles: ['WORKER', 'MANAGER', 'ADMIN'] } },
  { path: '/inventory', name: 'Inventory', component: () => import('@/views/worker/InventoryView.vue'), meta: { roles: ['WORKER', 'MANAGER', 'ADMIN'] } },

  // Менеджер / Администратор
  { path: '/dashboard',  name: 'Dashboard',  component: () => import('@/views/manager/DashboardView.vue'),  meta: { roles: ['MANAGER', 'ADMIN'], title: 'Аналитика' } },
  { path: '/stocks',     name: 'Stocks',     component: () => import('@/views/manager/StocksView.vue'),     meta: { roles: ['MANAGER', 'ADMIN'] } },
  { path: '/orders',     name: 'Orders',     component: () => import('@/views/manager/OrdersView.vue'),     meta: { roles: ['MANAGER', 'ADMIN'] } },
  { path: '/moves',      name: 'Moves',      component: () => import('@/views/manager/MovesView.vue'),      meta: { roles: ['MANAGER', 'ADMIN'], title: 'Перемещения' } },
  { path: '/forecast',   name: 'Forecast',   component: () => import('@/views/manager/ForecastView.vue'),   meta: { roles: ['MANAGER', 'ADMIN'], title: 'Прогнозирование' } },
  { path: '/products',   name: 'Products',   component: () => import('@/views/manager/ProductsView.vue'),   meta: { roles: ['MANAGER', 'ADMIN'] } },
  { path: '/cells',         name: 'Cells',        component: () => import('@/views/manager/CellsView.vue'),        meta: { roles: ['MANAGER', 'ADMIN'] } },
  { path: '/warehouse-map', name: 'WarehouseMap', component: () => import('@/views/manager/WarehouseMapView.vue'), meta: { roles: ['MANAGER', 'ADMIN'], title: 'Зоны склада' } },
  { path: '/users',      name: 'Users',      component: () => import('@/views/manager/UsersView.vue'),      meta: { roles: ['ADMIN'], title: 'Пользователи' } },

  { path: '/:pathMatch(.*)*', redirect: '/' },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

router.beforeEach(async to => {
  const auth = useAuthStore()
  if (!auth.isAuthenticated) await auth.init()

  if (to.meta.public) return true

  if (!auth.isAuthenticated) return { name: 'Login' }

  const role = String(auth.user?.role ?? '').toUpperCase()
  if (to.meta.roles && !to.meta.roles.map(r => String(r).toUpperCase()).includes(role)) {
    return auth.isManager ? { name: 'Dashboard' } : { name: 'Home' }
  }

  // Менеджер и админ работают в панели менеджера, не на экране кладовщика
  if (to.name === 'Home' && auth.isManager) {
    return { name: 'Dashboard' }
  }

  return true
})

export default router
