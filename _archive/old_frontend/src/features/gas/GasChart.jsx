import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

const GAS_LABELS = {
  CO2: "CO2",
  H2S: "H2S",
  SO2: "SO2",
  NO2: "NO2",
  NO: "NO",
  CH4: "CH4",
};

export default function GasChart({ gasData }) {
  const data = Object.entries(gasData || {})
    .map(([key, item]) => ({
      gas: gasLabel(key),
      min: clamp(item?.min),
      mean: clamp(item?.mean),
      max: clamp(item?.max),
    }))
    .filter((item) => item.max !== 0 || item.mean !== 0 || item.min !== 0);

  if (!data.length) {
    return (
      <div style={styles.empty}>
        暂无气体统计数据
      </div>
    );
  }

  return (
    <ResponsiveContainer width="100%" height="100%">
      <BarChart data={data} barGap={6} barCategoryGap={22}>
        <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#e2e8f0" />
        <XAxis dataKey="gas" tick={{ fill: "#64748b", fontSize: 12 }} axisLine={false} tickLine={false} />
        <YAxis tick={{ fill: "#64748b", fontSize: 12 }} axisLine={false} tickLine={false} />
        <Tooltip content={<CustomTooltip />} cursor={{ fill: "rgba(15, 118, 110, 0.06)" }} />
        <Legend iconType="circle" wrapperStyle={{ paddingTop: 10 }} />
        <Bar dataKey="min" fill="#14b8a6" name="最小值" radius={[5, 5, 0, 0]} />
        <Bar dataKey="mean" fill="#2563eb" name="平均值" radius={[5, 5, 0, 0]} />
        <Bar dataKey="max" fill="#f97316" name="最大值" radius={[5, 5, 0, 0]} />
      </BarChart>
    </ResponsiveContainer>
  );
}

function CustomTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null;
  return (
    <div style={styles.tooltip}>
      <strong>{label}</strong>
      {payload.map((entry) => (
        <div key={entry.name} style={{ color: entry.color, marginTop: 4 }}>
          {entry.name}：{Number(entry.value).toFixed(3)}
        </div>
      ))}
    </div>
  );
}

function gasLabel(key) {
  const upper = String(key).toUpperCase();
  const match = Object.keys(GAS_LABELS).find((name) => upper.includes(name));
  return match ? GAS_LABELS[match] : key;
}

function clamp(v) {
  const n = Number(v);
  return Number.isFinite(n) ? Math.max(0, n) : 0;
}

const styles = {
  empty: {
    height: "100%",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    color: "#94a3b8",
  },
  tooltip: {
    background: "rgba(255,255,255,0.98)",
    border: "1px solid #e2e8f0",
    borderRadius: 10,
    padding: 12,
    boxShadow: "0 14px 30px rgba(15, 23, 42, 0.12)",
    fontSize: 13,
  },
};
