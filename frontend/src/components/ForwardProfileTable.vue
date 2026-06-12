<template>
  <el-table :data="rows" stripe border size="small" class="data-table">
    <el-table-column type="expand">
      <template #default="{ row }">
        <div class="expanded">
          <h4>source_trace</h4>
          <JsonViewer :value="row.source_trace || []" />
          <h4>attention_reason</h4>
          <p>{{ row.attention_reason || "后端未返回单独原因字段，请查看 source_trace 与 forward_profile。" }}</p>
        </div>
      </template>
    </el-table-column>
    <el-table-column prop="cell_id" label="cell_id" min-width="180" />
    <el-table-column prop="cell_start" label="start" width="110" />
    <el-table-column prop="cell_end" label="end" width="110" />
    <el-table-column label="distance_to_face" width="150">
      <template #default="{ row }">{{ formatNumber(row.distance_to_face) }}</template>
    </el-table-column>
    <el-table-column label="GRS" width="90">
      <template #default="{ row }">{{ formatNumber(row.GRS_geo_base) }}</template>
    </el-table-column>
    <el-table-column label="main_hazards" min-width="220">
      <template #default="{ row }">
        <el-tag v-for="item in row.main_hazards || []" :key="item" class="tag-item" effect="plain">
          {{ item }}
        </el-tag>
      </template>
    </el-table-column>
  </el-table>
</template>

<script setup lang="ts">
import type { ForwardAttentionCell } from "@/types/tbm";
import JsonViewer from "@/components/JsonViewer.vue";

defineProps<{
  rows: ForwardAttentionCell[];
}>();

function formatNumber(value: unknown): string {
  return typeof value === "number" ? value.toFixed(3) : "--";
}
</script>

<style scoped>
.data-table {
  width: 100%;
}

.expanded {
  padding: 8px 24px 18px;
}

.expanded h4 {
  margin: 10px 0 8px;
}

.expanded p {
  margin: 0;
  color: #374151;
}

.tag-item {
  margin: 2px 4px 2px 0;
}
</style>
