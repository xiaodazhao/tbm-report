import { useEffect, useMemo, useRef, useState } from "react";

import { getApiErrorMessage } from "@/api/client";
import { tbmApi } from "@/api/tbm";

const SESSION_STORAGE_KEY = "tbm-agent-session-v2";

const SAMPLE_QUERIES = [
  "先帮我总结今天的整体施工情况",
  "重点解释一下地质高关注区段为什么值得注意",
  "施工状态和效率有没有明显异常",
  "前方 30 米还需要注意什么",
  "和历史记录对比一下今天的变化",
];

const HIGHLIGHT_LABELS = {
  available_date_count: "可用日期数",
  latest_date: "最新日期",
  work_total_min: "工作时长 min",
  stop_total_min: "停机时长 min",
  abnormal_count: "异常次数",
  gas_exceed_types: "气体超限",
  has_geology: "地质数据",
  geology_high_risk_segment_count: "高风险区段",
  geology_multi_source_segment_count: "多源区段",
  top_coupling_segment: "重点区段",
  top_coupling_label: "耦合等级",
  top_coupling_index: "耦合指数",
  forward_advice_level: "前方风险等级",
  forward_main_hazards: "前方主要风险",
  forward_high_risk_count: "前方高风险数",
  current_chainage_dk: "当前里程",
  advance_length_m: "推进长度 m",
  dominant_operation: "主导状态",
  work_ratio: "工作占比",
  has_history: "历史记录",
  history_count: "历史样本数",
  previous_date: "上一记录",
};

function createSessionId() {
  if (typeof window !== "undefined" && window.crypto?.randomUUID) {
    return window.crypto.randomUUID();
  }
  return `tbm-agent-${Date.now()}`;
}

function readStoredSessionId() {
  if (typeof window === "undefined") return createSessionId();
  return window.localStorage.getItem(SESSION_STORAGE_KEY) || createSessionId();
}

function writeStoredSessionId(sessionId) {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(SESSION_STORAGE_KEY, sessionId);
}

function normalizeMessages(messages = []) {
  return messages.map((item, index) => ({
    id: item.message_id ?? `${item.role}-${index}`,
    role: item.role || "assistant",
    createdAt: item.created_at || "",
    payload: item.payload || {},
  }));
}

export default function AgentPage({ date, compact = false }) {
  const [sessionId, setSessionId] = useState(() => readStoredSessionId());
  const [messages, setMessages] = useState([]);
  const [query, setQuery] = useState("");
  const [useLlm, setUseLlm] = useState(false);
  const [verbose, setVerbose] = useState(false);
  const [loading, setLoading] = useState(false);
  const [hydrating, setHydrating] = useState(true);
  const [capabilities, setCapabilities] = useState(null);
  const [error, setError] = useState("");
  const scrollerRef = useRef(null);

  const supervisor = capabilities?.supervisor;
  const agents = useMemo(() => capabilities?.agents || [], [capabilities]);

  useEffect(() => {
    writeStoredSessionId(sessionId);
  }, [sessionId]);

  useEffect(() => {
    tbmApi
      .getAgentV2Capabilities()
      .then((res) => setCapabilities(res.data || null))
      .catch((err) => {
        console.error("Agent V2 capabilities load failed", err);
        setCapabilities(null);
      });
  }, []);

  useEffect(() => {
    hydrateSession(sessionId);
  }, [sessionId]);

  useEffect(() => {
    if (!scrollerRef.current) return;
    scrollerRef.current.scrollTop = scrollerRef.current.scrollHeight;
  }, [messages, loading]);

  async function hydrateSession(activeSessionId) {
    setHydrating(true);
    try {
      const res = await tbmApi.getAgentV2Session(activeSessionId, 40);
      setMessages(normalizeMessages(res.data?.messages || []));
      setError("");
    } catch (err) {
      console.error("Agent session load failed", err);
      setMessages([]);
      setError(getApiErrorMessage(err, "问答会话加载失败，请确认后端服务可用。"));
    } finally {
      setHydrating(false);
    }
  }

  async function handleRun() {
    const cleanQuery = query.trim();
    if (!cleanQuery || loading) return;

    const optimisticUser = {
      id: `pending-user-${Date.now()}`,
      role: "user",
      createdAt: "",
      payload: {
        query: cleanQuery,
        date: date || null,
      },
    };

    setMessages((prev) => [...prev, optimisticUser]);
    setLoading(true);
    setError("");
    setQuery("");

    try {
      const res = await tbmApi.runAgentV2({
        query: cleanQuery,
        date: date || null,
        session_id: sessionId,
        history_limit: 10,
        use_llm: useLlm,
        verbose,
      });

      if (res.data?.success === false) {
        const message = res.data.message || "Agent V2 分析失败。";
        setError(message);
        setMessages((prev) => [
          ...prev,
          {
            id: `error-${Date.now()}`,
            role: "assistant",
            createdAt: "",
            payload: {
              answer: message,
              is_error: true,
            },
          },
        ]);
      } else {
        const result = res.data?.data || res.data;
        const nextSessionId = result.session_id || sessionId;
        if (nextSessionId !== sessionId) {
          setSessionId(nextSessionId);
        } else {
          await hydrateSession(nextSessionId);
        }
      }
    } catch (err) {
      console.error("Agent V2 request failed", err);
      const message = getApiErrorMessage(err, "Agent V2 请求失败，请确认后端 /api/tbm/agent_v2 已启动。");
      setError(message);
      setMessages((prev) => [
        ...prev,
        {
          id: `error-${Date.now()}`,
          role: "assistant",
          createdAt: "",
          payload: {
            answer: message,
            is_error: true,
          },
        },
      ]);
    } finally {
      setLoading(false);
    }
  }

  function handleNewConversation() {
    const nextSessionId = createSessionId();
    setMessages([]);
    setError("");
    setQuery("");
    setSessionId(nextSessionId);
  }

  function handleSample(queryText) {
    setQuery(queryText);
  }

  function handleTextareaKeyDown(event) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      handleRun();
    }
  }

  return (
    <div style={{ ...styles.container, ...(compact ? styles.compactContainer : {}) }}>
      <div style={styles.topBar}>
        <div style={styles.sessionMeta}>
          <div style={styles.sessionTitle}>TBM 多智能体问答</div>
          <div style={styles.sessionSubline}>
            <span>当前日期：{date || "自动使用最近数据"}</span>
            <span>会话：{shortSessionId(sessionId)}</span>
          </div>
        </div>
        <div style={styles.topActions}>
          <Toggle checked={useLlm} onChange={setUseLlm} label="LLM 润色" />
          <Toggle checked={verbose} onChange={setVerbose} label="完整详情" />
          <button type="button" onClick={handleNewConversation} style={styles.secondaryButton}>
            新对话
          </button>
        </div>
      </div>

      <div ref={scrollerRef} style={styles.messageScroller}>
        {hydrating ? (
          <div style={styles.statusCard}>正在恢复会话记录...</div>
        ) : messages.length === 0 ? (
          <div style={styles.emptyState}>
            <div style={styles.emptyTitle}>从一个工程问题开始</div>
            <p style={styles.emptyText}>
              现在的问答支持会话记忆。你可以先问整体情况，再继续追问“为什么”“哪一段更值得注意”“和昨天比有什么变化”。
            </p>
            <div style={styles.sampleGrid}>
              {SAMPLE_QUERIES.map((item) => (
                <button
                  key={item}
                  type="button"
                  onClick={() => handleSample(item)}
                  style={styles.sampleButton}
                >
                  {item}
                </button>
              ))}
            </div>
          </div>
        ) : (
          messages.map((message) => (
            <MessageBubble key={message.id} message={message} />
          ))
        )}

        {loading && <div style={styles.statusCard}>正在调度专家并生成回答...</div>}
        {error && <div style={styles.errorCard}>{error}</div>}
      </div>

      <div style={styles.composer}>
        <div style={styles.sampleRow}>
          {SAMPLE_QUERIES.map((item) => (
            <button key={item} type="button" onClick={() => handleSample(item)} style={styles.inlineSample}>
              {item}
            </button>
          ))}
        </div>
        <div style={styles.composerRow}>
          <textarea
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            onKeyDown={handleTextareaKeyDown}
            placeholder="输入你的问题。Shift + Enter 换行，Enter 直接发送。"
            style={styles.textarea}
          />
          <button
            type="button"
            onClick={handleRun}
            disabled={loading || !query.trim()}
            style={{
              ...styles.primaryButton,
              opacity: loading || !query.trim() ? 0.55 : 1,
            }}
          >
            {loading ? "分析中" : "发送"}
          </button>
        </div>
      </div>

      <details style={styles.capabilityPanel}>
        <summary style={styles.capabilitySummary}>
          {supervisor?.name || "TBMSupervisorAgent"} · {supervisor?.planning_mode || "contextual-supervisor"}
        </summary>
        <div style={styles.capabilityMeta}>
          <span>会话记忆：{supervisor?.session_memory ? "已启用" : "未启用"}</span>
          <span>规划模式：{supervisor?.planning_mode || "--"}</span>
        </div>
        <div style={styles.agentGrid}>
          {agents.map((agent) => (
            <div key={agent.name} style={styles.agentCard}>
              <strong>{agent.name}</strong>
              <span>{agent.description}</span>
              <em>{(agent.tools || []).join("，")}</em>
            </div>
          ))}
        </div>
      </details>
    </div>
  );
}

function MessageBubble({ message }) {
  if (message.role === "user") {
    return (
      <div style={styles.userRow}>
        <div style={styles.userBubble}>
          <div style={styles.bubbleMeta}>
            <span>你</span>
            {message.payload?.date && <span>{message.payload.date}</span>}
          </div>
          <div style={styles.userText}>{message.payload?.query || ""}</div>
        </div>
      </div>
    );
  }

  const payload = message.payload || {};
  const highlights = buildHighlightItems(payload.highlights || {});
  const warnings = payload.highlights?.warnings || [];

  return (
    <div style={styles.assistantRow}>
      <div style={styles.assistantBubble}>
        <div style={styles.assistantHeader}>
          <div>
            <strong>TBM Supervisor</strong>
            <div style={styles.bubbleMeta}>
              <span>{payload.date || "最近数据"}</span>
              <span>{(payload.routed_agents || []).join(" / ") || "待路由"}</span>
            </div>
          </div>
          <div style={styles.modeChip}>{payload.mode || "supervisor_v2"}</div>
        </div>

        <div
          style={{
            ...styles.answerText,
            ...(payload.is_error ? styles.errorAnswer : {}),
          }}
        >
          {payload.answer || "暂无回答。"}
        </div>

        {payload.context_summary && (
          <div style={styles.contextBar}>
            <span>会话记忆：{payload.context_summary.has_history ? "已使用" : "首次提问"}</span>
            <span>继承日期：{payload.context_summary.inherited_date || "--"}</span>
            <span>上轮焦点：{payload.context_summary.last_focus_segment || "--"}</span>
          </div>
        )}

        {highlights.length > 0 && (
          <div style={styles.highlightGrid}>
            {highlights.map((item) => (
              <div key={item.key} style={styles.highlightItem}>
                <span>{item.label}</span>
                <strong>{item.value}</strong>
              </div>
            ))}
          </div>
        )}

        {warnings.length > 0 && (
          <div style={styles.warningList}>
            {warnings.map((item, index) => (
              <div key={`${item.tool || "warning"}-${index}`} style={styles.warningItem}>
                {item.agent ? `${item.agent}.${item.tool}` : "Warning"}：{item.message}
              </div>
            ))}
          </div>
        )}

        {(payload.supervisor_plan || []).length > 0 && (
          <details style={styles.detailBlock}>
            <summary>调度计划</summary>
            <div style={styles.planList}>
              {payload.supervisor_plan.map((step, index) => (
                <div key={`${step.agent}-${index}`} style={styles.planItem}>
                  <div style={styles.planHead}>
                    <span style={styles.planIndex}>{index + 1}</span>
                    <strong>{step.agent}</strong>
                    <span>{(step.tools || []).join(" / ")}</span>
                  </div>
                  <p>{step.reason || "按上下文进行路由。"}</p>
                </div>
              ))}
            </div>
          </details>
        )}

        {(payload.tool_results || []).length > 0 && (
          <details style={styles.detailBlock}>
            <summary>工具执行结果</summary>
            <div style={styles.traceList}>
              {payload.tool_results.map((item, index) => (
                <ToolTrace key={`${item.agent}-${item.tool}-${index}`} item={item} />
              ))}
            </div>
          </details>
        )}

        {payload.verbose && payload.context_messages && (
          <details style={styles.detailBlock}>
            <summary>会话上下文快照</summary>
            <pre style={styles.jsonBlock}>{JSON.stringify(payload.context_messages, null, 2)}</pre>
          </details>
        )}
      </div>
    </div>
  );
}

function ToolTrace({ item }) {
  const resolved = normalizeToolTraceItem(item);
  const summary = resolved.summary || {};
  return (
    <div style={styles.traceCard}>
      <div style={styles.traceHeader}>
        <span style={styles.traceAgent}>{resolved.agent}</span>
        <span style={styles.traceTool}>{resolved.tool}</span>
        <span style={resolved.success ? styles.traceOk : styles.traceFail}>
          {resolved.success ? "成功" : "失败"}
        </span>
      </div>
      {resolved.message && <div style={styles.traceMessage}>{resolved.message}</div>}
      {Object.keys(summary).length > 0 && (
        <div style={styles.summaryGrid}>
          {Object.entries(summary).map(([key, value]) => (
            <div key={key} style={styles.summaryItem}>
              <span>{formatKey(key)}</span>
              <strong>{formatValue(value)}</strong>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function normalizeToolTraceItem(item = {}) {
  const nested = item.result || {};
  const success = typeof item.success === "boolean" ? item.success : !!nested.success;
  const message = item.message || nested.message || "";
  const summary =
    item.summary ||
    buildSummaryFromVerboseData(item.tool || nested.tool, nested.data || {});

  return {
    agent: item.agent || nested.agent || "--",
    tool: item.tool || nested.tool || "--",
    success,
    message,
    summary,
  };
}

function buildSummaryFromVerboseData(tool, data) {
  if (!data || typeof data !== "object") return {};

  if (tool === "analyze_day") {
    return {
      date: data.date,
      operation: data.operation,
      geology: data.geology,
      forward_risk: data.forward_risk,
      coupling: data.coupling,
    };
  }

  if (tool === "analyze_forward_risk") {
    return {
      date: data.date,
      forward_risk: data.forward_risk,
      forward_risk_text: data.forward_risk_text,
    };
  }

  if (tool === "analyze_operation") {
    return {
      date: data.date,
      stats: data.stats,
      state_stats: data.state_stats,
    };
  }

  if (tool === "analyze_geology") {
    return {
      date: data.date,
      segment_summary: data.segment_summary,
      coupling_summary: data.coupling_summary,
      segment_count: data.segment_count,
    };
  }

  if (tool === "analyze_gas") {
    return {
      date: data.date,
      exceed_types: data.exceed_types,
      gas_stats: data.gas_stats,
    };
  }

  if (tool === "get_digital_twin_state") {
    return {
      date: data.date,
      digital_twin_state: data.digital_twin_state,
    };
  }

  if (tool === "compare_history") {
    return {
      date: data.date,
      history_comparison: data.history_comparison,
    };
  }

  if (tool === "risk_profile") {
    return {
      date: data.date,
      risk_profile: data.risk_profile,
      speed_profile_count: Array.isArray(data.speed_profile) ? data.speed_profile.length : 0,
    };
  }

  if (tool === "load_day") {
    return data;
  }

  if (tool === "list_dates") {
    return {
      date_count: Array.isArray(data.dates) ? data.dates.length : 0,
      preview_dates: Array.isArray(data.dates) ? data.dates.slice(0, 8) : [],
    };
  }

  return data;
}

function Toggle({ checked, onChange, label }) {
  return (
    <label style={styles.toggleLabel}>
      <input type="checkbox" checked={checked} onChange={(event) => onChange(event.target.checked)} />
      {label}
    </label>
  );
}

function buildHighlightItems(highlights = {}) {
  return Object.entries(highlights)
    .filter(([key, value]) => key !== "warnings" && value !== undefined && value !== null)
    .map(([key, value]) => ({
      key,
      label: HIGHLIGHT_LABELS[key] || formatKey(key),
      value: key === "work_ratio" ? formatPercent(value) : formatValue(value),
    }));
}

function shortSessionId(sessionId) {
  if (!sessionId) return "--";
  return sessionId.length > 12 ? `${sessionId.slice(0, 6)}...${sessionId.slice(-4)}` : sessionId;
}

function formatKey(key) {
  return String(key).replaceAll("_", " ");
}

function formatPercent(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) return "--";
  return `${(number * 100).toFixed(1)}%`;
}

function formatValue(value) {
  if (Array.isArray(value)) {
    return value.length ? value.join("，") : "--";
  }
  if (typeof value === "boolean") {
    return value ? "有" : "无";
  }
  if (typeof value === "number") {
    return Number.isInteger(value) ? String(value) : value.toFixed(3);
  }
  if (value && typeof value === "object") {
    return JSON.stringify(value);
  }
  return value === "" || value === undefined || value === null ? "--" : String(value);
}

const styles = {
  container: {
    height: "100%",
    minHeight: 0,
    display: "grid",
    gridTemplateRows: "auto minmax(0, 1fr) auto auto",
    gap: 14,
  },
  compactContainer: {
    padding: 0,
  },
  topBar: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "flex-start",
    gap: 12,
    flexWrap: "wrap",
  },
  sessionMeta: {
    display: "flex",
    flexDirection: "column",
    gap: 4,
    minWidth: 0,
  },
  sessionTitle: {
    fontSize: 19,
    fontWeight: 900,
    color: "#0f172a",
  },
  sessionSubline: {
    display: "flex",
    gap: 10,
    flexWrap: "wrap",
    color: "#64748b",
    fontSize: 12,
  },
  topActions: {
    display: "flex",
    alignItems: "center",
    gap: 12,
    flexWrap: "wrap",
  },
  toggleLabel: {
    display: "inline-flex",
    alignItems: "center",
    gap: 6,
    color: "#475569",
    fontSize: 12,
    whiteSpace: "nowrap",
  },
  secondaryButton: {
    border: "1px solid #cbd5e1",
    borderRadius: 999,
    background: "#fff",
    color: "#334155",
    fontWeight: 800,
    cursor: "pointer",
    padding: "8px 12px",
  },
  messageScroller: {
    minHeight: 0,
    overflow: "auto",
    paddingRight: 4,
    display: "flex",
    flexDirection: "column",
    gap: 12,
  },
  statusCard: {
    borderRadius: 14,
    padding: "14px 16px",
    border: "1px solid #dbeafe",
    background: "#eff6ff",
    color: "#1d4ed8",
    fontSize: 13,
    fontWeight: 700,
  },
  errorCard: {
    borderRadius: 14,
    padding: "14px 16px",
    border: "1px solid #fecaca",
    background: "#fef2f2",
    color: "#b91c1c",
    fontSize: 13,
    fontWeight: 700,
  },
  emptyState: {
    borderRadius: 18,
    border: "1px dashed #cbd5e1",
    background: "linear-gradient(180deg, #f8fafc 0%, #ffffff 100%)",
    padding: 20,
    display: "flex",
    flexDirection: "column",
    gap: 14,
  },
  emptyTitle: {
    fontSize: 16,
    fontWeight: 900,
    color: "#0f172a",
  },
  emptyText: {
    margin: 0,
    color: "#475569",
    fontSize: 14,
    lineHeight: 1.7,
  },
  sampleGrid: {
    display: "grid",
    gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))",
    gap: 10,
  },
  sampleButton: {
    border: "1px solid #cbd5e1",
    borderRadius: 12,
    background: "#fff",
    color: "#0f172a",
    padding: "12px 14px",
    textAlign: "left",
    lineHeight: 1.6,
    cursor: "pointer",
  },
  userRow: {
    display: "flex",
    justifyContent: "flex-end",
  },
  assistantRow: {
    display: "flex",
    justifyContent: "flex-start",
  },
  userBubble: {
    maxWidth: "88%",
    borderRadius: "18px 18px 4px 18px",
    background: "#0f766e",
    color: "#fff",
    padding: "14px 16px",
    boxShadow: "0 12px 28px rgba(15, 118, 110, 0.16)",
  },
  assistantBubble: {
    width: "min(100%, 920px)",
    borderRadius: "18px 18px 18px 6px",
    background: "#ffffff",
    border: "1px solid #dbe4ee",
    padding: "16px 16px 14px",
    display: "flex",
    flexDirection: "column",
    gap: 12,
    boxShadow: "0 14px 36px rgba(15, 23, 42, 0.08)",
  },
  assistantHeader: {
    display: "flex",
    justifyContent: "space-between",
    gap: 12,
    alignItems: "flex-start",
    flexWrap: "wrap",
  },
  bubbleMeta: {
    marginTop: 4,
    display: "flex",
    gap: 10,
    flexWrap: "wrap",
    color: "rgba(255,255,255,0.76)",
    fontSize: 12,
  },
  userText: {
    marginTop: 6,
    whiteSpace: "pre-wrap",
    lineHeight: 1.7,
    wordBreak: "break-word",
  },
  modeChip: {
    borderRadius: 999,
    background: "#ecfeff",
    border: "1px solid #99f6e4",
    color: "#0f766e",
    padding: "6px 10px",
    fontSize: 12,
    fontWeight: 800,
    whiteSpace: "nowrap",
  },
  answerText: {
    whiteSpace: "pre-wrap",
    lineHeight: 1.75,
    color: "#0f172a",
    wordBreak: "break-word",
    fontSize: 14,
  },
  errorAnswer: {
    color: "#b91c1c",
  },
  contextBar: {
    display: "flex",
    flexWrap: "wrap",
    gap: 10,
    fontSize: 12,
    color: "#64748b",
    padding: "10px 12px",
    borderRadius: 12,
    background: "#f8fafc",
    border: "1px solid #e2e8f0",
  },
  highlightGrid: {
    display: "grid",
    gridTemplateColumns: "repeat(auto-fit, minmax(140px, 1fr))",
    gap: 8,
  },
  highlightItem: {
    border: "1px solid #e2e8f0",
    borderRadius: 12,
    background: "#f8fafc",
    padding: "10px 12px",
    display: "flex",
    flexDirection: "column",
    gap: 4,
    minWidth: 0,
  },
  warningList: {
    display: "flex",
    flexDirection: "column",
    gap: 8,
  },
  warningItem: {
    borderRadius: 12,
    background: "#fff7ed",
    border: "1px solid #fed7aa",
    color: "#9a3412",
    padding: "10px 12px",
    fontSize: 12,
    lineHeight: 1.6,
  },
  detailBlock: {
    borderRadius: 12,
    border: "1px solid #e2e8f0",
    background: "#fff",
    padding: "10px 12px",
  },
  planList: {
    marginTop: 10,
    display: "flex",
    flexDirection: "column",
    gap: 8,
  },
  planItem: {
    border: "1px solid #dbeafe",
    borderRadius: 10,
    background: "#eff6ff",
    padding: 10,
  },
  planHead: {
    display: "flex",
    alignItems: "center",
    gap: 8,
    flexWrap: "wrap",
    color: "#1e3a8a",
    fontSize: 13,
  },
  planIndex: {
    width: 22,
    height: 22,
    borderRadius: 999,
    background: "#2563eb",
    color: "#fff",
    display: "inline-flex",
    alignItems: "center",
    justifyContent: "center",
    fontWeight: 900,
    flexShrink: 0,
  },
  traceList: {
    marginTop: 10,
    display: "flex",
    flexDirection: "column",
    gap: 8,
  },
  traceCard: {
    border: "1px solid #e2e8f0",
    borderRadius: 10,
    padding: 10,
    background: "#fff",
  },
  traceHeader: {
    display: "grid",
    gridTemplateColumns: "minmax(84px, auto) minmax(0, 1fr) auto",
    gap: 8,
    alignItems: "center",
    fontSize: 12,
  },
  traceAgent: {
    color: "#0f172a",
    fontWeight: 900,
  },
  traceTool: {
    color: "#475569",
    overflow: "hidden",
    textOverflow: "ellipsis",
    whiteSpace: "nowrap",
  },
  traceOk: {
    color: "#15803d",
    fontWeight: 900,
  },
  traceFail: {
    color: "#b91c1c",
    fontWeight: 900,
  },
  traceMessage: {
    marginTop: 6,
    color: "#64748b",
    fontSize: 12,
  },
  summaryGrid: {
    marginTop: 8,
    display: "grid",
    gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))",
    gap: 8,
  },
  summaryItem: {
    display: "flex",
    justifyContent: "space-between",
    gap: 10,
    color: "#64748b",
    fontSize: 12,
    minWidth: 0,
    padding: "8px 10px",
    borderRadius: 10,
    background: "#f8fafc",
  },
  composer: {
    display: "flex",
    flexDirection: "column",
    gap: 10,
    paddingTop: 8,
    borderTop: "1px solid #e2e8f0",
  },
  sampleRow: {
    display: "flex",
    gap: 8,
    flexWrap: "wrap",
  },
  inlineSample: {
    border: "1px solid #dbe4ee",
    borderRadius: 999,
    background: "#fff",
    color: "#475569",
    padding: "6px 10px",
    fontSize: 12,
    cursor: "pointer",
  },
  composerRow: {
    display: "grid",
    gridTemplateColumns: "1fr 100px",
    gap: 12,
    alignItems: "stretch",
  },
  textarea: {
    minHeight: 86,
    resize: "vertical",
    border: "1px solid #cbd5e1",
    borderRadius: 14,
    padding: "12px 14px",
    fontSize: 14,
    lineHeight: 1.6,
    outline: "none",
  },
  primaryButton: {
    border: "none",
    borderRadius: 14,
    background: "#0f766e",
    color: "#fff",
    fontWeight: 900,
    cursor: "pointer",
    boxShadow: "0 16px 34px rgba(15, 118, 110, 0.22)",
  },
  capabilityPanel: {
    borderRadius: 14,
    border: "1px solid #dbe4ee",
    background: "#f8fafc",
    padding: "10px 12px",
  },
  capabilitySummary: {
    cursor: "pointer",
    fontWeight: 800,
    color: "#0f172a",
  },
  capabilityMeta: {
    marginTop: 10,
    display: "flex",
    gap: 12,
    flexWrap: "wrap",
    color: "#64748b",
    fontSize: 12,
  },
  agentGrid: {
    marginTop: 12,
    display: "grid",
    gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))",
    gap: 10,
  },
  agentCard: {
    border: "1px solid #e2e8f0",
    borderRadius: 12,
    background: "#fff",
    padding: "10px 12px",
    display: "flex",
    flexDirection: "column",
    gap: 4,
    color: "#475569",
    fontSize: 12,
  },
  jsonBlock: {
    maxHeight: 280,
    overflow: "auto",
    margin: "10px 0 0",
    padding: 10,
    background: "#0f172a",
    color: "#e2e8f0",
    borderRadius: 10,
    fontSize: 12,
  },
};
