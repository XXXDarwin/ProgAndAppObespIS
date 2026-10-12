<template>
  <router-link
    :to="to"
    class="flex items-center gap-2.5 px-3 py-2 rounded-lg text-sm font-medium transition-colors"
    :class="isActive
      ? 'bg-blue-600 text-white'
      : 'text-slate-300 hover:bg-slate-800 hover:text-white'"
  >
    <slot />
  </router-link>
</template>

<script setup>
import { computed } from 'vue'
import { useRoute } from 'vue-router'

const props = defineProps({ to: String })
const route = useRoute()
const isActive = computed(() => route.path === props.to)
</script>
