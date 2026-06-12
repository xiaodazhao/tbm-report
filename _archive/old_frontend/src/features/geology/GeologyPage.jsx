import { useEffect, useMemo, useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import api, { getApiErrorMessage } from "@/api/client";

export default function GeologyPage({ date }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!date) return;
    setData(null);
    setError("");
    api
      .get(`/api/tbm/geology?date=${date}`)
      .then((res) => setData(res.data || {}))
      .catch((err) => {
        console.error("地质融合数据加载失败", err);
        setError(getApiErrorMessage(err, "地质融合数据加载失败。"));
      });
  }, [date]);

  const segmentSummary = data?.segment_summary || {};
  const recordSummary = data?.record_summary || {};
  const typicalSegments = data?.typical_segments || [];

  const barData = useMemo(() => {
    const counts = recordSummary?.risk_counts || {};
    return [
      { name: "低风险", value: Number(counts.low || 0), color: "#0f766e" },
      { name: "中风险", value: Number(counts.medium || 0), color: "#d97706" },
      { name: "高风险", value: Number(counts.high || 0), color: "#dc2626" },
    ];
  }, [recordSummary]);

  if (error) return <Empty text={error} />;
  if (!data) return <Empty text="正在加载地质融合数据..." />;

  return (
    <div style={styles.wrapper}>
      <div style={styles.kpiGrid}>
        <Kpi label="高风险区段" value={segmentSummary.high_risk_segment_count ?? 0} tone="red" />
        <Kpi label="多源证据区段" value={segmentSummary.multi_source_segment_count ?? 0} tone="amber" />
        <Kpi label="典型区段" value={typicalSegments.length} tone="blue" />
      </div>

      <div style={styles.mainGrid}>
        <section style={styles.sectionCard}>
          <div style={styles.sectionTitle}>区段分析摘要</div>
          <p style={styles.summaryText}>
            {cleanText(segmentSummary.summary_text) || "当前日期暂未形成可用的区段级地质融合摘要。"}
          </p>
        </section>

        <section style={styles.sectionCard}>
          <div style={styles.sectionTitle}>风险等级分布</div>
          <div style={styles.chartWrap}>
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={barData} margin={{ top: 8, right: 10, bottom: 0, left: -24 }}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#e2e8f0" />
                <XAxis dataKey="name" tick={{ fontSize: 12, fill: "#64748b" }} axisLine={false} tickLine={false} />
                <YAxis tick={{ fontSize: 12, fill: "#64748b" }} axisLine={false} tickLine={false} allowDecimals={false} />
                <Tooltip />
                <Bar dataKey="value" radius={[6, 6, 0, 0]}>
                  {barData.map((entry) => (
                    <Cell key={entry.name} fill={entry.color} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </section>
      </div>

      <section style={styles.sectionCard}>
        <details>
          <summary style={styles.summaryTitle}>记录级摘要</summary>
          <p style={styles.summaryText}>
            {cleanText(recordSummary.summary_text) || "当前日期暂未形成可用的记录级地质摘要。"}
          </p>
        </details>
      </section>

      <section style={{ ...styles.sectionCard, flex: 1, minHeight: 0 }}>
        <div style={styles.sectionTitle}>典型风险区段</div>
        {typicalSegments.length === 0 ? (
          <Empty text="暂无典型风险区段" compact />
        ) : (
          <div style={styles.tableWrap}>
            <table style={styles.table}>
              <thead>
                <tr>
                  <th style={styles.th}>区段</th>
                  <th style={styles.th}>风险等级</th>
                  <th style={styles.th}>风险得分</th>
                  <th style={styles.th}>证据源数量</th>
                  <th style={styles.th}>耦合标签</th>
                  <th style={styles.th}>解释</th>
                </tr>
              </thead>
              <tbody>
                {typicalSegments.slice(0, 12).map((row, index) => (
                  <tr key={`${row.segment || index}`}>
                    <td style={styles.td}>{row.segment || "--"}</td>
                    <td style={styles.td}>
                      <RiskBadge risk={row.risk_mode || row.risk || row.fused_grade_mode} />
                    </td>
                    <td style={styles.td}>{format(row.risk_score_max)}</td>
                    <td style={styles.td}>{row.active_source_count_max ?? "--"}</td>
                    <td style={styles.td}>{row.coupling_label || "--"}</td>
                    <td style={{ ...styles.td, minWidth: 220 }}>
                      {cleanText(row.coupling_interpretation || row.interpretation) || "--"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}

function Kpi({ label, value, tone }) {
  const tones = {
    red: ["#fef2f2", "#dc2626"],
    amber: ["#fffbeb", "#d97706"],
    blue: ["#eff6ff", "#2563eb"],
  };
  const [bg, color] = tones[tone] || tones.blue;
  return (
    <div style={{ ...styles.kpi, background: bg }}>
      <span>{label}</span>
      <strong style={{ color }}>{value}</strong>
    </div>
  );
}

function RiskBadge({ risk }) {
  const text = riskText(risk);
  const style = text === "高风险" ? styles.riskHigh : text === "中风险" ? styles.riskMedium : styles.riskLow;
  return <span style={{ ...styles.riskBadge, ...style }}>{text}</span>;
}

function Empty({ text, compact = false }) {
  return <div style={{ ...styles.empty, minHeight: compact ? 96 : "100%" }}>{text}</div>;
}

function riskText(risk) {
  const raw = String(risk || "").toLowerCase();
  if (raw.includes("high") || raw.includes("高")) return "高风险";
  if (raw.includes("medium") || raw.includes("中")) return "中风险";
  if (raw.includes("low") || raw.includes("低")) return "低风险";
  return risk || "--";
}

function format(v) {
  const n = Number(v);
  return Number.isFinite(n) ? n.toFixed(2) : "--";
}

function cleanText(v) {
  if (!v) return "";
  return String(v).replace(/\s+/g, " ").trim();
}

const styles = {
  wrapper: {
    height: "100%",
    display: "flex",
    flexDirection: "column",
    gap: 14,
  },
  kpiGrid: {
    display: "grid",
    gridTemplateColumns: "repeat(3, minmax(0, 1fr))",
    gap: 10,
  },
  kpi: {
    border: "1px solid #e2e8f0",
    borderRadius: 12,
    padding: 12,
    display: "flex",
    flexDirection: "column",
    gap: 6,
  },
  mainGrid: {
    display: "grid",
    gridTemplateColumns: "1.25fr 1fr",
    gap: 14,
  },
  sectionCard: {
    background: "#fff",
    border: "1px solid #e2e8f0",
    borderRadius: 12,
    padding: 14,
  },
  sectionTitle: {
    color: "#0f172a",
    fontSize: 15,
    fontWeight: 900,
    marginBottom: 10,
  },
  summaryTitle: {
    color: "#0f172a",
    fontSize: 15,
    fontWeight: 900,
    cursor: "pointer",
  },
  summaryText: {
    color: "#475569",
    fontSize: 14,
    lineHeight: 1.8,
    margin: "8px 0 0",
  },
  chartWrap: {
    height: 190,
  },
  tableWrap: {
    maxHeight: 300,
    overflow: "auto",
    border: "1px solid #e2e8f0",
    borderRadius: 10,
  },
  table: {
    width: "100%",
    borderCollapse: "collapse",
    fontSize: 13,
  },
  th: {
    position: "sticky",
    top: 0,
    background: "#f8fafc",
    color: "#475569",
    textAlign: "left",
    padding: "10px 12px",
    borderBottom: "1px solid #e2e8f0",
    whiteSpace: "nowrap",
  },
  td: {
    color: "#334155",
    padding: "10px 12px",
    borderBottom: "1px solid #f1f5f9",
    verticalAlign: "top",
    whiteSpace: "nowrap",
  },
  riskBadge: {
    display: "inline-flex",
    borderRadius: 999,
    padding: "3px 9px",
    fontSize: 12,
    fontWeight: 900,
  },
  riskHigh: {
    background: "#fee2e2",
    color: "#b91c1c",
  },
  riskMedium: {
    background: "#fffbeb",
    color: "#b45309",
  },
  riskLow: {
    background: "#dcfce7",
    color: "#166534",
  },
  empty: {
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    color: "#94a3b8",
    textAlign: "center",
  },
};
