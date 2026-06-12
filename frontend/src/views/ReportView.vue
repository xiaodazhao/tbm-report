<template>
  <div>
    <h2 class="page-title">日报生成页</h2>
    <p class="page-subtitle">面向普通用户的 TBM 施工日报生成工作台。</p>

    <el-row :gutter="16" align="top">
      <el-col :span="5">
        <div class="panel">
          <h3 class="panel-title">生成设置</h3>
          <DateSelector
            :dates="store.dates"
            :selected-date="store.selectedDate"
            :use-llm="store.useLlm"
            :loading="store.loading"
            button-text="生成日报"
            @update:selected-date="store.selectedDate = $event"
            @update:use-llm="store.useLlm = $event"
            @submit="store.generateReport"
          />
        </div>

        <div class="panel status-panel">
          <h3 class="panel-title">后端状态</h3>
          <el-descriptions :column="1" size="small" border>
            <el-descriptions-item label="状态">
              <el-tag :type="store.health?.ok ? 'success' : 'danger'" effect="plain">
                {{ store.health?.ok ? "在线" : "未连接" }}
              </el-tag>
            </el-descriptions-item>
            <el-descriptions-item label="服务">{{ store.health?.service || "--" }}</el-descriptions-item>
            <el-descriptions-item label="Pipeline">{{ store.health?.pipeline || "--" }}</el-descriptions-item>
          </el-descriptions>
        </div>
      </el-col>

      <el-col :span="13">
        <ReportViewer :text="store.report?.report_text" />
      </el-col>

      <el-col :span="6">
        <div class="panel">
          <h3 class="panel-title">质量与 Trace 摘要</h3>
          <QualityCards :quality="store.report?.quality_summary" :trace="store.report?.trace_summary" />
        </div>

        <WarningPanel class="right-panel" :warnings="store.report?.warnings" />

        <div class="panel right-panel">
          <h3 class="panel-title">High GRCI 简表</h3>
          <HighGrciTable :rows="store.report?.high_grci_cells || []" />
        </div>

        <div class="panel right-panel">
          <h3 class="panel-title">Forward Profile 简表</h3>
          <ForwardProfileTable :rows="forwardRows" />
        </div>
      </el-col>
    </el-row>
  </div>
</template>

<script setup lang="ts">
import { computed } from "vue";
import DateSelector from "@/components/DateSelector.vue";
import ForwardProfileTable from "@/components/ForwardProfileTable.vue";
import HighGrciTable from "@/components/HighGrciTable.vue";
import QualityCards from "@/components/QualityCards.vue";
import ReportViewer from "@/components/ReportViewer.vue";
import WarningPanel from "@/components/WarningPanel.vue";
import { useReportStore } from "@/stores/reportStore";

const store = useReportStore();
const forwardRows = computed(() => store.report?.forward_profile?.forward_attention_cells || []);
</script>

<style scoped>
.status-panel,
.right-panel {
  margin-top: 16px;
}
</style>
