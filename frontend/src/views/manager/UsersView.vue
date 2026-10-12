<template>
  <ManagerLayout>
    <div class="space-y-4">
      <div class="flex justify-between items-center gap-3">
        <h2 class="text-lg font-semibold text-gray-700">Пользователи системы</h2>
        <div class="flex items-center gap-2">
          <button v-if="auth.isAdmin" @click="showCreate = true" class="btn-primary">+ Создать</button>
          <div v-if="auth.isAdmin" class="relative" ref="actionsMenuRef">
            <button
              type="button"
              class="btn-secondary px-2.5"
              title="Дополнительные действия"
              aria-label="Дополнительные действия"
              @click="actionsMenuOpen = !actionsMenuOpen"
            >
              <IconMenu />
            </button>
            <div
              v-if="actionsMenuOpen"
              class="absolute right-0 top-full mt-1 w-56 bg-white border border-gray-200 rounded-lg shadow-lg z-20 py-1"
            >
              <button
                type="button"
                class="w-full text-left px-4 py-2 text-sm text-red-700 hover:bg-red-50 disabled:opacity-50"
                :disabled="resettingWarehouse"
                @click="onResetWarehouseClick"
              >
                {{ resettingWarehouse ? 'Очистка...' : 'Очистить данные склада' }}
              </button>
            </div>
          </div>
        </div>
      </div>

      <div class="card p-0 overflow-hidden">
        <div v-if="loading" class="p-6 space-y-2"><div v-for="i in 3" :key="i" class="skeleton h-12 w-full"></div></div>
        <table v-else class="w-full text-sm">
          <thead class="bg-gray-50 border-b text-gray-500">
            <tr>
              <th
                v-for="col in sortColumns"
                :key="col.key"
                class="px-4 py-3 text-left font-medium cursor-pointer select-none hover:text-gray-800 hover:bg-gray-100/80 transition-colors"
                @click="toggleSort(col.key)"
              >
                {{ col.label }}<span v-if="sortKey === col.key" class="text-blue-600 ml-0.5">{{ sortDir === 'asc' ? '↑' : '↓' }}</span>
              </th>
              <th class="px-4 py-3 font-medium text-right">Действия</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-gray-50">
            <tr v-for="u in sortedUsers" :key="u.id" class="hover:bg-gray-50">
              <td class="px-4 py-3 font-mono font-medium text-gray-800">{{ u.username }}</td>
              <td class="px-4 py-3 text-gray-600">{{ u.full_name || '—' }}</td>
              <td class="px-4 py-3">
                <span :class="{ ADMIN: 'badge-red', MANAGER: 'badge-blue', WORKER: 'badge-green' }[u.role] + ' badge'">{{ u.role }}</span>
              </td>
              <td class="px-4 py-3">
                <span :class="u.is_active ? 'badge-green' : 'badge-gray'">{{ u.is_active ? 'Активен' : 'Деактивирован' }}</span>
              </td>
              <td class="px-4 py-3 text-gray-400 text-xs">{{ fmt(u.created_at) }}</td>
              <td class="px-4 py-3 text-right">
                <div class="flex justify-end gap-2">
                  <button
                    v-if="u.is_active"
                    class="btn-secondary"
                    :disabled="deletingId === u.id || isSelf(u)"
                    @click="deleteUser(u)"
                    title="Деактивировать пользователя"
                  >
                    {{ deletingId === u.id ? '...' : 'Удалить' }}
                  </button>
                  <button
                    v-else
                    class="btn-secondary"
                    :disabled="purgingId === u.id || isSelf(u)"
                    @click="purgeUser(u)"
                    title="Удалить из базы без возможности восстановления"
                  >
                    {{ purgingId === u.id ? '...' : 'Удалить навсегда' }}
                  </button>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <!-- Reset warehouse modal -->
      <div
        v-if="showResetWarehouse"
        class="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4"
        @click.self="showResetWarehouse = false"
      >
        <div class="bg-white rounded-2xl shadow-xl w-full max-w-md p-6">
          <h3 class="text-lg font-bold text-red-800 mb-2">Очистить данные склада</h3>
          <p class="text-sm text-gray-600 mb-4">
            Будут удалены: товары, категории, ячейки, остатки, заказы, история, прогнозы ML и журнал аудита.
            Действие необратимо.
          </p>
          <label class="check flex items-start gap-2 mb-4">
            <input
              v-model="resetDeleteUsers"
              type="checkbox"
              class="mt-0.5"
              :disabled="resettingWarehouse"
            />
            <span class="text-sm text-gray-700">
              Удалить вместе с пользователями
              <span class="block text-xs text-gray-500 mt-0.5">
                Останутся только администраторы и ваш текущий вход. Без галочки — все учётные записи сохраняются.
              </span>
            </span>
          </label>
          <div class="flex gap-3">
            <button
              type="button"
              class="btn-primary flex-1 bg-red-600 hover:bg-red-700 border-red-600"
              :disabled="resettingWarehouse"
              @click="confirmResetWarehouse"
            >
              {{ resettingWarehouse ? 'Очистка...' : 'Очистить' }}
            </button>
            <button
              type="button"
              class="btn-secondary flex-1"
              :disabled="resettingWarehouse"
              @click="showResetWarehouse = false"
            >
              Отмена
            </button>
          </div>
        </div>
      </div>

      <!-- Create modal -->
      <div v-if="showCreate" class="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4" @click.self="showCreate=false">
        <div class="bg-white rounded-2xl shadow-xl w-full max-w-sm p-6">
          <h3 class="text-lg font-bold mb-4">Новый пользователь</h3>
          <div class="space-y-3">
            <div><label class="label">Логин *</label><input v-model="form.username" class="input" /></div>
            <div><label class="label">ФИО</label><input v-model="form.full_name" class="input" /></div>
            <div><label class="label">Пароль *</label><input v-model="form.password" type="password" class="input" /></div>
            <div>
              <label class="label">Роль</label>
              <select v-model="form.role" class="input">
                <option value="WORKER">Кладовщик</option>
                <option value="MANAGER">Менеджер</option>
                <option value="ADMIN">Администратор</option>
              </select>
            </div>
          </div>
          <p v-if="createError" class="text-red-500 text-sm mt-2">{{ createError }}</p>
          <div class="flex gap-3 mt-4">
            <button @click="createUser" class="btn-primary flex-1" :disabled="creating">{{ creating ? '...' : 'Создать' }}</button>
            <button @click="showCreate=false" class="btn-secondary flex-1">Отмена</button>
          </div>
        </div>
      </div>
    </div>
  </ManagerLayout>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import ManagerLayout from '@/layouts/ManagerLayout.vue'
import IconMenu from '@/components/IconMenu.vue'
import { authApi } from '@/api'
import { parseApiDetail } from '@/utils/apiError'

const router = useRouter()
const auth = useAuthStore()
const users = ref([])
const loading = ref(true)
const showCreate = ref(false)
const creating = ref(false)
const createError = ref('')
const form = ref({ username: '', full_name: '', password: '', role: 'WORKER' })
const deletingId = ref(null)
const purgingId = ref(null)
const resettingWarehouse = ref(false)
const showResetWarehouse = ref(false)
const resetDeleteUsers = ref(false)
const actionsMenuOpen = ref(false)
const actionsMenuRef = ref(null)

function closeActionsMenu() {
  actionsMenuOpen.value = false
}

function onDocumentClick(e) {
  if (!actionsMenuRef.value?.contains(e.target)) closeActionsMenu()
}

const sortColumns = [
  { key: 'username', label: 'Логин' },
  { key: 'full_name', label: 'ФИО' },
  { key: 'role', label: 'Роль' },
  { key: 'is_active', label: 'Статус' },
  { key: 'created_at', label: 'Создан' },
]
const sortKey = ref('created_at')
const sortDir = ref('desc')

function toggleSort(key) {
  if (sortKey.value === key) {
    sortDir.value = sortDir.value === 'asc' ? 'desc' : 'asc'
  } else {
    sortKey.value = key
    sortDir.value = 'asc'
  }
}

const sortedUsers = computed(() => {
  const list = [...users.value]
  const dir = sortDir.value === 'asc' ? 1 : -1
  const cmp = (a, b) => {
    switch (sortKey.value) {
      case 'full_name':
        return (a.full_name || '').localeCompare(b.full_name || '', 'ru') * dir
      case 'role':
        return (a.role || '').localeCompare(b.role || '') * dir
      case 'is_active':
        return ((a.is_active ? 1 : 0) - (b.is_active ? 1 : 0)) * dir
      case 'created_at':
        return (new Date(a.created_at) - new Date(b.created_at)) * dir
      default:
        return (a.username || '').localeCompare(b.username || '', 'ru') * dir
    }
  }
  list.sort(cmp)
  return list
})

function fmt(dt) { return new Date(dt).toLocaleDateString('ru-RU') }

async function load() {
  loading.value = true
  try { const { data } = await authApi.users(); users.value = data } finally { loading.value = false }
}

async function createUser() {
  creating.value = true; createError.value = ''
  try {
    await authApi.createUser(form.value)
    showCreate.value = false
    form.value = { username: '', full_name: '', password: '', role: 'WORKER' }
    await load()
  } catch(e) { createError.value = e.response?.data?.detail || 'Ошибка' } finally { creating.value = false }
}

function isSelf(u) {
  return auth.user?.id && String(auth.user.id) === String(u.id)
}

async function deleteUser(u) {
  if (isSelf(u)) {
    alert('Нельзя удалить самого себя')
    return
  }
  const ok = confirm(`Деактивировать пользователя ${u.username}? Он не сможет войти в систему.`)
  if (!ok) return
  deletingId.value = u.id
  try {
    await authApi.deleteUser(u.id)
    await load()
  } catch (e) {
    alert(e.response?.data?.detail || 'Ошибка удаления')
  } finally {
    deletingId.value = null
  }
}

async function purgeUser(u) {
  if (isSelf(u)) {
    alert('Нельзя удалить самого себя')
    return
  }
  const ok = confirm(
    `Удалить пользователя ${u.username} навсегда?\n\n` +
    'Запись будет стёрта из базы. Логин можно будет использовать снова. ' +
    'История заказов и аудита сохранится, но без привязки к этому пользователю.',
  )
  if (!ok) return
  purgingId.value = u.id
  try {
    await authApi.purgeUser(u.id)
    await load()
  } catch (e) {
    alert(e.response?.data?.detail || 'Ошибка удаления')
  } finally {
    purgingId.value = null
  }
}
function onResetWarehouseClick() {
  closeActionsMenu()
  resetDeleteUsers.value = false
  showResetWarehouse.value = true
}

async function confirmResetWarehouse() {
  const userPart = resetDeleteUsers.value
    ? 'Пользователи (кроме администраторов) будут удалены.\n\n'
    : 'Учётные записи пользователей будут сохранены.\n\n'
  const ok = confirm(
    'Подтвердите полную очистку склада.\n\n' + userPart + 'Продолжить?',
  )
  if (!ok) return

  resettingWarehouse.value = true
  try {
    const { data } = await authApi.resetWarehouse({ delete_users: resetDeleteUsers.value })
    showResetWarehouse.value = false

    const stats =
      `Удалено: заказов ${data.orders_removed}, товаров ${data.products_removed}, ` +
      `ячеек ${data.cells_removed}, записей аудита ${data.audit_logs_removed}, ` +
      `ML-моделей ${data.ml_models_removed}` +
      (data.users_removed ? `, пользователей ${data.users_removed}` : '')

    if (resetDeleteUsers.value) {
      auth.logout()
      await router.push({ name: 'Login' })
      alert(`${data.detail}\n\n${stats}\n\nВыполнен выход из системы.`)
    } else {
      await load()
      alert(`${data.detail}\n\n${stats}`)
    }
  } catch (e) {
    alert(parseApiDetail(e, 'Ошибка очистки'))
  } finally {
    resettingWarehouse.value = false
  }
}

onMounted(() => {
  document.addEventListener('click', onDocumentClick)
  load()
})

onUnmounted(() => {
  document.removeEventListener('click', onDocumentClick)
})
</script>
