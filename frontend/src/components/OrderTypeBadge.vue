<template>
  <span :class="cls">{{ label }}</span>
</template>
<script setup>
import { computed } from 'vue'
const props = defineProps({ type: String })
const map = { ARRIVAL: ['badge-blue', 'Приёмка'], CONSUMPTION: ['badge-green', 'Расход'], INVENTORY: ['badge-yellow', 'Инвентаризация'] }
const cls   = computed(() => map[props.type]?.[0] ?? 'badge-gray')
const label = computed(() => map[props.type]?.[1] ?? props.type)
</script>
