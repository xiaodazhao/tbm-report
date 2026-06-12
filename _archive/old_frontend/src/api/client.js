import axios from "axios";

const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000",
  timeout: 60000,
});

function isWrappedApiResponse(data) {
  return (
    data &&
    typeof data === "object" &&
    typeof data.ok === "boolean" &&
    Object.prototype.hasOwnProperty.call(data, "data")
  );
}

function buildMeta(data) {
  return {
    ok: data.ok,
    message: data.message || "",
    warnings: Array.isArray(data.warnings) ? data.warnings : [],
    ...(data.meta && typeof data.meta === "object" ? data.meta : {}),
  };
}

function unwrapPayload(data) {
  const payload = data.data;
  const meta = buildMeta(data);

  if (payload && typeof payload === "object" && !Array.isArray(payload)) {
    return { ...payload, __meta: meta };
  }

  return {
    value: payload,
    __meta: meta,
  };
}

api.interceptors.response.use(
  (response) => {
    if (isWrappedApiResponse(response?.data)) {
      response.data = unwrapPayload(response.data);
    }
    return response;
  },
  (error) => {
    if (isWrappedApiResponse(error?.response?.data)) {
      error.apiMessage = error.response.data.message || "";
      error.apiWarnings = Array.isArray(error.response.data.warnings)
        ? error.response.data.warnings
        : [];
      error.apiMeta = buildMeta(error.response.data);
      error.apiData = error.response.data.data;
    }
    return Promise.reject(error);
  },
);

export function getApiErrorMessage(error, fallback = "请求失败，请稍后重试。") {
  const message =
    error?.apiMessage ||
    error?.response?.data?.message ||
    error?.message ||
    fallback;
  if (typeof message === "string") {
    const normalized = message.trim();
    if (!normalized || normalized === "Network Error" || normalized === "Failed to fetch") {
      return fallback;
    }
  }
  return typeof message === "string" && message.trim() ? message : fallback;
}

export default api;
