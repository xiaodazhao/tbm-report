<template>
  <article class="report-viewer">
    <el-empty v-if="!text" description="请选择日期并生成日报" />
    <template v-else>
      <section v-for="(block, index) in blocks" :key="index" class="report-block">
        <h2 v-if="block.title">{{ block.title }}</h2>
        <p v-for="(line, lineIndex) in block.lines" :key="lineIndex">{{ line }}</p>
      </section>
    </template>
  </article>
</template>

<script setup lang="ts">
import { computed } from "vue";

const props = defineProps<{
  text?: string;
}>();

const blocks = computed(() => {
  const raw = (props.text || "").replace(/\r\n/g, "\n").trim();
  if (!raw) return [];
  const sections: Array<{ title: string; lines: string[] }> = [];
  let current = { title: "", lines: [] as string[] };
  for (const line of raw.split("\n").map((item) => item.trim()).filter(Boolean)) {
    if (/^\d+[.、]\s*/.test(line) || /^#+\s*/.test(line)) {
      if (current.title || current.lines.length) sections.push(current);
      current = { title: line.replace(/^#+\s*/, ""), lines: [] };
    } else {
      current.lines.push(line);
    }
  }
  if (current.title || current.lines.length) sections.push(current);
  return sections;
});
</script>

<style scoped>
.report-viewer {
  min-height: 680px;
  padding: 28px 34px;
  background: #ffffff;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  line-height: 1.75;
}

.report-block + .report-block {
  margin-top: 22px;
}

h2 {
  margin: 0 0 10px;
  padding-bottom: 8px;
  border-bottom: 1px solid #e5e7eb;
  font-size: 18px;
  color: #111827;
}

p {
  margin: 6px 0;
  color: #374151;
  white-space: pre-wrap;
}
</style>
