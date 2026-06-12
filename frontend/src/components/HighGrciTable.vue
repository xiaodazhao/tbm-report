<template>
  <el-table :data="safeRows" stripe border size="small" class="data-table">
    <el-table-column type="expand">
      <template #default="{ row }">
        <div class="expanded">
          <h4>source_trace</h4>
          <JsonViewer :value="row.source_trace || []" />
          <h4>supporting_evidence_ids</h4>
          <el-tag v-for="id in row.supporting_evidence_ids || []" :key="id" class="tag-item" effect="plain">
            {{ id }}
          </el-tag>
        </div>
      </template>
    </el-table-column>
    <el-table-column prop="cell_id" label="cell_id" min-width="180" fixed />
    <el-table-column prop="cell_start" label="start" width="110" />
    <el-table-column prop="cell_end" label="end" width="110" />
    <el-table-column label="GRS" width="90">
      <template #default="{ row }">{{ formatNumber(row.GRS_geo_base) }}</template>
    </el-table-column>
    <el-table-column label="RAI" width="90">
      <template #default="{ row }">{{ formatNumber(row.RAI) }}</template>
    </el-table-column>
    <el-table-column label="GRCI" width="90">
      <template #default="{ row }">{{ formatNumber(row.GRCI) }}</template>
    </el-table-column>
    <el-table-column label="available" width="110">
      <template #default="{ row }">
        <el-tag :type="row.GRCI_available ? 'success' : 'info'" effect="plain">
          {{ row.GRCI_available ? "true" : "false" }}
        </el-tag>
      </template>
    </el-table-column>
    <el-table-column prop="coupling_level" label="level" width="120" />
    <el-table-column label="main_hazards" min-width="180">
      <template #default="{ row }">
        <el-tag v-for="item in row.main_hazards || []" :key="item" class="tag-item" effect="plain">
          {{ item }}
        </el-tag>
      </template>
    </el-table-column>
  </el-table>
</template>

<script setup lang="ts">
import { computed } from "vue";
import type { HighGrciCell } from "@/types/tbm";
import JsonViewer from "@/components/JsonViewer.vue";

const props = defineProps<{
  rows?: HighGrciCell[];
  filterValid?: boolean;
}>();

const safeRows = computed(() => {
  const rows = props.rows || [];
  if (props.filterValid === false) return rows;
  return rows.filter((row) => row.GRCI_available !== false && row.GRCI != null && row.is_forward_cell !== true);
});

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

.tag-item {
  margin: 2px 4px 2px 0;
}
</style>
