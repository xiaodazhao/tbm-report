import { useEffect, useMemo, useState } from "react";
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import api, { getApiErrorMessage } from "@/api/client";

export default function RiskProfilePage({ date }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!date) return;
    setData(null);
    setError("");
    api
      .get(`/api/tbm/risk_profile?date=${date}`)
      .then((res) => setData(res.data || {}))
      .catch((err) => {
        console.error("空间风险剖面加载失败", err);
        setError(getApiErrorMessage(err, "空间风险剖面加载失败。"));
      });
  }, [date]);

  const riskProfile = data?.risk_profile || {};
  const profile = riskProfile?.profile || [];
  const speedProfile = data?.speed_profile || [];

  const mergedData = useMemo(() => {
    const speedMap = new Map();
    speedProfile.forEach((row) => {
      speedMap.set(Number(row.chainage), firstNumeric(row, ["chainage"]));
    });
    return profile.map((row) => ({
      chainage: Number(row.chainage),
      active_source_count: Number(row.active_source_count || 0),
      speed: speedMap.get(Number(row.chainage)) ?? null,
    }));
  }, [profile, speedProfile]);

  if (error) return <Empty text={error} />;
  if (!data) return <Empty text="正在加载空间风险剖面..." />;

  return (
    <div style={styles.wrapper}>
      <section style={styles.infoBox}>
        <div style={styles.infoTitle}>风险与掘进响应关联</div>
        <p style={styles.infoText}>
          该图将地质风险证据源数量与掘进速度沿里程展开，用于观察高风险区段是否伴随速度衰减或施工响应异常。
        </p>
      </section>

      <section style={styles.chartCard}>
        <div style={styles.chartTitle}>里程风险剖面</div>
        {mergedData.length === 0 ? (
          <Empty text="暂无可绘制的风险剖面数据" compact />
        ) : (
          <div style={styles.chartInner}>
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={mergedData} margin={{ top: 20, right: 54, left: 12, bottom: 42 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                <XAxis
                  dataKey="chainage"
                  tickFormatter={formatChainage}
                  tick={{ fontSize: 11, fill: "#64748b" }}
                  minTickGap={52}
                />
                <YAxis
                  yAxisId="left"
                  tick={{ fontSize: 12, fill: "#64748b" }}
                  allowDecimals={false}
                />
                <YAxis
                  yAxisId="right"
                  orientation="right"
                  tick={{ fontSize: 12, fill: "#64748b" }}
                />
                <Tooltip
                  labelFormatter={(label) => `里程：${formatChainage(label)}`}
                  formatter={(value, name) => [format(value), name]}
                  contentStyle={styles.tooltip}
                />
                <Legend verticalAlign="top" height={36} />
                <ReferenceLine
                  yAxisId="left"
                  y={4}
                  stroke="#d97706"
                  strokeDasharray="5 5"
                  label={{ value: "关注阈值", fill: "#d97706", fontSize: 12 }}
                />
                <Line
                  yAxisId="left"
                  type="monotone"
                  dataKey="active_source_count"
                  stroke="#dc2626"
                  strokeWidth={3}
                  dot={false}
                  name="风险证据源数量"
                />
                <Line
                  yAxisId="right"
                  type="monotone"
                  dataKey="speed"
                  stroke="#2563eb"
                  strokeWidth={2}
                  strokeDasharray="5 3"
                  dot={false}
                  name="掘进速度"
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
        )}
      </section>
    </div>
  );
}

function Empty({ text, compact = false }) {
  return <div style={{ ...styles.empty, minHeight: compact ? 220 : "100%" }}>{text}</div>;
}

function formatChainage(chainage) {
  const value = Number(chainage);
  if (!Number.isFinite(value)) return "--";
  const km = Math.floor(value / 1000);
  const m = value % 1000;
  return `DK${km}+${m.toFixed(1)}`;
}

function firstNumeric(row, exclude = []) {
  const found = Object.entries(row || {}).find(
    ([key, value]) => !exclude.includes(key) && Number.isFinite(Number(value)),
  );
  return found ? Number(found[1]) : null;
}

function format(v) {
  const n = Number(v);
  return Number.isFinite(n) ? n.toFixed(2) : "--";
}

const styles = {
  wrapper: {
    height: "100%",
    display: "flex",
    flexDirection: "column",
    gap: 14,
  },
  infoBox: {
    background: "#fff",
    border: "1px solid #e2e8f0",
    borderRadius: 12,
    padding: 14,
  },
  infoTitle: {
    color: "#0f172a",
    fontSize: 15,
    fontWeight: 900,
  },
  infoText: {
    color: "#64748b",
    fontSize: 13,
    lineHeight: 1.7,
    margin: "6px 0 0",
  },
  chartCard: {
    flex: 1,
    minHeight: 0,
    background: "#fff",
    border: "1px solid #e2e8f0",
    borderRadius: 12,
    padding: 14,
    display: "flex",
    flexDirection: "column",
  },
  chartTitle: {
    color: "#0f172a",
    fontSize: 15,
    fontWeight: 900,
    marginBottom: 10,
  },
  chartInner: {
    flex: 1,
    minHeight: 290,
  },
  tooltip: {
    borderRadius: 10,
    border: "1px solid #e2e8f0",
    boxShadow: "0 14px 30px rgba(15, 23, 42, 0.12)",
  },
  empty: {
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    color: "#94a3b8",
    textAlign: "center",
  },
};
