<template>
  <div>
    <el-empty v-if="!traceItems.length" description="暂无可展示 trace 项" />
    <el-timeline v-else>
      <el-timeline-item v-for="(item, index) in traceItems" :key="index" :timestamp="item.type">
        <div class="trace-card">
          <strong>{{ item.claim || item.text || `Claim ${index + 1}` }}</strong>
          <p>{{ item.status || item.grounding_status || item.result || "trace item" }}</p>
          <JsonViewer :value="item" />
        </div>
      </el-timeline-item>
    </el-timeline>
  </div>
</template>

<script setup lang="ts">
import { computed } from "vue";
import JsonViewer from "@/components/JsonViewer.vue";

const props = defineProps<{
  trace: Record<string, unknown> | null | undefined;
}>();

const traceItems = computed(() => {
  const trace = props.trace || {};
  const candidates = [
    trace.claim_traces,
    trace.traces,
    trace.items,
    trace.report_trace,
    trace.claims
  ];
  const found = candidates.find(Array.isArray);
  return (found || []) as Array<Record<string, unknown>>;
});
</script>

<style scoped>
.trace-card {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.trace-card strong {
  color: #111827;
}

.trace-card p {
  margin: 0;
  color: #6b7280;
}
</style>
