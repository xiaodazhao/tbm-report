import axios from "axios";
import type { DebugReportResponse, HealthResponse, ReportResponse } from "@/types/tbm";

const apiBaseUrl = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

const client = axios.create({
  baseURL: apiBaseUrl,
  timeout: 120000
});

function normalizeError(error: unknown): Error {
  if (axios.isAxiosError(error)) {
    if (!error.response) {
      return new Error("无法连接后端，请确认 FastAPI 服务已启动。");
    }
    const detail = error.response.data?.detail;
    const message = Array.isArray(detail)
      ? detail.map((item) => item.msg || JSON.stringify(item)).join("；")
      : detail || error.message;
    return new Error(`请求失败：${message}`);
  }
  return error instanceof Error ? error : new Error("请求失败：未知错误");
}

export async function getHealth(): Promise<HealthResponse> {
  try {
    const response = await client.get<HealthResponse>("/api/tbm/health");
    return response.data;
  } catch (error) {
    throw normalizeError(error);
  }
}

export async function getDates(): Promise<string[]> {
  try {
    const response = await client.get<{ dates: string[] }>("/api/tbm/dates");
    return response.data.dates || [];
  } catch (error) {
    throw normalizeError(error);
  }
}

export async function generateReport(date: string, useLlm: boolean): Promise<ReportResponse> {
  try {
    const response = await client.post<ReportResponse>("/api/tbm/report", {
      date,
      use_llm: useLlm
    });
    return response.data;
  } catch (error) {
    throw normalizeError(error);
  }
}

export async function generateDebugReport(date: string, useLlm: boolean): Promise<DebugReportResponse> {
  try {
    const response = await client.post<DebugReportResponse>("/api/tbm/report/debug", {
      date,
      use_llm: useLlm
    });
    return response.data;
  } catch (error) {
    throw normalizeError(error);
  }
}
