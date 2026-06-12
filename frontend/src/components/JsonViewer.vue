<template>
  <pre class="json-block">{{ formatted }}</pre>
</template>

<script setup lang="ts">
import { computed } from "vue";

const props = defineProps<{
  value: unknown;
}>();

const formatted = computed(() => JSON.stringify(props.value ?? {}, null, 2));
</script>
