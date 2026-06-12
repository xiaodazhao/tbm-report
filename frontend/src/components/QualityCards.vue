<template>
  <div class="quality-grid">
    <div class="quality-card">
      <span>质量评分</span>
      <strong>{{ numberValue(quality?.quality_score) }}</strong>
    </div>
    <div class="quality-card">
      <span>Grounding Rate</span>
      <strong>{{ percentValue(quality?.grounding_rate) }}</strong>
    </div>
    <div class="quality-card">
      <span>Unsupported Claims</span>
      <strong>{{ numberValue(quality?.unsupported_claim_count) }}</strong>
    </div>
    <div class="quality-card">
      <span>Trace Coverage</span>
      <strong>{{ percentValue(trace?.trace_coverage) }}</strong>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { QualitySummary, TraceSummary } from "@/types/tbm";

defineProps<{
  quality?: QualitySummary | null;
  trace?: TraceSummary | null;
}>();

function numberValue(value: unknown): string {
  return typeof value === "number" ? value.toFixed(value % 1 === 0 ? 0 : 2) : "--";
}

function percentValue(value: unknown): string {
  return typeof value === "number" ? `${(value * 100).toFixed(0)}%` : "--";
}
</script>

<style scoped>
.quality-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
}

.quality-card {
  padding: 12px;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  background: #f9fafb;
}

.quality-card span {
  display: block;
  color: #6b7280;
  font-size: 12px;
}

.quality-card strong {
  display: block;
  margin-top: 6px;
  font-size: 22px;
  color: #1f4f82;
}
</style>
