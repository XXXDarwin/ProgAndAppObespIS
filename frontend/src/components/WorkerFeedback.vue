<template>
  <div
    class="rounded-xl border px-4 py-4 text-sm"
    :class="{
      'bg-green-50 border-green-200 text-green-800': type === 'success',
      'bg-red-50 border-red-200 text-red-800': type === 'error',
      'bg-blue-50 border-blue-200 text-blue-800': type === 'info',
      'bg-yellow-50 border-yellow-200 text-yellow-800': type === 'warning',
    }"
  >
    <div v-if="title" class="font-semibold text-base mb-1">{{ title }}</div>
    <p v-if="message" class="leading-relaxed">{{ message }}</p>
    <slot />
  </div>
</template>

<script setup>
defineProps({
  type: { type: String, default: 'info' },
  title: { type: String, default: '' },
  message: { type: String, default: '' },
})
</script>
