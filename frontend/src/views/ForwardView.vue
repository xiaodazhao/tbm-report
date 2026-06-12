<template>
  <div>
    <h2 class="page-title">前方关注提示页</h2>
    <p class="page-subtitle">展示当前掌子面前方可用地质证据形成的关注提示。</p>

    <el-alert
      title="前方关注提示来自当前掌子面前方的可用地质证据，仅表示关注/提示，不表示已发生事实，也不使用 GRCI。"
      type="warning"
      show-icon
      :closable="false"
      class="semantic-warning"
    />

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

        <div class="panel meta-panel">
          <h3 class="panel-title">Forward Profile 元信息</h3>
          <el-descriptions :column="1" size="small" border>
            <el-descriptions-item label="当前里程">
              {{ store.report?.forward_profile?.current_chainage ?? "--" }}
            </el-descriptions-item>
            <el-descriptions-item label="lookahead">
              {{ store.report?.forward_profile?.lookahead_m ?? "--" }}
            </el-descriptions-item>
          </el-descriptions>
        </div>
      </el-col>

      <el-col :span="19">
        <div class="panel">
          <h3 class="panel-title">Forward Attention Cells</h3>
          <ForwardProfileTable :rows="forwardRows" />
        </div>

        <div class="panel profile-panel">
          <h3 class="panel-title">forward_profile 原始摘要</h3>
          <JsonViewer :value="store.report?.forward_profile || {}" />
        </div>
      </el-col>
    </el-row>
  </div>
</template>

<script setup lang="ts">
import { computed } from "vue";
import DateSelector from "@/components/DateSelector.vue";
import ForwardProfileTable from "@/components/ForwardProfileTable.vue";
import JsonViewer from "@/components/JsonViewer.vue";
import { useReportStore } from "@/stores/reportStore";

const store = useReportStore();
const forwardRows = computed(() => store.report?.forward_profile?.forward_attention_cells || []);
</script>

<style scoped>
.semantic-warning {
  margin-bottom: 16px;
}

.meta-panel,
.profile-panel {
  margin-top: 16px;
}
</style>
