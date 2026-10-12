/** Демо-каталог в стиле seed WMS */
export const DEMO_CATEGORIES = [
  'Электроника',
  'Хозтовары',
  'Одежда',
  'Продукты питания',
  'Инструменты',
]

export const DEMO_PRODUCTS = [
  { sku: 'SKU-001', name: 'Ноутбук Lenovo IdeaPad', category: 'Электроника', unit: 'шт', weight: 2.1 },
  { sku: 'SKU-002', name: 'Мышь беспроводная Logitech', category: 'Электроника', unit: 'шт', weight: 0.1 },
  { sku: 'SKU-003', name: 'Клавиатура механическая', category: 'Электроника', unit: 'шт', weight: 0.8 },
  { sku: 'SKU-004', name: 'Монитор 27" Samsung', category: 'Электроника', unit: 'шт', weight: 4.5 },
  { sku: 'SKU-005', name: 'Наушники Sony WH-1000XM5', category: 'Электроника', unit: 'шт', weight: 0.25 },
  { sku: 'SKU-006', name: 'Швабра телескопическая', category: 'Хозтовары', unit: 'шт', weight: 0.5 },
  { sku: 'SKU-007', name: 'Моющее средство Fairy 5л', category: 'Хозтовары', unit: 'шт', weight: 5.2 },
  { sku: 'SKU-008', name: 'Перчатки резиновые (пара)', category: 'Хозтовары', unit: 'пара', weight: 0.1 },
  { sku: 'SKU-009', name: 'Футболка хлопок M', category: 'Одежда', unit: 'шт', weight: 0.2 },
  { sku: 'SKU-010', name: 'Джинсы классика L', category: 'Одежда', unit: 'шт', weight: 0.5 },
  { sku: 'SKU-011', name: 'Носки (упак. 5 пар)', category: 'Одежда', unit: 'упак', weight: 0.15 },
  { sku: 'SKU-012', name: 'Сахар 1кг', category: 'Продукты питания', unit: 'кг', weight: 1.0 },
  { sku: 'SKU-013', name: 'Мука пшеничная 2кг', category: 'Продукты питания', unit: 'кг', weight: 2.0 },
  { sku: 'SKU-014', name: 'Масло подсолнечное 1л', category: 'Продукты питания', unit: 'шт', weight: 0.9 },
  { sku: 'SKU-015', name: 'Шуруповёрт Bosch', category: 'Инструменты', unit: 'шт', weight: 1.8 },
  { sku: 'SKU-016', name: 'Набор отвёрток 12 шт', category: 'Инструменты', unit: 'шт', weight: 0.6 },
  { sku: 'SKU-017', name: 'Рулетка 5м', category: 'Инструменты', unit: 'шт', weight: 0.2 },
  { sku: 'SKU-018', name: 'Кабель USB-C 2м', category: 'Электроника', unit: 'шт', weight: 0.05 },
  { sku: 'SKU-019', name: 'Чехол для ноутбука 15"', category: 'Электроника', unit: 'шт', weight: 0.3 },
  { sku: 'SKU-020', name: 'Удлинитель 5 розеток 3м', category: 'Хозтовары', unit: 'шт', weight: 0.7 },
]

export const PRODUCT_NAMES = [
  'Адаптер питания', 'Блокнот А4', 'Степлер офисный', 'Маркер перманентный',
  'Скотч упаковочный', 'Папка-регистратор', 'Калькулятор', 'Лампа настольная',
  'Термос 0.5л', 'Зонт складной', 'Рюкзак городской', 'Плед флисовый',
]

export const UNITS = ['шт', 'кг', 'л', 'упак', 'пара']

export function randomCell() {
  const zone = ['A', 'B', 'C'][Math.floor(Math.random() * 3)]
  const rack = 1 + Math.floor(Math.random() * 3)
  const shelf = 1 + Math.floor(Math.random() * 3)
  const pos = 1 + Math.floor(Math.random() * 3)
  return `${zone}${rack}-${shelf}-${pos}`
}

export function randomInt(min, max) {
  return min + Math.floor(Math.random() * (max - min + 1))
}
