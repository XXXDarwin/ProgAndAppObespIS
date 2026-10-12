<template>
  <ManagerLayout>
    <div class="space-y-4">
      <div class="flex flex-wrap gap-3 items-center">
        <input v-model="search" class="input w-64" placeholder="Поиск по SKU / названию" />
        <select v-model="filterCategoryId" class="input w-52" @change="load">
          <option value="">Все категории</option>
          <option v-for="c in categories" :key="c.id" :value="String(c.id)">{{ c.name }}</option>
        </select>
        <button @click="openCreateProduct" class="btn-primary">+ Добавить товар</button>
        <button @click="showCategoryModal = true" class="btn-secondary">+ Категория</button>
        <button @click="showImport = !showImport" class="btn-secondary">
          {{ showImport ? 'Скрыть импорт' : 'Загрузить из файла' }}
        </button>
      </div>

      <div v-if="showImport" class="card space-y-4 max-w-2xl">
        <p class="text-sm text-gray-500">
          Импорт из .xlsx, .xls, .csv или .json. Обязательные поля: <span class="font-mono">sku</span>, <span class="font-mono">name</span>.
          Опционально: <span class="font-mono">unit</span>, <span class="font-mono">category</span>, <span class="font-mono">weight</span>, <span class="font-mono">description</span>.
        </p>

        <div class="space-y-2">
          <label class="label">Файл</label>
          <input type="file" accept=".xlsx,.xls,.csv,.json" class="input" @change="onFileChange" />
          <label class="flex items-center gap-2 text-sm text-gray-600">
            <input v-model="skipDuplicates" type="checkbox" class="rounded" />
            Пропускать товары с уже существующим SKU
          </label>
          <button class="btn-primary" :disabled="!uploadFile || uploading" @click="submitUpload">
            {{ uploading ? 'Загрузка...' : 'Импортировать из файла' }}
          </button>
        </div>

        <div class="space-y-2 border-t border-gray-100 pt-4">
          <label class="label">JSON</label>
          <p class="text-xs text-gray-400 font-mono">
            { "items": [{ "sku": "ABC-1", "name": "Товар 1", "unit": "шт", "category": "Электроника" }] }
          </p>
          <textarea v-model="jsonText" class="input font-mono text-sm min-h-[100px]" />
          <button class="btn-secondary" :disabled="!jsonText.trim() || importingJson" @click="submitJson">
            {{ importingJson ? 'Импорт...' : 'Импортировать из JSON' }}
          </button>
        </div>

        <div v-if="importResult" class="bg-blue-50 border border-blue-200 rounded-xl p-4 text-sm text-blue-800">
          <div>Добавлено: <strong>{{ importResult.created }}</strong></div>
          <div v-if="importResult.skipped">Пропущено (дубликаты): <strong>{{ importResult.skipped }}</strong></div>
          <ul v-if="importResult.errors?.length" class="mt-2 text-red-600 list-disc pl-5">
            <li v-for="(err, idx) in importResult.errors" :key="idx">{{ err }}</li>
          </ul>
        </div>
        <p v-if="importError" class="text-red-500 text-sm">{{ importError }}</p>
      </div>

      <div class="card p-0 overflow-hidden">
        <div v-if="loading" class="p-6 space-y-2"><div v-for="i in 5" :key="i" class="skeleton h-10 w-full"></div></div>
        <table v-else class="w-full text-sm">
          <thead class="bg-gray-50 border-b text-gray-500">
            <tr>
              <th class="px-4 py-3 text-left font-medium">SKU</th>
              <th class="px-4 py-3 text-left font-medium">Название</th>
              <th class="px-4 py-3 text-left font-medium">Категория</th>
              <th class="px-4 py-3 text-left font-medium">Ед.</th>
              <th class="px-4 py-3 font-medium text-right">Остаток</th>
              <th class="px-4 py-3 font-medium text-right">Действия</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-gray-50">
            <tr v-for="p in filtered" :key="p.id" class="hover:bg-gray-50">
              <td class="px-4 py-2.5 font-mono text-blue-700 font-medium">{{ p.sku }}</td>
              <td class="px-4 py-2.5 text-gray-700">{{ p.name }}</td>
              <td class="px-4 py-2.5">
                <span v-if="p.category?.name" class="badge badge-blue">{{ p.category.name }}</span>
                <span v-else class="text-gray-400 text-xs">Без категории</span>
              </td>
              <td class="px-4 py-2.5 text-gray-400">{{ p.unit }}</td>
              <td class="px-4 py-2.5 text-right font-semibold" :class="(p.total_stock??0) > 0 ? 'text-gray-800' : 'text-red-400'">{{ p.total_stock ?? 0 }}</td>
              <td class="px-4 py-2.5 text-right">
                <div class="flex justify-end gap-2">
                  <button class="btn-secondary" @click="openEditProduct(p)">Изменить</button>
                  <button
                    class="btn-secondary"
                    :disabled="deletingId === p.id"
                    @click="deleteProduct(p)"
                    title="Удалить (деактивировать) товар"
                  >
                    {{ deletingId === p.id ? '...' : 'Удалить' }}
                  </button>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
        <div v-if="!loading && !filtered.length" class="text-center text-gray-400 py-12 text-sm">Нет товаров</div>
      </div>

      <!-- Create product -->
      <div v-if="showCreate" class="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4" @click.self="showCreate=false">
        <div class="bg-white rounded-2xl shadow-xl w-full max-w-md p-6">
          <h3 class="text-lg font-bold mb-4">Новый товар</h3>
          <div class="space-y-3">
            <div><label class="label">SKU *</label><input v-model="form.sku" class="input uppercase" /></div>
            <div><label class="label">Название *</label><input v-model="form.name" class="input" /></div>
            <div>
              <label class="label">Категория</label>
              <select v-model="form.category_id" class="input">
                <option value="">Без категории</option>
                <option v-for="c in categories" :key="c.id" :value="String(c.id)">{{ c.name }}</option>
              </select>
            </div>
            <div><label class="label">Единица</label><input v-model="form.unit" class="input" /></div>
            <div><label class="label">Описание</label><textarea v-model="form.description" class="input" rows="2"></textarea></div>
          </div>
          <p v-if="createError" class="text-red-500 text-sm mt-2">{{ createError }}</p>
          <div class="flex gap-3 mt-4">
            <button @click="createProduct" class="btn-primary flex-1" :disabled="creating">{{ creating ? '...' : 'Создать' }}</button>
            <button @click="showCreate=false" class="btn-secondary flex-1">Отмена</button>
          </div>
        </div>
      </div>

      <!-- Edit product -->
      <div v-if="showEdit" class="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4" @click.self="showEdit=false">
        <div class="bg-white rounded-2xl shadow-xl w-full max-w-md p-6">
          <h3 class="text-lg font-bold mb-4">Изменить товар</h3>
          <p class="text-sm font-mono text-blue-700 mb-3">{{ editForm.sku }}</p>
          <div class="space-y-3">
            <div><label class="label">Название</label><input v-model="editForm.name" class="input" /></div>
            <div>
              <label class="label">Категория</label>
              <select v-model="editForm.category_id" class="input">
                <option value="">Без категории</option>
                <option v-for="c in categories" :key="c.id" :value="String(c.id)">{{ c.name }}</option>
              </select>
            </div>
            <div><label class="label">Единица</label><input v-model="editForm.unit" class="input" /></div>
            <div><label class="label">Описание</label><textarea v-model="editForm.description" class="input" rows="2"></textarea></div>
          </div>
          <p v-if="editError" class="text-red-500 text-sm mt-2">{{ editError }}</p>
          <div class="flex gap-3 mt-4">
            <button @click="saveProduct" class="btn-primary flex-1" :disabled="saving">{{ saving ? '...' : 'Сохранить' }}</button>
            <button @click="showEdit=false" class="btn-secondary flex-1">Отмена</button>
          </div>
        </div>
      </div>

      <!-- Create category -->
      <div v-if="showCategoryModal" class="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4" @click.self="showCategoryModal=false">
        <div class="bg-white rounded-2xl shadow-xl w-full max-w-sm p-6">
          <h3 class="text-lg font-bold mb-4">Новая категория</h3>
          <div>
            <label class="label">Название *</label>
            <input v-model="categoryName" class="input" placeholder="Например: Электроника" @keydown.enter.prevent="createCategory" />
          </div>
          <p v-if="categoryError" class="text-red-500 text-sm mt-2">{{ categoryError }}</p>
          <div class="flex gap-3 mt-4">
            <button @click="createCategory" class="btn-primary flex-1" :disabled="creatingCategory">{{ creatingCategory ? '...' : 'Создать' }}</button>
            <button @click="showCategoryModal=false" class="btn-secondary flex-1">Отмена</button>
          </div>
        </div>
      </div>
    </div>
  </ManagerLayout>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import ManagerLayout from '@/layouts/ManagerLayout.vue'
import { productsApi } from '@/api'
import { parseApiDetail } from '@/utils/apiError'

const products = ref([])
const categories = ref([])
const loading = ref(true)
const search = ref('')
const filterCategoryId = ref('')
const showCreate = ref(false)
const showEdit = ref(false)
const showCategoryModal = ref(false)
const creating = ref(false)
const saving = ref(false)
const creatingCategory = ref(false)
const createError = ref('')
const editError = ref('')
const categoryError = ref('')
const categoryName = ref('')
const form = ref({ sku: '', name: '', unit: 'шт', description: '', category_id: '' })
const editForm = ref({ id: null, sku: '', name: '', unit: 'шт', description: '', category_id: '' })
const deletingId = ref(null)
const showImport = ref(false)
const uploadFile = ref(null)
const jsonText = ref('')
const uploading = ref(false)
const importingJson = ref(false)
const skipDuplicates = ref(true)
const importResult = ref(null)
const importError = ref('')

function emptyProductForm() {
  return { sku: '', name: '', unit: 'шт', description: '', category_id: '' }
}

function parseCategoryId(value) {
  if (value === '' || value == null) return null
  const id = Number(value)
  return Number.isFinite(id) && id > 0 ? id : null
}

function buildProductPayload(data) {
  const payload = {
    sku: data.sku?.trim().toUpperCase(),
    name: data.name?.trim(),
    unit: data.unit?.trim() || 'шт',
  }
  const description = data.description?.trim()
  if (description) payload.description = description
  const category_id = parseCategoryId(data.category_id)
  if (category_id != null) payload.category_id = category_id
  return payload
}

function onFileChange(e) {
  uploadFile.value = e.target.files?.[0] || null
  importError.value = ''
  importResult.value = null
}

async function loadCategories() {
  try {
    const { data } = await productsApi.categories()
    categories.value = data || []
  } catch {
    categories.value = []
  }
}

async function submitUpload() {
  if (!uploadFile.value) return
  uploading.value = true
  importError.value = ''
  importResult.value = null
  try {
    const { data } = await productsApi.uploadProducts(uploadFile.value, skipDuplicates.value)
    importResult.value = data
    uploadFile.value = null
    await load()
  } catch (e) {
    importError.value = parseApiDetail(e, 'Ошибка загрузки')
  } finally {
    uploading.value = false
  }
}

async function submitJson() {
  importingJson.value = true
  importError.value = ''
  importResult.value = null
  try {
    const payload = JSON.parse(jsonText.value)
    if (payload.skip_duplicates === undefined) payload.skip_duplicates = skipDuplicates.value
    const { data } = await productsApi.importProductsJson(payload)
    importResult.value = data
    jsonText.value = ''
    await load()
  } catch (e) {
    importError.value = parseApiDetail(e, e instanceof SyntaxError ? 'Некорректный JSON' : 'Ошибка импорта')
  } finally {
    importingJson.value = false
  }
}

const filtered = computed(() => {
  const q = search.value.toLowerCase().trim()
  if (!q) return products.value
  return products.value.filter(p =>
    p.sku.toLowerCase().includes(q) ||
    p.name.toLowerCase().includes(q) ||
    (p.category?.name || '').toLowerCase().includes(q),
  )
})

async function load() {
  loading.value = true
  try {
    const params = { active_only: true }
    if (filterCategoryId.value) params.category_id = Number(filterCategoryId.value)
    const { data } = await productsApi.list(params)
    products.value = data
  } finally {
    loading.value = false
  }
}

function openCreateProduct() {
  form.value = emptyProductForm()
  createError.value = ''
  showCreate.value = true
}

function openEditProduct(p) {
  editForm.value = {
    id: p.id,
    sku: p.sku,
    name: p.name,
    unit: p.unit || 'шт',
    description: p.description || '',
    category_id: p.category?.id != null ? String(p.category.id) : '',
  }
  editError.value = ''
  showEdit.value = true
}

async function createProduct() {
  creating.value = true
  createError.value = ''
  try {
    await productsApi.create(buildProductPayload(form.value))
    showCreate.value = false
    form.value = emptyProductForm()
    await load()
  } catch (e) {
    createError.value = parseApiDetail(e, 'Ошибка')
  } finally {
    creating.value = false
  }
}

async function saveProduct() {
  saving.value = true
  editError.value = ''
  try {
    const payload = {
      name: editForm.value.name?.trim(),
      unit: editForm.value.unit?.trim() || 'шт',
      description: editForm.value.description?.trim() || null,
      category_id: parseCategoryId(editForm.value.category_id),
    }
    await productsApi.update(editForm.value.id, payload)
    showEdit.value = false
    await load()
  } catch (e) {
    editError.value = parseApiDetail(e, 'Ошибка сохранения')
  } finally {
    saving.value = false
  }
}

async function createCategory() {
  const name = categoryName.value.trim()
  if (!name) {
    categoryError.value = 'Введите название категории'
    return
  }
  creatingCategory.value = true
  categoryError.value = ''
  try {
    await productsApi.createCategory({ name })
    categoryName.value = ''
    showCategoryModal.value = false
    await loadCategories()
  } catch (e) {
    categoryError.value = parseApiDetail(e, 'Ошибка')
  } finally {
    creatingCategory.value = false
  }
}

async function deleteProduct(p) {
  const stock = p.total_stock ?? 0
  if (stock > 0) {
    alert(`Нельзя удалить товар: на складе есть остатки (${stock} ед.)`)
    return
  }
  const ok = confirm(`Удалить товар ${p.sku} — "${p.name}"?`)
  if (!ok) return
  deletingId.value = p.id
  try {
    await productsApi.delete(p.id)
    await load()
  } catch (e) {
    alert(parseApiDetail(e, 'Ошибка удаления'))
  } finally {
    deletingId.value = null
  }
}

onMounted(async () => {
  await loadCategories()
  await load()
})
</script>
