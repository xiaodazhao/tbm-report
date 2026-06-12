<template>
  <div>
    <h2 class="page-title">高关注区段页</h2>
    <p class="page-subtitle">展示后端返回的已掘区段 high GRCI cell；前端不计算 GRCI。</p>

    <el-row :gutter="16">
      <el-col :span="5">
        <div class="panel">
          <h3 class="panel-title">数据来源</h3>
          <DateSelector
            :dates="store.dates"
            :selected-date="store.selectedDate"
            :use-llm="store.useLlm"
            :loading="store.loading"
            button-text="生成并查看"
            @update:selected-date="store.selectedDate = $event"
            @update:use-llm="store.useLlm = $event"
            @submit="store.generateReport"
          />
        </div>
      </el-col>

      <el-col :span="19">
        <div class="panel">
          <h3 class="panel-title">High GRCI Cells</h3>
          <el-alert
            title="本表只展示后端 high_grci_cells 中 GRCI_available=true 且非 forward cell 的记录。"
            type="info"
            show-icon
            :closable="false"
            class="hint"
          />
          <HighGrciTable :rows="store.report?.high_grci_cells || []" />
        </div>
      </el-col>
    </el-row>
  </div>
</template>

<script setup lang="ts">
import DateSelector from "@/components/DateSelector.vue";
import HighGrciTable from "@/components/HighGrciTable.vue";
import { useReportStore } from "@/stores/reportStore";

const store = useReportStore();
</script>

<style scoped>
.hint {
  margin-bottom: 12px;
}
</style>
