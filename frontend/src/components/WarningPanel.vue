<template>
  <div class="panel">
    <h3 class="panel-title">Warnings</h3>
    <el-empty v-if="!warnings?.length" description="暂无 warning" :image-size="70" />
    <el-alert
      v-for="(warning, index) in warnings"
      :key="index"
      :title="warning"
      type="warning"
      show-icon
      :closable="false"
      class="warning-item"
    />
  </div>
</template>

<script setup lang="ts">
defineProps<{
  warnings?: string[];
}>();
</script>

<style scoped>
.warning-item + .warning-item {
  margin-top: 8px;
}
</style>
