# WMS — складская система

Веб-приложение для учёта товаров, ячеек, заказов (приёмка / расход / инвентаризация), аналитики и прогнозирования спроса.

**Стек:** Vue 3 + FastAPI + PostgreSQL + XGBoost (прогноз).

---

## Что нужно установить

| Компонент | Версия | Зачем |
|-----------|--------|--------|
| [Docker Desktop](https://www.docker.com/products/docker-desktop/) | актуальная | **Рекомендуемый** способ запуска всего проекта |
| Git | любая | клонирование репозитория |

Для запуска **без Docker** дополнительно: Python 3.11+, Node.js 20+, PostgreSQL 16.

---

## Быстрый старт (Docker) — рекомендуется

Все команды выполняйте из папки `wms` (где лежит `docker-compose.yml`).

### 1. Запуск контейнеров

```powershell
cd C:\Users\Darwin\Desktop\Project2\wms
docker compose up -d --build
```

Поднимаются сервисы:

| Сервис | Порт | Назначение |
|--------|------|------------|
| **nginx** | **80** | Единая точка входа (фронт + API) |
| frontend | 5173 | Vue (dev-сервер, можно открыть напрямую) |
| backend | 8000 | FastAPI API |
| db | 5432 | PostgreSQL |

Первый запуск может занять несколько минут (сборка образов, установка зависимостей).

### 2. Проверка

- Интерфейс: **http://localhost** (через nginx) или **http://localhost:5173**
- API: **http://localhost:8000/api/health** → `{"status":"ok",...}`
- Документация API: **http://localhost:8000/docs**

### 3. Вход в систему

При первом запуске backend сам создаёт администратора, если в БД нет пользователей:

| Логин | Пароль | Роль |
|-------|--------|------|
| `admin` | `admin123` | Администратор |

### 4. Демо-данные (товары, ячейки, остатки, история для ML)

```powershell
docker compose exec backend python -m app.seed
```

Создаётся:

- 5 категорий, 20 товаров с SKU
- ячейки склада и начальные остатки
- пользователи `manager1`, `worker1`, `worker2`
- ~90 дней истории расхода для обучения прогноза

Учётные записи после seed:

| Логин | Пароль | Роль |
|-------|--------|------|
| `admin` | `admin123` | Администратор |
| `manager1` | `manager123` | Менеджер |
| `worker1` | `worker123` | Кладовщик |
| `worker2` | `worker123` | Кладовщик |

### 5. Обучение моделей прогноза (опционально, после seed)

```powershell
docker compose exec backend python -m app.seed_train
```

Занимает около 1–2 минут. После этого в меню **«Прогнозирование»** можно строить графики.

Либо в интерфейсе: **Прогнозирование** → меню **⋯** → **«Обучить все модели»**.

---

## Остановка и перезапуск

```powershell
# Остановить
docker compose down

# Остановить и удалить данные БД (полный сброс)
docker compose down -v

# Перезапуск после изменений в коде
docker compose up -d --build

# Логи backend
docker compose logs -f backend
```

---

## Запуск без Docker (Windows, для разработки)

### 1. PostgreSQL

Запустите PostgreSQL локально и создайте БД:

- база: `wms_db`
- пользователь: `wms_user` / пароль: `wms_pass`

Или только БД в Docker:

```powershell
docker compose up -d db
```

### 2. Backend

```powershell
cd C:\Users\Darwin\Desktop\Project2\wms\backend

# Виртуальное окружение (если ещё нет)
python -m venv venv
.\venv\Scripts\Activate.ps1

pip install -r requirements.txt

# Настройки: скопируйте .env.example → .env
# Для локального запуска укажите localhost вместо db:
# DATABASE_URL=postgresql+asyncpg://wms_user:wms_pass@127.0.0.1:5432/wms_db
# DATABASE_URL_SYNC=postgresql+psycopg2://wms_user:wms_pass@127.0.0.1:5432/wms_db

uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

API: **http://127.0.0.1:8000**

Демо-данные:

```powershell
python -m app.seed
python -m app.seed_train
```

### 3. Frontend

```powershell
cd C:\Users\Darwin\Desktop\Project2\wms\frontend
npm install
npm run dev
```

Откройте **http://localhost:5173** — запросы к `/api` проксируются на `127.0.0.1:8000` (см. `vite.config.js`).

---

## Генератор тестовых данных

Папка `data-generator/` — отдельный инструмент для файлов импорта (товары, приёмка, расход, история спроса).

### Веб-интерфейс

```powershell
cd C:\Users\Darwin\Desktop\Project2\wms\data-generator
python -m http.server 8765
```

Откройте **http://localhost:8765**

### Полный склад одной кнопкой

1. WMS запущен (`docker compose up`).
2. Генератор → вкладка **«Полный склад»** → **Сгенерировать** → **Загрузить в WMS** (логин/пароль вверху страницы).
3. В WMS откройте **Остатки**, **Товары**, **Прогнозирование** — данные уже согласованы.

### Пошагово (отдельные файлы)

1. **Товары** — каталог с `category` → импорт в WMS.
2. **Приёмка** / **Расход** — заказы → соответствующие разделы.
3. **История спроса** → пресет **«Бенчмарк прогнозов Супер»** → **Прогнозирование** → импорт и обучение ML.

Подробнее (запуск, CLI, расширенные параметры спроса): [data-generator/README.md](data-generator/README.md)

---

## Роли и основные разделы

### Менеджер / администратор

| Раздел | Путь | Назначение |
|--------|------|------------|
| Аналитика | `/dashboard` | KPI, графики, товары по категориям |
| Остатки | `/stocks` | Просмотр, перемещение, удаление остатков |
| Заказы | `/orders` | История операций |
| Заказы на приёмку | `/arrival-requests` | Создание заданий кладовщику |
| Заказы на расход | `/consumption-requests` | Создание заданий на отгрузку |
| Инвентаризация | `/inventory-requests` | Задания по зонам/стеллажам |
| Прогнозирование | `/forecast` | ML-прогноз спроса |
| Товары | `/products` | Каталог, категории, импорт |
| Ячейки | `/cells` | Адреса хранения |
| Зоны склада | `/warehouse-map` | Карта зон |
| Пользователи | `/users` | Только **ADMIN** |

### Кладовщик

| Раздел | Путь |
|--------|------|
| Главная | `/` |
| Приёмка | `/arrival` |
| Расход | `/dispatch` |
| Перемещение | `/move` |
| Инвентаризация | `/inventory` |

Заказы создаёт менеджер; кладовщик берёт их в работу и завершает по маршрутному листу.

---

## Прогнозирование спроса (кратко)

1. В системе должны быть **товары с категориями** и **история расхода** (реальные заказы или импорт JSON).
2. **Прогнозирование** → ⋯ → **Обучить все модели** (или `python -m app.seed_train` после seed).
3. Выберите категорию/товар → **Построить прогноз**.

Минимум для обучения: **14 дней** истории по товару.

---

## Полезные команды

```powershell
# Статус контейнеров
docker compose ps

# Зайти в shell backend
docker compose exec backend bash

# Проверка API из PowerShell
Invoke-WebRequest http://localhost:8000/api/health

# Пересоздать только backend после правок Python
docker compose up -d --build backend
```

---

## Частые проблемы

### Порт 80 или 5432 занят

Измените порты в `docker-compose.yml`, например `"8080:80"` для nginx.

### «Модель не найдена» на прогнозе

Запустите обучение: меню **Обучить модели** или `docker compose exec backend python -m app.seed_train`.

### Пустые остатки / нет товаров

Выполните `docker compose exec backend python -m app.seed`.

### Frontend не видит API (локальный запуск)

- Backend должен слушать **8000**.
- В `frontend/vite.config.js` proxy указывает на `http://127.0.0.1:8000`.
- При работе через Docker используйте **http://localhost** (nginx), а не только :5173 без proxy.

### Ошибка подключения к БД в Docker

Дождитесь `healthy` у контейнера `wms_db`: `docker compose ps`. Перезапуск: `docker compose restart backend`.

### Сброс всего и чистый старт

```powershell
docker compose down -v
docker compose up -d --build
docker compose exec backend python -m app.seed
docker compose exec backend python -m app.seed_train
```

---

## Структура проекта

```
wms/
├── backend/          # FastAPI, модели, ML
├── frontend/         # Vue 3 + Vite + Tailwind
├── data-generator/   # Генератор JSON/Excel для импорта
├── nginx/            # Прокси :80 → frontend + backend
├── docker-compose.yml
└── README.md         # этот файл
```

---

## API (префикс `/api`)

| Группа | Префикс |
|--------|---------|
| Авторизация | `/api/auth` |
| Товары и категории | `/api/products` |
| Ячейки | `/api/cells` |
| Склад, заказы, остатки | `/api/warehouse` |
| Прогнозирование | `/api/predictions` |
| Полная загрузка склада | `POST /api/warehouse/bootstrap` |

Полная интерактивная документация: **http://localhost:8000/docs**
