<template>
  <span :class="cls">{{ label }}</span>
</template>
<script setup>
import { computed } from 'vue'
const props = defineProps({ status: String })
const map = {
  PENDING:     ['badge-yellow', 'Ожидает'],
  IN_PROGRESS: ['badge-blue',   'В работе'],
  COMPLETED:   ['badge-green',  'Завершён'],
  CANCELLED:   ['badge-red',    'Отменён'],
}
const cls   = computed(() => map[props.status]?.[0] ?? 'badge-gray')
const label = computed(() => map[props.status]?.[1] ?? props.status)
</script>
