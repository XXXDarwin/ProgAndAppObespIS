<template>
  <ManagerLayout>
    <div class="space-y-4">
      <div class="flex gap-3">
        <button @click="showBulk = true" class="btn-primary">+ Создать ячейки</button>
        <button @click="showRackDelete = true" class="btn-secondary">Удалить стеллаж</button>
        <button @click="load" class="btn-secondary">Обновить</button>
      </div>

      <!-- Stats -->
      <div class="grid grid-cols-3 gap-3">
        <div class="card text-center">
          <div class="text-2xl font-bold text-blue-700">{{ cells.length }}</div>
          <div class="text-xs text-gray-400 mt-0.5">Всего ячеек</div>
        </div>
        <div class="card text-center">
          <div class="text-2xl font-bold text-green-700">{{ cells.filter(c => c.current_stock > 0).length }}</div>
          <div class="text-xs text-gray-400 mt-0.5">Занято</div>
        </div>
        <div class="card text-center">
          <div class="text-2xl font-bold text-gray-700">{{ cells.filter(c => c.current_stock === 0).length }}</div>
          <div class="text-xs text-gray-400 mt-0.5">Свободно</div>
        </div>
      </div>

      <div class="card p-0 overflow-hidden">
        <div v-if="loading" class="p-6 space-y-2"><div v-for="i in 6" :key="i" class="skeleton h-10 w-full"></div></div>
        <table v-else class="w-full text-sm">
          <thead class="bg-gray-50 border-b text-gray-500">
            <tr>
              <th class="px-4 py-3 text-left font-medium">Адрес</th>
              <th class="px-4 py-3 text-left font-medium">Зона</th>
              <th class="px-4 py-3 font-medium text-right">Занято</th>
              <th class="px-4 py-3 font-medium text-right">Свободно</th>
              <th class="px-4 py-3 font-medium text-right">Макс.</th>
              <th class="px-4 py-3 font-medium text-right">Действия</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-gray-50">
            <tr v-for="c in cells" :key="c.id" class="hover:bg-gray-50">
              <td class="px-4 py-2.5 font-mono font-medium text-gray-800">{{ c.address }}</td>
              <td class="px-4 py-2.5"><span class="badge badge-blue">{{ c.zone }}</span></td>
              <td class="px-4 py-2.5 text-right font-semibold" :class="c.current_stock > 0 ? 'text-blue-700' : 'text-gray-300'">{{ c.current_stock }}</td>
              <td class="px-4 py-2.5 text-right text-green-700">{{ c.free_capacity }}</td>
              <td class="px-4 py-2.5 text-right text-gray-400">{{ c.max_capacity }}</td>
              <td class="px-4 py-2.5 text-right">
                <button
                  class="btn-secondary"
                  :disabled="deletingId === c.id"
                  @click="deleteCell(c)"
                  title="Удалить (деактивировать) ячейку"
                >
                  {{ deletingId === c.id ? '...' : 'Удалить' }}
                </button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <!-- Delete rack modal -->
      <div
        v-if="showRackDelete"
        class="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4"
        @click.self="showRackDelete=false"
      >
        <div class="bg-white rounded-2xl shadow-xl w-full max-w-md p-6">
          <h3 class="text-lg font-bold mb-4">Удалить стеллаж</h3>
          <div class="space-y-3 text-sm">
            <div class="grid grid-cols-2 gap-2">
              <div>
                <label class="label">Зона</label>
                <select v-model="rackForm.zone" class="input">
                  <option v-for="z in zones" :key="z" :value="z">{{ z }}</option>
                </select>
              </div>
              <div>
                <label class="label">Стеллаж</label>
                <select v-model.number="rackForm.rack" class="input">
                  <option v-for="r in racksForZone" :key="r" :value="r">{{ r }}</option>
                </select>
              </div>
            </div>

            <label class="flex items-center gap-2 text-gray-700 select-none">
              <input v-model="rackForm.forceClear" type="checkbox" />
              <span>Сначала очистить остатки в ячейках этого стеллажа</span>
            </label>

            <p class="text-xs text-gray-500">
              Будут деактивированы все ячейки в выбранной зоне/стеллаже.
              <span v-if="!rackForm.forceClear" class="text-gray-500">Если есть товары — операция будет запрещена.</span>
            </p>
          </div>

          <p v-if="rackError" class="text-red-500 text-sm mt-2">{{ rackError }}</p>
          <div class="flex gap-3 mt-4">
            <button @click="deleteRack" class="btn-primary flex-1" :disabled="rackDeleting">
              {{ rackDeleting ? '...' : 'Удалить' }}
            </button>
            <button @click="showRackDelete=false" class="btn-secondary flex-1">Отмена</button>
          </div>
        </div>
      </div>

      <!-- Bulk create modal -->
      <div v-if="showBulk" class="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4" @click.self="showBulk=false">
        <div class="bg-white rounded-2xl shadow-xl w-full max-w-md p-6">
          <h3 class="text-lg font-bold mb-4">Массовое создание ячеек</h3>
          <div class="space-y-3 text-sm">
            <div><label class="label">Зоны (через запятую)</label><input v-model="bulkForm.zones" class="input" placeholder="A, B, C" /></div>
            <div class="grid grid-cols-3 gap-2">
              <div><label class="label">Стеллажей</label><input v-model.number="bulkForm.racks" type="number" class="input" min="1" /></div>
              <div><label class="label">Полок</label><input v-model.number="bulkForm.shelves" type="number" class="input" min="1" /></div>
              <div><label class="label">Позиций</label><input v-model.number="bulkForm.positions" type="number" class="input" min="1" /></div>
            </div>
            <div><label class="label">Вместимость</label><input v-model.number="bulkForm.capacity" type="number" class="input" /></div>
            <p class="text-gray-500 text-xs">Будет создано: <strong>{{ totalCells }}</strong> ячеек</p>
          </div>
          <p v-if="bulkError" class="text-red-500 text-sm mt-2">{{ bulkError }}</p>
          <div class="flex gap-3 mt-4">
            <button @click="bulkCreate" class="btn-primary flex-1" :disabled="bulkCreating">{{ bulkCreating ? '...' : 'Создать' }}</button>
            <button @click="showBulk=false" class="btn-secondary flex-1">Отмена</button>
          </div>
        </div>
      </div>
    </div>
  </ManagerLayout>
</template>

<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import ManagerLayout from '@/layouts/ManagerLayout.vue'
import { cellsApi } from '@/api'

const cells = ref([])
const loading = ref(true)
const showBulk = ref(false)
const showRackDelete = ref(false)
const bulkCreating = ref(false)
const bulkError = ref('')
const bulkForm = ref({ zones: 'A, B', racks: 3, shelves: 4, positions: 5, capacity: 100 })
const deletingId = ref(null)

const rackForm = ref({ zone: 'A', rack: 1, forceClear: false })
const rackDeleting = ref(false)
const rackError = ref('')

const zones = computed(() => {
  const z = new Set(cells.value.map(c => String(c.zone).toUpperCase()))
  return [...z].sort()
})

const racksForZone = computed(() => {
  const z = String(rackForm.value.zone || '').toUpperCase()
  const r = new Set(cells.value.filter(c => String(c.zone).toUpperCase() === z).map(c => Number(c.rack)))
  return [...r].sort((a, b) => a - b)
})

const totalCells = computed(() => {
  const zones = bulkForm.value.zones.split(',').filter(z => z.trim()).length
  return zones * bulkForm.value.racks * bulkForm.value.shelves * bulkForm.value.positions
})

async function load() {
  loading.value = true
  try {
    const { data } = await cellsApi.list()
    cells.value = data
    // Инициализация дефолтов в модалке удаления стеллажа
    if (zones.value.length && !zones.value.includes(rackForm.value.zone)) {
      rackForm.value.zone = zones.value[0]
    }
    if (racksForZone.value.length && !racksForZone.value.includes(rackForm.value.rack)) {
      rackForm.value.rack = racksForZone.value[0]
    }
  } finally {
    loading.value = false
  }
}

async function bulkCreate() {
  bulkCreating.value = true; bulkError.value = ''
  try {
    const zones = bulkForm.value.zones.split(',').map(z => z.trim()).filter(Boolean)
    await cellsApi.bulkCreate({ zones, racks_per_zone: bulkForm.value.racks, shelves_per_rack: bulkForm.value.shelves, positions_per_shelf: bulkForm.value.positions, max_capacity: bulkForm.value.capacity })
    showBulk.value = false
    await load()
  } catch(e) { bulkError.value = e.response?.data?.detail || 'Ошибка' } finally { bulkCreating.value = false }
}

async function deleteCell(c) {
  if ((c.current_stock ?? 0) > 0) {
    alert(`Нельзя удалить ячейку ${c.address}: в ней есть товары (${c.current_stock} ед.)`)
    return
  }
  const ok = confirm(`Удалить ячейку ${c.address}?`)
  if (!ok) return
  deletingId.value = c.id
  try {
    await cellsApi.deactivate(c.id)
    await load()
  } catch (e) {
    alert(e.response?.data?.detail || 'Ошибка удаления')
  } finally {
    deletingId.value = null
  }
}

watch(
  () => rackForm.value.zone,
  () => {
    if (racksForZone.value.length) rackForm.value.rack = racksForZone.value[0]
  }
)

async function deleteRack() {
  rackError.value = ''
  const zone = String(rackForm.value.zone || '').toUpperCase()
  const rack = Number(rackForm.value.rack)
  if (!zone || !rack) {
    rackError.value = 'Выберите зону и стеллаж'
    return
  }
  const ok = confirm(
    `Удалить стеллаж ${zone}-${rack} и деактивировать все ячейки в нём?` +
      (rackForm.value.forceClear ? ' (С очисткой остатков)' : '')
  )
  if (!ok) return

  rackDeleting.value = true
  try {
    await cellsApi.deactivateRack(zone, rack, { force_clear_stock: rackForm.value.forceClear })
    showRackDelete.value = false
    await load()
  } catch (e) {
    rackError.value = e.response?.data?.detail || 'Ошибка удаления стеллажа'
  } finally {
    rackDeleting.value = false
  }
}
onMounted(load)
</script>
