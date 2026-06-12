import { useEffect, useMemo, useState } from "react";

import api, { getApiErrorMessage } from "@/api/client";
import GasChart from "./GasChart";

const VIEW_OPTIONS = [
  { key: "all", label: "全部时段" },
  { key: "work", label: "掘进时段" },
  { key: "stop", label: "停机时段" },
];

const GAS_ORDER = ["CH4", "CO2", "H2S", "SO2", "NO2", "NO"];

export default function GasPage({ date }) {
  const [gas, setGas] = useState(null);
  const [error, setError] = useState("");
  const [view, setView] = useState("all");
  const [focusGas, setFocusGas] = useState("");

  useEffect(() => {
    if (!date) return;
    setGas(null);
    setError("");
    api
      .get(`/api/tbm/gas?date=${date}`)
      .then((res) => setGas(res.data || {}))
      .catch((err) => {
        console.error("气体数据加载失败", err);
        setError(getApiErrorMessage(err, "气体监测数据加载失败。"));
      });
  }, [date]);

  const gasView = gas?.[view] || {};
  const gasItems = useMemo(() => {
    const entries = Object.entries(gasView || {}).map(([key, value]) => ({
      key,
      label: gasLabel(key),
      value,
    }));
    return entries.sort((a, b) => GAS_ORDER.indexOf(a.label) - GAS_ORDER.indexOf(b.label));
  }, [gasView]);

  useEffect(() => {
    if (!gasItems.length) return;
    if (!gasItems.some((item) => item.key === focusGas)) {
      setFocusGas(gasItems[0].key);
    }
  }, [gasItems, focusGas]);

  if (error) return <Empty text={error} />;
  if (!gas) return <Empty text="正在加载气体监测数据..." />;

  const current = gasItems.find((item) => item.key === focusGas) || gasItems[0];
  const stats = current?.value || {};
  const exceedCount = Number(stats.exceed_event_count || 0);
  const status = exceedCount > 0 ? "存在超限" : "状态正常";

  return (
    <div style={styles.wrapper}>
      <div style={styles.controls}>
        {VIEW_OPTIONS.map((item) => (
          <button
            key={item.key}
            type="button"
            onClick={() => setView(item.key)}
            style={{
              ...styles.segmentButton,
              ...(view === item.key ? styles.segmentActive : {}),
            }}
          >
            {item.label}
          </button>
        ))}
      </div>

      <div style={styles.controls}>
        {gasItems.map((item) => (
          <button
            key={item.key}
            type="button"
            onClick={() => setFocusGas(item.key)}
            style={{
              ...styles.gasButton,
              ...(focusGas === item.key ? styles.gasActive : {}),
            }}
          >
            {item.label}
          </button>
        ))}
      </div>

      <section style={styles.focusCard}>
        <div style={styles.focusHeader}>
          <div>
            <div style={styles.focusTitle}>{current?.label || "气体"} 重点指标</div>
            <div style={styles.focusSub}>
              当前视图：{VIEW_OPTIONS.find((item) => item.key === view)?.label}
            </div>
          </div>
          <span style={exceedCount > 0 ? styles.badgeDanger : styles.badgeOk}>{status}</span>
        </div>

        <div style={styles.metricGrid}>
          <Metric label="平均值" value={stats.mean} />
          <Metric label="最大值" value={stats.max} />
          <Metric label="最小值" value={stats.min} />
        </div>

        {exceedCount > 0 && (
          <div style={styles.warning}>检测到 {exceedCount} 次超限事件，请重点复核该时段。</div>
        )}
      </section>

      <section style={styles.chartCard}>
        <div style={styles.chartTitle}>气体浓度统计对比</div>
        <div style={styles.chartWrap}>
          <GasChart gasData={gasView} />
        </div>
      </section>
    </div>
  );
}

function Metric({ label, value }) {
  const n = Number(value);
  return (
    <div style={styles.metric}>
      <span>{label}</span>
      <strong>{Number.isFinite(n) ? n.toFixed(3) : "--"}</strong>
    </div>
  );
}

function Empty({ text }) {
  return <div style={styles.empty}>{text}</div>;
}

function gasLabel(key) {
  const upper = String(key).toUpperCase();
  return GAS_ORDER.find((name) => upper.includes(name)) || key;
}

const styles = {
  wrapper: {
    height: "100%",
    display: "flex",
    flexDirection: "column",
    gap: 14,
  },
  controls: {
    display: "flex",
    gap: 8,
    flexWrap: "wrap",
  },
  segmentButton: {
    border: "1px solid #cbd5e1",
    borderRadius: 999,
    background: "#fff",
    color: "#475569",
    padding: "7px 12px",
    fontSize: 13,
    fontWeight: 700,
    cursor: "pointer",
  },
  segmentActive: {
    borderColor: "#0f766e",
    background: "#ccfbf1",
    color: "#0f766e",
  },
  gasButton: {
    border: "1px solid #e2e8f0",
    borderRadius: 8,
    background: "#fff",
    color: "#475569",
    padding: "6px 10px",
    fontSize: 12,
    fontWeight: 800,
    cursor: "pointer",
  },
  gasActive: {
    borderColor: "#f97316",
    background: "#fff7ed",
    color: "#c2410c",
  },
  focusCard: {
    border: "1px solid #e2e8f0",
    borderRadius: 12,
    background: "#fff",
    padding: 14,
  },
  focusHeader: {
    display: "flex",
    justifyContent: "space-between",
    gap: 12,
    alignItems: "center",
    marginBottom: 12,
  },
  focusTitle: {
    color: "#0f172a",
    fontSize: 15,
    fontWeight: 900,
  },
  focusSub: {
    color: "#64748b",
    fontSize: 12,
    marginTop: 3,
  },
  badgeOk: {
    background: "#dcfce7",
    color: "#166534",
    borderRadius: 999,
    padding: "5px 10px",
    fontSize: 12,
    fontWeight: 800,
  },
  badgeDanger: {
    background: "#fee2e2",
    color: "#b91c1c",
    borderRadius: 999,
    padding: "5px 10px",
    fontSize: 12,
    fontWeight: 800,
  },
  metricGrid: {
    display: "grid",
    gridTemplateColumns: "repeat(3, minmax(0, 1fr))",
    gap: 10,
  },
  metric: {
    borderRadius: 10,
    background: "#f8fafc",
    border: "1px solid #e2e8f0",
    padding: 10,
    display: "flex",
    flexDirection: "column",
    gap: 4,
  },
  warning: {
    marginTop: 10,
    color: "#b91c1c",
    fontSize: 13,
    fontWeight: 700,
  },
  chartCard: {
    flex: 1,
    minHeight: 0,
    border: "1px solid #e2e8f0",
    borderRadius: 12,
    background: "#fff",
    padding: 14,
    display: "flex",
    flexDirection: "column",
  },
  chartTitle: {
    fontSize: 15,
    fontWeight: 900,
    color: "#0f172a",
    marginBottom: 10,
  },
  chartWrap: {
    flex: 1,
    minHeight: 230,
  },
  empty: {
    height: "100%",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    color: "#94a3b8",
  },
};
