<template>
  <ManagerLayout>
    <div class="space-y-5">
      <div class="flex justify-end">
        <div class="relative shrink-0" ref="actionsMenuRef">
          <button
            type="button"
            class="btn-secondary px-2.5"
            title="Сводка и обучение моделей"
            aria-label="Сводка и обучение моделей"
            @click="actionsMenuOpen = !actionsMenuOpen"
          >
            <IconMenu />
          </button>
          <div
            v-if="actionsMenuOpen"
            class="absolute right-0 top-full mt-1 w-72 bg-white border border-gray-200 rounded-lg shadow-lg z-20 py-1 max-h-[85vh] overflow-y-auto"
          >
            <div v-if="overview" class="px-4 py-3 border-b border-gray-100 space-y-2.5 text-sm">
              <div class="text-xs font-semibold text-gray-500 uppercase tracking-wide">Сводка ML</div>
              <div class="flex justify-between gap-4">
                <span class="text-gray-600">Товаров</span>
                <span class="font-bold text-gray-800">{{ overview.total_products }}</span>
              </div>
              <div class="flex justify-between gap-4">
                <span class="text-gray-600">Моделей готово</span>
                <span class="font-bold text-green-700">{{ overview.models_ready }}</span>
              </div>
              <div class="flex justify-between gap-4">
                <span class="text-gray-600">Можно обучить</span>
                <span class="font-bold text-blue-700">{{ overview.history_ready }}</span>
              </div>
              <div class="text-xs text-gray-400 -mt-1">≥ 14 дней истории расхода</div>
              <div class="flex justify-between gap-4 pt-1 border-t border-gray-50">
                <span class="text-gray-600">Обучение</span>
                <span class="font-semibold" :class="trainingStatusClass">{{ trainingStatusLabel }}</span>
              </div>
            </div>
            <div v-else class="px-4 py-3 border-b border-gray-100 text-sm text-gray-400">
              Загрузка сводки…
            </div>
            <div class="px-4 py-3 border-b border-gray-100">
              <label class="label text-xs mb-1.5">Модель прогноза</label>
              <select
                v-if="availableForecastMethods.length"
                v-model="forecastMethod"
                class="input w-full text-sm"
                @change="onForecastMethodChange"
              >
                <option
                  v-for="m in availableForecastMethods"
                  :key="m.id"
                  :value="m.id"
                  :title="m.description"
                >
                  {{ m.label }}
                </option>
              </select>
              <div v-else class="text-xs text-gray-400">Загрузка…</div>
            </div>
            <button
              type="button"
              class="w-full text-left px-4 py-2 text-sm text-gray-700 hover:bg-gray-50 disabled:opacity-50"
              :disabled="trainingStatus === 'running' || !selectedMethodRequiresTraining"
              :title="!selectedMethodRequiresTraining ? 'Только для XGBoost' : ''"
              @click="onTrainClick(false)"
            >
              {{ trainingStatus === 'running' ? 'Обучение...' : 'Обучить все модели' }}
            </button>
            <button
              type="button"
              class="w-full text-left px-4 py-2 text-sm text-gray-700 hover:bg-gray-50 disabled:opacity-50"
              :disabled="trainingStatus === 'running' || !filterCategoryId || !selectedMethodRequiresTraining"
              @click="onTrainClick(true)"
            >
              Обучить категорию
            </button>
            <button
              type="button"
              class="w-full text-left px-4 py-2 text-sm text-gray-700 hover:bg-gray-50 disabled:opacity-50"
              :disabled="trainingStatus === 'running' || !selectedMethodRequiresTraining"
              @click="onTrainForce"
            >
              Переобучить принудительно
            </button>
            <label class="block w-full text-left px-4 py-2 text-sm text-gray-700 hover:bg-gray-50 cursor-pointer">
              Импорт истории
              <input type="file" accept=".json" class="hidden" @change="onImportClick" />
            </label>
            <button
              type="button"
              class="w-full text-left px-4 py-2 text-sm text-gray-700 hover:bg-gray-50 border-t border-gray-100"
              @click="openValidationModal"
            >
              Диагностика и метрики качества
            </button>
          </div>
        </div>
      </div>

      <!-- Validation sandbox modal -->
      <div
        v-if="showValidation"
        class="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4"
        @click.self="closeValidationModal"
      >
        <div class="bg-white rounded-xl shadow-xl w-full max-w-5xl max-h-[90vh] flex flex-col">
          <div class="px-5 py-4 border-b border-gray-100 flex items-start justify-between gap-4">
            <div>
              <h2 class="text-lg font-semibold text-gray-800">Диагностика качества моделей</h2>
              <p class="text-sm text-gray-500 mt-1">
                Holdout-валидация на истории расхода. Одна модель — из меню ⋮; «Все модели» — сравнение сразу по всем доступным методам.
              </p>
            </div>
            <button type="button" class="text-gray-400 hover:text-gray-600 text-xl leading-none" @click="closeValidationModal">
              ×
            </button>
          </div>

          <div class="px-5 py-4 border-b border-gray-50 flex flex-wrap gap-3 items-end">
            <div>
              <label class="label">Тестовая выборка</label>
              <select v-model.number="validationTestSize" class="input w-40" :disabled="validationLoading">
                <option :value="0.1">10%</option>
                <option :value="0.2">20%</option>
                <option :value="0.3">30%</option>
                <option :value="0.4">40%</option>
              </select>
            </div>
            <div>
              <label class="label">Товар</label>
              <select v-model="validationProductId" class="input w-64" :disabled="validationLoading">
                <option value="">Все товары</option>
                <option v-for="p in filteredProducts" :key="p.id" :value="String(p.id)">
                  {{ p.sku }} · {{ p.name }}
                </option>
              </select>
            </div>
            <button
              type="button"
              class="btn-primary"
              :disabled="validationLoading"
              @click="runValidationAll"
            >
              {{ validationLoading && validationMode === 'all' ? 'Сравнение моделей...' : 'Все модели' }}
            </button>
            <button
              type="button"
              class="btn-secondary"
              :disabled="validationLoading"
              @click="runValidation"
            >
              {{ validationLoading && validationMode === 'single' ? 'Валидация...' : `Модель: ${selectedMethodMeta?.label || forecastMethod}` }}
            </button>
            <button
              type="button"
              class="btn-secondary"
              :disabled="validationLoading || !validationHasData"
              @click="toggleValidationJson"
            >
              {{ showValidationJson ? 'Скрыть JSON' : 'Сводка JSON' }}
            </button>
            <button
              type="button"
              class="btn-secondary text-sm"
              :disabled="validationLoading || !validationHasData"
              title="Копировать в буфер"
              @click="copyValidationJson"
            >
              Копировать
            </button>
            <button
              type="button"
              class="btn-secondary text-sm"
              :disabled="validationLoading || !validationHasData"
              title="Скачать .json"
              @click="downloadValidationJson"
            >
              Скачать
            </button>
          </div>

          <div
            v-if="validationJsonMsg"
            class="mx-5 mt-2 text-xs px-3 py-1.5 rounded-lg"
            :class="validationJsonMsgOk ? 'bg-green-50 text-green-800' : 'bg-red-50 text-red-700'"
          >
            {{ validationJsonMsg }}
          </div>

          <div v-if="showValidationJson && validationJsonText" class="mx-5 mt-2 mb-0 border border-gray-200 rounded-lg bg-gray-50 overflow-hidden">
            <pre class="text-xs p-3 overflow-auto max-h-48 text-gray-800 font-mono whitespace-pre">{{ validationJsonText }}</pre>
          </div>

          <div class="px-5 py-3 overflow-y-auto flex-1 space-y-4">
            <div v-if="validationError" class="text-sm px-3 py-2 rounded-lg bg-yellow-50 text-yellow-800">
              {{ validationError }}
            </div>

            <div v-if="validationCompareResult" class="text-sm text-gray-600">
              Сравнение {{ validationCompareResult.methods_total }} моделей ·
              {{ formatValidatedAt(validationCompareResult.validated_at) }}
              · test_size: {{ Math.round(validationCompareResult.test_size * 100) }}%
            </div>

            <div v-if="validationMethodRuns.length" class="overflow-x-auto">
              <h3 class="text-sm font-semibold text-gray-700 mb-2">Сравнение моделей (средние метрики)</h3>
              <table class="w-full text-sm">
                <thead>
                  <tr class="text-left text-gray-400 border-b">
                    <th class="pb-2 font-medium">Модель</th>
                    <th class="pb-2 font-medium text-right">SKU OK</th>
                    <th class="pb-2 font-medium text-right">MAE</th>
                    <th class="pb-2 font-medium text-right">RMSE</th>
                    <th class="pb-2 font-medium text-right">MAPE %</th>
                    <th class="pb-2 font-medium text-right">R²</th>
                  </tr>
                </thead>
                <tbody class="divide-y divide-gray-50">
                  <tr
                    v-for="(run, idx) in validationMethodRuns"
                    :key="run.forecast_method"
                    class="hover:bg-gray-50 cursor-pointer"
                    :class="validationDetailMethod === run.forecast_method ? 'bg-blue-50' : ''"
                    @click="validationDetailMethod = run.forecast_method"
                  >
                    <td class="py-2 text-gray-800">
                      {{ run.forecast_method_label || run.forecast_method }}
                      <span v-if="idx === 0 && run.avg_mae != null" class="ml-1 text-xs text-green-600">лучший MAE</span>
                    </td>
                    <td class="py-2 text-right">{{ run.products_validated }} / {{ run.products_total }}</td>
                    <td class="py-2 text-right font-mono">{{ fmtMetric(run.avg_mae) }}</td>
                    <td class="py-2 text-right font-mono">{{ fmtMetric(run.avg_rmse) }}</td>
                    <td class="py-2 text-right font-mono">{{ fmtMetric(run.avg_mape) }}</td>
                    <td class="py-2 text-right font-mono">{{ fmtMetric(run.avg_r2) }}</td>
                  </tr>
                </tbody>
              </table>
              <p class="text-xs text-gray-400 mt-2">Нажмите строку, чтобы увидеть детали по категориям и SKU.</p>
            </div>

            <div v-if="validationSkuMatrix.length && validationCompareResult" class="overflow-x-auto">
              <h3 class="text-sm font-semibold text-gray-700 mb-2">MAE по артикулам (все модели)</h3>
              <table class="w-full text-sm">
                <thead>
                  <tr class="text-left text-gray-400 border-b">
                    <th class="pb-2 font-medium">SKU</th>
                    <th
                      v-for="run in validationMethodRuns"
                      :key="run.forecast_method"
                      class="pb-2 font-medium text-right whitespace-nowrap"
                    >
                      {{ run.forecast_method_label || run.forecast_method }}
                    </th>
                  </tr>
                </thead>
                <tbody class="divide-y divide-gray-50">
                  <tr v-for="row in validationSkuMatrix" :key="row.product_id" class="hover:bg-gray-50">
                    <td class="py-2 font-mono text-blue-700">{{ row.product_sku }}</td>
                    <td
                      v-for="run in validationMethodRuns"
                      :key="run.forecast_method"
                      class="py-2 text-right font-mono"
                    >
                      {{ fmtMetric(row.metrics[run.forecast_method]) }}
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>

            <div v-if="validationResult && !validationCompareResult" class="text-sm text-gray-600 space-y-1">
              <div>
                {{ validationResult.forecast_method_label || validationResult.forecast_method }} ·
                {{ formatValidatedAt(validationResult.validated_at) }}
                · test_size: {{ Math.round(validationResult.test_size * 100) }}%
                · успешно: {{ validationResult.products_validated }} / {{ validationResult.products_total }}
                <span v-if="validationResult.products_skipped" class="text-gray-400">
                  (пропущено: {{ validationResult.products_skipped }})
                </span>
              </div>
            </div>

            <div v-if="validationCategories.length" class="overflow-x-auto">
              <h3 class="text-sm font-semibold text-gray-700 mb-2">
                Сводка по категориям
                <span v-if="validationActiveRun" class="font-normal text-gray-500">
                  — {{ validationActiveRun.forecast_method_label }}
                </span>
              </h3>
              <table class="w-full text-sm">
                <thead>
                  <tr class="text-left text-gray-400 border-b">
                    <th class="pb-2 font-medium">Категория</th>
                    <th class="pb-2 font-medium text-right">SKU</th>
                    <th class="pb-2 font-medium text-right">MAE</th>
                    <th class="pb-2 font-medium text-right">RMSE</th>
                    <th class="pb-2 font-medium text-right">MAPE %</th>
                    <th class="pb-2 font-medium text-right">R²</th>
                  </tr>
                </thead>
                <tbody class="divide-y divide-gray-50">
                  <tr v-for="c in validationCategories" :key="c.category_id ?? 'none'" class="hover:bg-gray-50">
                    <td class="py-2 text-gray-700">{{ c.category_name }}</td>
                    <td class="py-2 text-right">{{ c.products_validated }}</td>
                    <td class="py-2 text-right font-mono">{{ fmtMetric(c.avg_mae) }}</td>
                    <td class="py-2 text-right font-mono">{{ fmtMetric(c.avg_rmse) }}</td>
                    <td class="py-2 text-right font-mono">{{ fmtMetric(c.avg_mape) }}</td>
                    <td class="py-2 text-right font-mono">{{ fmtMetric(c.avg_r2) }}</td>
                  </tr>
                </tbody>
              </table>
            </div>

            <div v-if="validationRows.length" class="overflow-x-auto">
              <h3 class="text-sm font-semibold text-gray-700 mb-2">
                Метрики по артикулам
                <span v-if="validationActiveRun" class="font-normal text-gray-500">
                  — {{ validationActiveRun.forecast_method_label }}
                </span>
              </h3>
              <table class="w-full text-sm">
                <thead>
                  <tr class="text-left text-gray-400 border-b">
                    <th class="pb-2 font-medium">SKU</th>
                    <th class="pb-2 font-medium">Категория</th>
                    <th class="pb-2 font-medium text-right">Train</th>
                    <th class="pb-2 font-medium text-right">Test</th>
                    <th class="pb-2 font-medium text-right">MAE</th>
                    <th class="pb-2 font-medium text-right">RMSE</th>
                    <th class="pb-2 font-medium text-right">MAPE %</th>
                    <th class="pb-2 font-medium text-right">R²</th>
                    <th class="pb-2 font-medium">Статус</th>
                  </tr>
                </thead>
                <tbody class="divide-y divide-gray-50">
                  <tr v-for="r in validationRows" :key="r.product_id" class="hover:bg-gray-50">
                    <td class="py-2 font-mono text-blue-700">{{ r.product_sku }}</td>
                    <td class="py-2">
                      <span v-if="r.category" class="badge badge-blue">{{ r.category.name }}</span>
                      <span v-else class="text-gray-400 text-xs">—</span>
                    </td>
                    <td class="py-2 text-right text-gray-600">{{ r.train_days || '—' }}</td>
                    <td class="py-2 text-right text-gray-600">{{ r.test_days || '—' }}</td>
                    <td class="py-2 text-right font-mono">{{ fmtMetric(r.mae) }}</td>
                    <td class="py-2 text-right font-mono">{{ fmtMetric(r.rmse) }}</td>
                    <td class="py-2 text-right font-mono">{{ fmtMetric(r.mape) }}</td>
                    <td class="py-2 text-right font-mono">{{ fmtMetric(r.r2) }}</td>
                    <td class="py-2">
                      <span v-if="r.status === 'ok'" class="text-green-600 text-xs">OK</span>
                      <span v-else class="text-amber-600 text-xs" :title="r.skip_reason">{{ skipLabel(r.skip_reason) }}</span>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>

            <div v-else-if="!validationLoading && !validationError" class="text-center py-10 text-gray-400 text-sm">
              Задайте долю тестовой выборки и нажмите «Все модели» или валидацию выбранной модели.
            </div>
          </div>
        </div>
      </div>

      <div class="flex flex-wrap gap-3 items-end">
        <div>
          <label class="label">Категория</label>
          <select v-model="filterCategoryId" class="input w-48" @change="onCategoryFilterChange">
            <option value="">Все категории</option>
            <option v-for="c in categories" :key="c.id" :value="String(c.id)">{{ c.name }}</option>
          </select>
        </div>
        <div>
          <label class="label">Товар</label>
          <select v-model="selectedProductId" class="input w-72">
            <option value="">— Выберите товар —</option>
            <option v-for="p in filteredProducts" :key="p.id" :value="p.id">
              {{ p.sku }} · {{ p.name }}{{ p.category?.name ? ` (${p.category.name})` : '' }}
            </option>
          </select>
        </div>
        <div>
          <label class="label">Поиск</label>
          <input v-model="productSearch" type="text" class="input w-48" placeholder="SKU / название" />
        </div>
        <div>
          <label class="label">Горизонт (дней)</label>
          <select v-model="days" class="input w-32">
            <option :value="7">7 дней</option>
            <option :value="14">14 дней</option>
            <option :value="30">30 дней</option>
          </select>
        </div>
        <button @click="loadForecast" class="btn-primary" :disabled="!selectedProductId || forecastLoading">
          {{ forecastLoading ? 'Загрузка...' : 'Построить прогноз' }}
        </button>
      </div>

      <div v-if="importMsg" class="text-sm px-3 py-2 rounded-lg"
        :class="importOk ? 'bg-green-50 text-green-700' : 'bg-yellow-50 text-yellow-800'">
        {{ importMsg }}
      </div>
      <div v-if="trainingMsg" class="text-sm px-3 py-2 rounded-lg"
        :class="trainingStatus === 'done' ? 'bg-green-50 text-green-700' : 'bg-blue-50 text-blue-700'">
        {{ trainingMsg }}
      </div>
      <div v-if="forecastError" class="bg-yellow-50 border border-yellow-200 text-yellow-800 rounded-xl p-4 text-sm">
        {{ forecastError }}
      </div>

      <!-- Insights -->
      <div v-if="forecast?.insights" class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
        <div class="card py-3">
          <div class="text-xs text-gray-500">Остаток на складе</div>
          <div class="text-lg font-bold text-gray-800">{{ forecast.insights.total_stock }} ед.</div>
        </div>
        <div class="card py-3">
          <div class="text-xs text-gray-500">Ср. расход / 14 дн.</div>
          <div class="text-lg font-bold text-gray-800">{{ forecast.insights.avg_daily_demand_14d }}</div>
        </div>
        <div class="card py-3">
          <div class="text-xs text-gray-500">Прогноз на период</div>
          <div class="text-lg font-bold text-gray-800">{{ forecast.insights.forecast_total }} ед.</div>
        </div>
        <div class="card py-3">
          <div class="text-xs text-gray-500">Запас (дней)</div>
          <div class="text-lg font-bold text-gray-800">
            {{ forecast.insights.days_until_stockout ?? '—' }}
          </div>
        </div>
      </div>

      <!-- Chart -->
      <div class="card" v-if="chartData.labels.length">
        <div class="mb-3">
          <h3 class="font-semibold text-gray-700">{{ forecast?.product_sku }} — {{ forecast?.product_name }}</h3>
          <p v-if="forecast?.category" class="text-xs text-gray-400 mt-0.5">
            <span class="badge badge-blue">{{ forecast.category.name }}</span>
          </p>
        </div>
        <Line :data="chartData" :options="chartOptions" class="max-h-72" />
      </div>

      <div v-else-if="!forecastLoading && selectedProductId && !forecastError"
        class="card text-center py-12 text-gray-400 text-sm">
        Нажмите «Построить прогноз» для отображения графика
      </div>

      <!-- Forecast table -->
      <div v-if="forecast" class="card">
        <button
          type="button"
          class="flex w-full items-center justify-between text-left font-semibold text-gray-700"
          @click="showForecastTable = !showForecastTable"
        >
          <span>Таблица прогноза ({{ forecast.forecast.length }})</span>
          <span class="text-gray-400 text-sm">{{ showForecastTable ? 'Свернуть' : 'Развернуть' }}</span>
        </button>
        <div v-if="showForecastTable" class="mt-4 overflow-x-auto">
          <table class="w-full text-sm">
            <thead>
              <tr class="text-left text-gray-400 border-b">
                <th class="pb-2 font-medium">Дата</th>
                <th class="pb-2 font-medium text-right">Прогноз</th>
                <th class="pb-2 font-medium text-right">Мин</th>
                <th class="pb-2 font-medium text-right">Макс</th>
              </tr>
            </thead>
            <tbody class="divide-y divide-gray-50">
              <tr v-for="p in forecast.forecast" :key="p.date" class="hover:bg-gray-50">
                <td class="py-2 text-gray-600">{{ p.date }}</td>
                <td class="py-2 text-right font-semibold text-gray-800">{{ p.predicted.toFixed(1) }}</td>
                <td class="py-2 text-right text-gray-500">{{ p.lower.toFixed(1) }}</td>
                <td class="py-2 text-right text-gray-500">{{ p.upper.toFixed(1) }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <!-- Products table -->
      <div class="card">
        <button
          type="button"
          class="flex w-full items-center justify-between text-left font-semibold text-gray-700"
          @click="showModelsTable = !showModelsTable"
        >
          <span>Товары ({{ models.length }})</span>
          <span class="text-gray-400 text-sm">{{ showModelsTable ? 'Свернуть' : 'Развернуть' }}</span>
        </button>
        <div v-if="showModelsTable" class="mt-4 overflow-x-auto">
          <table class="w-full text-sm">
            <thead class="text-left text-gray-500 border-b">
              <tr>
                <th class="pb-2 font-medium">SKU</th>
                <th class="pb-2 font-medium">Категория</th>
                <th class="pb-2 font-medium text-right">Остаток</th>
                <th class="pb-2 font-medium text-right">История</th>
                <th class="pb-2 font-medium">Модель</th>
                <th class="pb-2 font-medium text-right">Действие</th>
              </tr>
            </thead>
            <tbody class="divide-y divide-gray-50">
              <tr v-for="m in models" :key="m.product_id" class="hover:bg-gray-50">
                <td class="py-2 font-mono text-blue-700">{{ m.product_sku }}</td>
                <td class="py-2">
                  <span v-if="m.category" class="badge badge-blue">{{ m.category.name }}</span>
                  <span v-else class="text-gray-400 text-xs">—</span>
                </td>
                <td class="py-2 text-right">{{ m.total_stock }}</td>
                <td class="py-2 text-right" :class="m.can_train ? 'text-gray-700' : 'text-red-400'">
                  {{ m.history_days }} дн.
                </td>
                <td class="py-2">
                  <span v-if="m.ready" class="text-green-600 text-xs">Готова</span>
                  <span v-else-if="m.can_train" class="text-amber-600 text-xs">Нужно обучить</span>
                  <span v-else class="text-gray-400 text-xs">Мало данных</span>
                </td>
                <td class="py-2 text-right">
                  <button class="btn-secondary text-xs" @click="selectProduct(m.product_id)">Прогноз</button>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>
  </ManagerLayout>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { Line } from 'vue-chartjs'
import { Chart as ChartJS, LineElement, PointElement, CategoryScale, LinearScale, Tooltip, Legend, Filler } from 'chart.js'
import ManagerLayout from '@/layouts/ManagerLayout.vue'
import IconMenu from '@/components/IconMenu.vue'
import { mlApi, productsApi } from '@/api'
import { parseApiDetail } from '@/utils/apiError'
import {
  buildValidationSummaryJson,
  formatValidationSummaryJson,
} from '@/utils/validationSummary'

ChartJS.register(LineElement, PointElement, CategoryScale, LinearScale, Tooltip, Legend, Filler)

const products = ref([])
const categories = ref([])
const models = ref([])
const overview = ref(null)
const filterCategoryId = ref('')
const productSearch = ref('')
const selectedProductId = ref('')
const days = ref(14)
const forecast = ref(null)
const forecastLoading = ref(false)
const forecastError = ref('')
const trainingStatus = ref('idle')
const trainingMsg = ref('')
const importMsg = ref('')
const importOk = ref(false)
const actionsMenuOpen = ref(false)
const actionsMenuRef = ref(null)
const showModelsTable = ref(false)
const showForecastTable = ref(true)
const showValidation = ref(false)
const validationTestSize = ref(0.2)
const validationProductId = ref('')
const validationLoading = ref(false)
const validationMode = ref('single')
const validationError = ref('')
const validationResult = ref(null)
const validationCompareResult = ref(null)
const validationDetailMethod = ref('')
const showValidationJson = ref(false)
const validationJsonMsg = ref('')
const validationJsonMsgOk = ref(true)
const forecastMethods = ref([])
const FORECAST_METHOD_STORAGE = 'wms_forecast_method'
const forecastMethod = ref(
  typeof localStorage !== 'undefined'
    ? localStorage.getItem(FORECAST_METHOD_STORAGE) || 'xgboost'
    : 'xgboost',
)
let trainPollTimer = null

const availableForecastMethods = computed(() =>
  forecastMethods.value.filter(m => m.available),
)

const selectedMethodMeta = computed(() =>
  forecastMethods.value.find(m => m.id === forecastMethod.value),
)

const selectedMethodRequiresTraining = computed(() =>
  selectedMethodMeta.value?.requires_training ?? forecastMethod.value === 'xgboost',
)

const validationMethodRuns = computed(() => validationCompareResult.value?.runs || [])

const validationActiveRun = computed(() => {
  if (validationCompareResult.value?.runs?.length) {
    const id = validationDetailMethod.value
    return validationCompareResult.value.runs.find(r => r.forecast_method === id)
      || validationCompareResult.value.runs[0]
  }
  return null
})

const validationCategories = computed(() => {
  if (validationActiveRun.value) return validationActiveRun.value.categories || []
  return validationResult.value?.categories || []
})

const validationRows = computed(() => {
  const rows = validationActiveRun.value?.results || validationResult.value?.results || []
  return [...rows].sort((a, b) => {
    if (a.status === 'ok' && b.status !== 'ok') return -1
    if (a.status !== 'ok' && b.status === 'ok') return 1
    return (a.product_sku || '').localeCompare(b.product_sku || '')
  })
})

const validationHasData = computed(
  () => !!(validationCompareResult.value || validationResult.value),
)

const validationSelectedProductSku = computed(() => {
  if (!validationProductId.value) return null
  const p = products.value.find(x => String(x.id) === validationProductId.value)
  return p?.sku ?? null
})

const validationSummaryObject = computed(() =>
  buildValidationSummaryJson({
    compare: validationCompareResult.value,
    single: validationResult.value,
    testSize: validationTestSize.value,
    productId: validationProductId.value ? Number(validationProductId.value) : null,
    productSku: validationSelectedProductSku.value,
  }),
)

const validationJsonText = computed(() =>
  formatValidationSummaryJson(validationSummaryObject.value),
)

const validationSkuMatrix = computed(() => {
  const runs = validationMethodRuns.value
  if (!runs.length) return []
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
})

const filteredProducts = computed(() => {
  let list = products.value
  if (filterCategoryId.value) {
    const cid = Number(filterCategoryId.value)
    list = list.filter(p => p.category?.id === cid)
  }
  const q = productSearch.value.toLowerCase().trim()
  if (q) {
    list = list.filter(p =>
      p.sku.toLowerCase().includes(q) ||
      p.name.toLowerCase().includes(q) ||
      (p.category?.name || '').toLowerCase().includes(q),
    )
  }
  return list
})

const trainingStatusLabel = computed(() => {
  const map = { idle: 'Не запущено', running: 'Выполняется', done: 'Завершено', error: 'Ошибка' }
  return map[trainingStatus.value] || trainingStatus.value
})

const trainingStatusClass = computed(() => {
  if (trainingStatus.value === 'running') return 'text-blue-700'
  if (trainingStatus.value === 'done') return 'text-green-700'
  if (trainingStatus.value === 'error') return 'text-red-600'
  return 'text-gray-600'
})

const chartOptions = {
  responsive: true,
  interaction: { intersect: false, mode: 'index' },
  plugins: { legend: { position: 'top' } },
  scales: { y: { beginAtZero: true } },
}

const chartData = computed(() => {
  if (!forecast.value) return { labels: [], datasets: [] }
  const histLabels = forecast.value.history.map(p => p.date)
  const fcLabels = forecast.value.forecast.map(p => p.date)
  const histValues = forecast.value.history.map(p => p.predicted)
  const fcValues = [null, ...new Array(histLabels.length - 1).fill(null), ...forecast.value.forecast.map(p => p.predicted)]
  const lowerValues = [...new Array(histLabels.length).fill(null), ...forecast.value.forecast.map(p => p.lower)]
  const upperValues = [...new Array(histLabels.length).fill(null), ...forecast.value.forecast.map(p => p.upper)]

  return {
    labels: [...histLabels, ...fcLabels],
    datasets: [
      { label: 'Факт (расход)', data: [...histValues, ...new Array(fcLabels.length).fill(null)], borderColor: '#6B7280', borderWidth: 2, pointRadius: 1, tension: 0.3 },
      { label: 'Прогноз', data: fcValues, borderColor: '#3B82F6', borderWidth: 2, borderDash: [5, 4], pointRadius: 3, tension: 0.3 },
      { label: 'Интервал (верх)', data: upperValues, borderColor: 'transparent', backgroundColor: 'rgba(59,130,246,0.1)', fill: '+1', pointRadius: 0 },
      { label: 'Интервал (низ)', data: lowerValues, borderColor: 'transparent', backgroundColor: 'rgba(59,130,246,0.1)', fill: false, pointRadius: 0 },
    ],
  }
})

function closeActionsMenu() {
  actionsMenuOpen.value = false
}

function onDocumentClick(e) {
  if (!actionsMenuRef.value?.contains(e.target)) closeActionsMenu()
}

function selectProduct(id) {
  selectedProductId.value = id
  loadForecast()
}

async function loadOverview() {
  try {
    const { data } = await mlApi.overview()
    overview.value = data
    trainingStatus.value = data.training_status || 'idle'
  } catch {
    overview.value = null
  }
}

async function loadModels() {
  const params = {}
  if (filterCategoryId.value) params.category_id = Number(filterCategoryId.value)
  try {
    const { data } = await mlApi.models(params)
    models.value = data || []
  } catch {
    models.value = []
  }
}

async function loadProducts() {
  const params = { active_only: true }
  if (filterCategoryId.value) params.category_id = Number(filterCategoryId.value)
  const { data } = await productsApi.list(params)
  products.value = data || []
}

async function loadCategories() {
  try {
    const { data } = await productsApi.categories()
    categories.value = data || []
  } catch {
    categories.value = []
  }
}

async function refreshAll() {
  await Promise.all([loadOverview(), loadModels(), loadProducts()])
}

function onCategoryFilterChange() {
  selectedProductId.value = ''
  forecast.value = null
  forecastError.value = ''
  refreshAll()
}

async function loadForecastMethods() {
  try {
    const { data } = await mlApi.methods()
    forecastMethods.value = data || []
    const saved = forecastMethod.value
    const found = forecastMethods.value.find(m => m.id === saved && m.available)
    if (!found) {
      const fallback =
        forecastMethods.value.find(m => m.id === 'xgboost' && m.available)
        || forecastMethods.value.find(m => m.available)
      if (fallback) {
        forecastMethod.value = fallback.id
        localStorage.setItem(FORECAST_METHOD_STORAGE, fallback.id)
      }
    }
  } catch {
    forecastMethods.value = []
  }
}

function onForecastMethodChange() {
  localStorage.setItem(FORECAST_METHOD_STORAGE, forecastMethod.value)
  if (selectedProductId.value && forecast.value) {
    loadForecast()
  }
}

async function loadForecast() {
  forecastLoading.value = true
  forecastError.value = ''
  forecast.value = null
  try {
    const { data } = await mlApi.forecast(
      selectedProductId.value,
      days.value,
      forecastMethod.value,
    )
    forecast.value = data
  } catch (e) {
    const fallback = selectedMethodRequiresTraining.value
      ? 'Ошибка загрузки прогноза. Возможно, модель не обучена.'
      : 'Ошибка загрузки прогноза. Проверьте объём истории расхода.'
    forecastError.value = parseApiDetail(e, fallback)
  } finally {
    forecastLoading.value = false
  }
}

async function importHistoryFile(e) {
  const file = e.target.files?.[0]
  if (!file) return
  importMsg.value = ''
  importOk.value = false
  try {
    const text = await file.text()
    const payload = JSON.parse(text)
    const { data } = await mlApi.importHistory(payload)
    importOk.value = true
    importMsg.value =
      `История загружена: ${data.orders_created} заказов, ${data.items_created} позиций, ` +
      `${data.days_covered} дней, ${data.skus} SKU. Запустите обучение моделей.`
    await refreshAll()
  } catch (err) {
    importMsg.value = parseApiDetail(err, 'Ошибка импорта')
  }
  e.target.value = ''
}

function stopTrainPoll() {
  if (trainPollTimer) {
    clearInterval(trainPollTimer)
    trainPollTimer = null
  }
}

function startTrainPoll() {
  stopTrainPoll()
  trainPollTimer = setInterval(async () => {
    try {
      const { data } = await mlApi.trainStatus()
      trainingStatus.value = data.status
      if (data.status === 'done') {
        trainingMsg.value = `Обучено моделей: ${data.products_trained}`
        stopTrainPoll()
        await refreshAll()
      } else if (data.status === 'error') {
        trainingMsg.value = `Ошибка: ${data.error}`
        stopTrainPoll()
      }
    } catch {
      stopTrainPoll()
    }
  }, 2000)
}

async function runTraining(opts = {}) {
  trainingStatus.value = 'running'
  trainingMsg.value = 'Обучение запущено в фоне...'
  try {
    await mlApi.train(opts)
    startTrainPoll()
  } catch (e) {
    trainingStatus.value = 'error'
    trainingMsg.value = parseApiDetail(e, 'Не удалось запустить обучение')
  }
}

function onTrainClick(categoryOnly) {
  closeActionsMenu()
  const payload = { force: false }
  if (categoryOnly && filterCategoryId.value) {
    payload.category_id = Number(filterCategoryId.value)
  }
  runTraining(payload)
}

function onTrainForce() {
  closeActionsMenu()
  const payload = { force: true }
  if (filterCategoryId.value) payload.category_id = Number(filterCategoryId.value)
  runTraining(payload)
}

function onImportClick(e) {
  closeActionsMenu()
  importHistoryFile(e)
}

function openValidationModal() {
  closeActionsMenu()
  validationError.value = ''
  validationJsonMsg.value = ''
  showValidationJson.value = false
  if (selectedProductId.value) {
    validationProductId.value = String(selectedProductId.value)
  }
  showValidation.value = true
}

function toggleValidationJson() {
  if (!validationHasData.value) return
  showValidationJson.value = !showValidationJson.value
}

function validationJsonFilename() {
  const ts = new Date().toISOString().slice(0, 19).replace(/[:T]/g, '-')
  const scope = validationProductId.value ? `sku-${validationSelectedProductSku.value || validationProductId.value}` : 'all'
  const kind = validationCompareResult.value ? 'compare' : 'single'
  return `wms-validation-${kind}-${scope}-${ts}.json`
}

async function copyValidationJson() {
  validationJsonMsg.value = ''
  const text = validationJsonText.value
  if (!text) {
    validationJsonMsgOk.value = false
    validationJsonMsg.value = 'Нет данных для сводки — сначала запустите валидацию'
    return
  }
  try {
    await navigator.clipboard.writeText(text)
    validationJsonMsgOk.value = true
    validationJsonMsg.value = 'JSON сводка скопирована в буфер'
    showValidationJson.value = true
  } catch {
    validationJsonMsgOk.value = false
    validationJsonMsg.value = 'Не удалось скопировать — откройте «Сводка JSON» и скопируйте вручную'
    showValidationJson.value = true
  }
}

function downloadValidationJson() {
  validationJsonMsg.value = ''
  const text = validationJsonText.value
  if (!text) {
    validationJsonMsgOk.value = false
    validationJsonMsg.value = 'Нет данных для сводки — сначала запустите валидацию'
    return
  }
  const blob = new Blob([text], { type: 'application/json;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = validationJsonFilename()
  a.click()
  URL.revokeObjectURL(url)
  validationJsonMsgOk.value = true
  validationJsonMsg.value = `Файл ${a.download} скачан`
  showValidationJson.value = true
}

function closeValidationModal() {
  if (validationLoading.value) return
  showValidation.value = false
}

function fmtMetric(v) {
  if (v == null || v === undefined) return '—'
  return Number(v).toLocaleString('ru-RU', { maximumFractionDigits: 4 })
}

function formatValidatedAt(iso) {
  if (!iso) return '—'
  try {
    return new Date(iso).toLocaleString('ru-RU')
  } catch {
    return iso
  }
}

function skipLabel(reason) {
  const map = {
    not_enough_data: 'Мало данных',
    validation_error: 'Ошибка',
  }
  return map[reason] || reason || 'Пропуск'
}

function validationPayloadBase() {
  const payload = { test_size: validationTestSize.value }
  if (validationProductId.value) {
    payload.product_id = Number(validationProductId.value)
  }
  return payload
}

async function runValidation() {
  validationLoading.value = true
  validationMode.value = 'single'
  validationError.value = ''
  validationResult.value = null
  validationCompareResult.value = null
  validationDetailMethod.value = ''
  validationJsonMsg.value = ''
  try {
    const payload = {
      ...validationPayloadBase(),
      forecast_method: forecastMethod.value,
    }
    const { data } = await mlApi.validate(payload)
    validationResult.value = data
  } catch (e) {
    validationError.value = parseApiDetail(e, 'Ошибка валидации моделей')
  } finally {
    validationLoading.value = false
  }
}

async function runValidationAll() {
  validationLoading.value = true
  validationMode.value = 'all'
  validationError.value = ''
  validationResult.value = null
  validationCompareResult.value = null
  validationDetailMethod.value = ''
  validationJsonMsg.value = ''
  try {
    const { data } = await mlApi.validateCompare(validationPayloadBase())
    validationCompareResult.value = data
    if (data.runs?.length) {
      validationDetailMethod.value = data.runs[0].forecast_method
    }
  } catch (e) {
    validationError.value = parseApiDetail(e, 'Ошибка сравнения моделей')
  } finally {
    validationLoading.value = false
  }
}

onMounted(async () => {
  document.addEventListener('click', onDocumentClick)
  await loadCategories()
  await loadForecastMethods()
  await refreshAll()
  try {
    const { data } = await mlApi.trainStatus()
    trainingStatus.value = data.status
    if (data.status === 'running') startTrainPoll()
  } catch { /* ignore */ }
})

onUnmounted(() => {
  document.removeEventListener('click', onDocumentClick)
  stopTrainPoll()
})

watch(filterCategoryId, () => {
  if (!filteredProducts.value.some(p => p.id === Number(selectedProductId.value))) {
    selectedProductId.value = ''
  }
})
</script>
