<template>
  <div>
    <el-alert
      title="Evidence Pack 是报告生成的结构化证据边界，前端只展示后端结果，不拼接、不计算。"
      type="info"
      show-icon
      :closable="false"
      class="hint"
    />
    <JsonViewer :value="value" />
  </div>
</template>

<script setup lang="ts">
import JsonViewer from "@/components/JsonViewer.vue";

defineProps<{
  value: unknown;
}>();
</script>

<style scoped>
.hint {
  margin-bottom: 12px;
}
</style>
