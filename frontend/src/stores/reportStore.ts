import { defineStore } from "pinia";
import { generateDebugReport, generateReport, getDates, getHealth } from "@/api/tbm";
import type { DebugReportResponse, HealthResponse, ReportResponse } from "@/types/tbm";

interface ReportState {
  health: HealthResponse | null;
  dates: string[];
  selectedDate: string;
  useLlm: boolean;
  report: ReportResponse | null;
  debugReport: DebugReportResponse | null;
  loading: boolean;
  error: string;
}

export const useReportStore = defineStore("report", {
  state: (): ReportState => ({
    health: null,
    dates: [],
    selectedDate: "",
    useLlm: false,
    report: null,
    debugReport: null,
    loading: false,
    error: ""
  }),
  actions: {
    clearError() {
      this.error = "";
    },
    async loadHealth() {
      try {
        this.health = await getHealth();
      } catch (error) {
        this.health = { ok: false };
        this.error = error instanceof Error ? error.message : "无法连接后端，请确认 FastAPI 服务已启动。";
      }
    },
    async loadDates() {
      try {
        this.dates = await getDates();
        if (!this.selectedDate && this.dates.length > 0) {
          this.selectedDate = this.dates[0];
        }
      } catch (error) {
        this.error = error instanceof Error ? error.message : "请求失败：无法加载日期。";
      }
    },
    async generateReport() {
      if (!this.selectedDate) {
        this.error = "请先选择日期。";
        return;
      }
      this.loading = true;
      this.error = "";
      try {
        this.report = await generateReport(this.selectedDate, this.useLlm);
      } catch (error) {
        this.error = error instanceof Error ? error.message : "请求失败：生成日报失败。";
      } finally {
        this.loading = false;
      }
    },
    async generateDebugReport() {
      if (!this.selectedDate) {
        this.error = "请先选择日期。";
        return;
      }
      this.loading = true;
      this.error = "";
      try {
        this.debugReport = await generateDebugReport(this.selectedDate, this.useLlm);
        this.report = this.debugReport;
      } catch (error) {
        this.error = error instanceof Error ? error.message : "请求失败：生成调试报告失败。";
      } finally {
        this.loading = false;
      }
    }
  }
});
