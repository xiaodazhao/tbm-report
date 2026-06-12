<template>
  <div class="toolbar">
    <el-form label-position="top">
      <el-form-item label="报告日期">
        <el-select
          :model-value="selectedDate"
          placeholder="请选择日期"
          filterable
          class="full-width"
          @update:model-value="$emit('update:selectedDate', $event)"
        >
          <el-option v-for="date in dates" :key="date" :label="date" :value="date" />
        </el-select>
      </el-form-item>

      <el-form-item label="LLM 模式">
        <el-switch
          :model-value="useLlm"
          active-text="启用"
          inactive-text="关闭"
          @update:model-value="$emit('update:useLlm', Boolean($event))"
        />
      </el-form-item>
    </el-form>

    <el-button type="primary" :loading="loading" :disabled="!selectedDate || loading" @click="$emit('submit')">
      {{ buttonText }}
    </el-button>
  </div>
</template>

<script setup lang="ts">
defineProps<{
  dates: string[];
  selectedDate: string;
  useLlm: boolean;
  loading?: boolean;
  buttonText?: string;
}>();

defineEmits<{
  "update:selectedDate": [value: string];
  "update:useLlm": [value: boolean];
  submit: [];
}>();
</script>

<style scoped>
.full-width {
  width: 100%;
}
</style>
