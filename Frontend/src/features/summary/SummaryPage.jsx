import { useEffect, useMemo, useState } from "react";
import { Cell, Legend, Pie, PieChart, ResponsiveContainer, Tooltip } from "recharts";

import api, { getApiErrorMessage } from "@/api/client";

export default function SummaryPage({ date }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!date) return;
    setData(null);
    setError("");
    api
      .get(`/api/tbm/summary?date=${date}`)
      .then((res) => setData(res.data || {}))
      .catch((err) => {
        console.error("概览数据加载失败", err);
        setError(getApiErrorMessage(err, "概览数据加载失败。"));
      });
  }, [date]);

  const pieData = useMemo(() => {
    if (!data) return [];
    return [
      { name: "掘进", value: number(data.work_total_min), color: "#0f766e" },
      { name: "停机", value: number(data.stop_total_min), color: "#dc2626" },
      { name: "过渡", value: number(data.transition_total_min), color: "#2563eb" },
      { name: "异常", value: number(data.abnormal_total_min), color: "#d97706" },
    ].filter((item) => item.value > 0);
  }, [data]);

  if (error) return <Empty text={error} />;
  if (!data) return <Empty text="正在加载工况概览..." />;

  return (
    <div style={styles.wrapper}>
      <div style={styles.statGrid}>
        <StatCard label="掘进次数" value={data.work_count} tone="green" />
        <StatCard label="停机次数" value={data.stop_count} tone="red" />
        <StatCard label="掘进时长" value={format(data.work_total_min)} unit="分钟" tone="blue" />
        <StatCard label="停机时长" value={format(data.stop_total_min)} unit="分钟" tone="amber" />
      </div>

      <div style={styles.statGrid}>
        <StatCard label="高风险区段" value={data.geology_high_risk_segment_count} tone="red" />
        <StatCard label="多源证据区段" value={data.geology_multi_source_segment_count} tone="amber" />
        <StatCard label="异常片段" value={data.abnormal_count} tone="slate" />
        <StatCard label="过渡片段" value={data.transition_count} tone="blue" />
      </div>

      <section style={styles.chartCard}>
        <div style={styles.sectionTitle}>工况时间占比</div>
        {pieData.length ? (
          <ResponsiveContainer width="100%" height={260}>
            <PieChart>
              <Pie
                data={pieData}
                dataKey="value"
                nameKey="name"
                cx="50%"
                cy="48%"
                outerRadius={88}
                innerRadius={52}
                paddingAngle={4}
              >
                {pieData.map((item) => (
                  <Cell key={item.name} fill={item.color} />
                ))}
              </Pie>
              <Tooltip formatter={(value) => [`${Number(value).toFixed(1)} 分钟`, "时长"]} />
              <Legend verticalAlign="bottom" height={32} />
            </PieChart>
          </ResponsiveContainer>
        ) : (
          <Empty text="暂无可绘制的工况占比数据" />
        )}
      </section>
    </div>
  );
}

function StatCard({ label, value, unit, tone }) {
  const colors = {
    green: ["#ecfdf5", "#0f766e"],
    red: ["#fef2f2", "#dc2626"],
    blue: ["#eff6ff", "#2563eb"],
    amber: ["#fffbeb", "#d97706"],
    slate: ["#f8fafc", "#475569"],
  };
  const [bg, color] = colors[tone] || colors.slate;

  return (
    <div style={styles.statCard}>
      <div style={styles.statLabel}>{label}</div>
      <div style={{ ...styles.statValue, color }}>
        {value ?? 0}
        {unit && <span style={styles.unit}>{unit}</span>}
      </div>
      <div style={{ ...styles.statBar, background: bg }}>
        <span style={{ ...styles.statBarInner, background: color }} />
      </div>
    </div>
  );
}

function Empty({ text }) {
  return <div style={styles.empty}>{text}</div>;
}

function number(v) {
  const n = Number(v);
  return Number.isFinite(n) ? n : 0;
}

function format(v) {
  const n = Number(v);
  return Number.isFinite(n) ? n.toFixed(1) : "--";
}

const styles = {
  wrapper: {
    display: "flex",
    flexDirection: "column",
    gap: 16,
    height: "100%",
  },
  statGrid: {
    display: "grid",
    gridTemplateColumns: "repeat(2, minmax(0, 1fr))",
    gap: 12,
  },
  statCard: {
    background: "#fff",
    border: "1px solid #e2e8f0",
    borderRadius: 12,
    padding: 14,
    minHeight: 104,
    boxShadow: "0 8px 22px rgba(15, 23, 42, 0.05)",
  },
  statLabel: {
    color: "#64748b",
    fontSize: 13,
    marginBottom: 8,
  },
  statValue: {
    fontSize: 26,
    fontWeight: 900,
    lineHeight: 1.15,
  },
  unit: {
    marginLeft: 4,
    fontSize: 12,
    color: "#94a3b8",
    fontWeight: 700,
  },
  statBar: {
    height: 5,
    borderRadius: 999,
    overflow: "hidden",
    marginTop: 12,
  },
  statBarInner: {
    display: "block",
    width: "58%",
    height: "100%",
    borderRadius: 999,
  },
  chartCard: {
    background: "#fff",
    border: "1px solid #e2e8f0",
    borderRadius: 12,
    padding: 14,
    minHeight: 312,
  },
  sectionTitle: {
    fontSize: 15,
    fontWeight: 800,
    color: "#0f172a",
    marginBottom: 8,
  },
  empty: {
    minHeight: 160,
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    color: "#94a3b8",
    textAlign: "center",
  },
};
