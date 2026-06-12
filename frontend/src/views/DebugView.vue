<template>
  <div>
    <h2 class="page-title">调试页</h2>
    <p class="page-subtitle">用于研究、开发和论文复核，展示后端 debug 接口完整中间结果。</p>

    <el-row :gutter="16">
      <el-col :span="5">
        <div class="panel">
          <h3 class="panel-title">Debug 请求</h3>
          <DateSelector
            :dates="store.dates"
            :selected-date="store.selectedDate"
            :use-llm="store.useLlm"
            :loading="store.loading"
            button-text="生成 Debug"
            @update:selected-date="store.selectedDate = $event"
            @update:use-llm="store.useLlm = $event"
            @submit="store.generateDebugReport"
          />
        </div>
      </el-col>

      <el-col :span="19">
        <div class="panel">
          <el-tabs model-value="evidence">
            <el-tab-pane label="Evidence Pack" name="evidence">
              <EvidencePackViewer :value="store.debugReport?.prompt_evidence_pack || {}" />
            </el-tab-pane>
            <el-tab-pane label="Prompt" name="prompt">
              <pre class="prompt-block">{{ store.debugReport?.prompt_text || "暂无 prompt" }}</pre>
            </el-tab-pane>
            <el-tab-pane label="ConstructionStateCells" name="cells">
              <el-table :data="store.debugReport?.construction_state_cells || []" stripe border size="small">
                <el-table-column type="expand">
                  <template #default="{ row }">
                    <JsonViewer :value="row" />
                  </template>
                </el-table-column>
                <el-table-column prop="cell_id" label="cell_id" min-width="180" fixed />
                <el-table-column prop="cell_start" label="start" width="110" />
                <el-table-column prop="cell_end" label="end" width="110" />
                <el-table-column prop="has_plc_response" label="PLC" width="80" />
                <el-table-column prop="has_geology_evidence" label="Geo" width="80" />
                <el-table-column prop="is_forward_cell" label="Forward" width="90" />
                <el-table-column prop="GRS_geo_base" label="GRS" width="100" />
                <el-table-column prop="RAI" label="RAI" width="100" />
                <el-table-column prop="GRCI" label="GRCI" width="100" />
                <el-table-column prop="GRCI_available" label="available" width="110" />
                <el-table-column prop="coupling_level" label="level" width="120" />
              </el-table>
            </el-tab-pane>
            <el-tab-pane label="Quality" name="quality">
              <JsonViewer :value="store.debugReport?.quality || {}" />
            </el-tab-pane>
            <el-tab-pane label="Trace" name="trace">
              <TraceViewer :trace="store.debugReport?.trace" />
            </el-tab-pane>
            <el-tab-pane label="Raw JSON" name="raw">
              <JsonViewer :value="store.debugReport || {}" />
            </el-tab-pane>
          </el-tabs>
        </div>
      </el-col>
    </el-row>
  </div>
</template>

<script setup lang="ts">
import DateSelector from "@/components/DateSelector.vue";
import EvidencePackViewer from "@/components/EvidencePackViewer.vue";
import JsonViewer from "@/components/JsonViewer.vue";
import TraceViewer from "@/components/TraceViewer.vue";
import { useReportStore } from "@/stores/reportStore";

const store = useReportStore();
</script>

<style scoped>
.prompt-block {
  min-height: 520px;
  margin: 0;
  padding: 16px;
  overflow: auto;
  white-space: pre-wrap;
  border-radius: 8px;
  border: 1px solid #e5e7eb;
  background: #f9fafb;
  color: #1f2937;
  line-height: 1.6;
}
</style>
