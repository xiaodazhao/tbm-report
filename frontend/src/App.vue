<template>
  <el-container class="app-shell">
    <el-aside class="app-sidebar" width="244px">
      <div class="brand">
        <div class="brand-mark">TBM</div>
        <div>
          <h1>施工日报工作台</h1>
          <p>Evidence Pack 驱动</p>
        </div>
      </div>

      <el-menu :default-active="route.path" router class="nav-menu">
        <el-menu-item index="/report">日报生成</el-menu-item>
        <el-menu-item index="/cells">高关注区段</el-menu-item>
        <el-menu-item index="/forward">前方关注提示</el-menu-item>
        <el-menu-item index="/debug">调试与追溯</el-menu-item>
      </el-menu>
    </el-aside>

    <el-container>
      <el-header class="app-header">
        <div>
          <strong>TBM Daily Report Backend</strong>
          <span>routes.report → run_daily_report_pipeline</span>
        </div>
        <el-tag :type="store.health?.ok ? 'success' : 'danger'" effect="plain">
          {{ store.health?.ok ? "后端在线" : "后端未连接" }}
        </el-tag>
      </el-header>

      <el-main class="app-main">
        <el-alert
          v-if="store.error"
          :title="store.error"
          type="error"
          show-icon
          closable
          class="global-error"
          @close="store.clearError"
        />
        <router-view />
      </el-main>
    </el-container>
  </el-container>
</template>

<script setup lang="ts">
import { onMounted } from "vue";
import { useRoute } from "vue-router";
import { useReportStore } from "@/stores/reportStore";

const route = useRoute();
const store = useReportStore();

onMounted(async () => {
  await store.loadHealth();
  await store.loadDates();
});
</script>
