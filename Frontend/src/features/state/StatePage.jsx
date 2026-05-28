import { useEffect, useState } from "react";

import api, { getApiErrorMessage } from "@/api/client";

export default function StatePage({ date }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!date) return;
    setData(null);
    setError("");
    api
      .get(`/api/tbm/state?date=${date}`)
      .then((res) => setData(res.data || {}))
      .catch((err) => {
        console.error("施工状态数据加载失败", err);
        setError(getApiErrorMessage(err, "施工状态数据加载失败。"));
      });
  }, [date]);

  if (error) return <Empty text={error} />;
  if (!data) return <Empty text="正在加载施工状态数据..." />;

  const segments = Array.isArray(data.segments) ? data.segments : [];
  const efficiency = Array.isArray(data.efficiency) ? data.efficiency : [];

  return (
    <div style={styles.wrapper}>
      <section style={styles.section}>
        <div style={styles.sectionHeader}>
          <div>
            <div style={styles.sectionTitle}>状态时间线</div>
            <div style={styles.sectionSub}>共识别 {segments.length} 个状态片段</div>
          </div>
        </div>

        {segments.length === 0 ? (
          <Empty text="暂无施工状态片段" compact />
        ) : (
          <div style={styles.timeline}>
            {segments.slice(0, 20).map((segment, index) => (
              <div key={`${segment.start}-${index}`} style={styles.timelineItem}>
                <span style={styles.stateDot} />
                <div style={styles.timelineMain}>
                  <strong>{segment.label_text || `施工状态 ${segment.label}`}</strong>
                  <span>
                    {segment.start || "--"} 至 {segment.end || "--"}
                  </span>
                </div>
                <div style={styles.duration}>{duration(segment.duration)}</div>
              </div>
            ))}
          </div>
        )}
      </section>

      <section style={{ ...styles.section, flex: 1, minHeight: 0 }}>
        <div style={styles.sectionHeader}>
          <div>
            <div style={styles.sectionTitle}>状态效率统计</div>
            <div style={styles.sectionSub}>按识别状态汇总关键运行指标</div>
          </div>
        </div>

        {efficiency.length === 0 ? (
          <Empty text="暂无效率统计数据" compact />
        ) : (
          <div style={styles.tableWrap}>
            <table style={styles.table}>
              <thead>
                <tr>
                  <th style={styles.th}>状态</th>
                  <th style={styles.th}>样本数</th>
                  <th style={styles.th}>平均值</th>
                  <th style={styles.th}>最大值</th>
                </tr>
              </thead>
              <tbody>
                {efficiency.slice(0, 12).map((row, index) => {
                  const values = numericValues(row);
                  return (
                    <tr key={`${row.label_text || index}`}>
                      <td style={styles.td}>{row.label_text || row.label || "--"}</td>
                      <td style={styles.td}>{row.count ?? row.samples ?? "--"}</td>
                      <td style={styles.td}>{format(values[0])}</td>
                      <td style={styles.td}>{format(values[1])}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}

function numericValues(row) {
  return Object.entries(row || {})
    .filter(([key, value]) => !["label", "label_text"].includes(key) && Number.isFinite(Number(value)))
    .map(([, value]) => Number(value));
}

function duration(v) {
  const n = Number(v);
  if (!Number.isFinite(n)) return "--";
  return `${(n / 60).toFixed(1)} 分钟`;
}

function format(v) {
  const n = Number(v);
  return Number.isFinite(n) ? n.toFixed(2) : "--";
}

function Empty({ text, compact = false }) {
  return <div style={{ ...styles.empty, minHeight: compact ? 96 : "100%" }}>{text}</div>;
}

const styles = {
  wrapper: {
    height: "100%",
    display: "flex",
    flexDirection: "column",
    gap: 14,
  },
  section: {
    background: "#fff",
    border: "1px solid #e2e8f0",
    borderRadius: 12,
    padding: 14,
  },
  sectionHeader: {
    display: "flex",
    justifyContent: "space-between",
    gap: 12,
    marginBottom: 12,
  },
  sectionTitle: {
    color: "#0f172a",
    fontSize: 15,
    fontWeight: 900,
  },
  sectionSub: {
    color: "#64748b",
    fontSize: 12,
    marginTop: 3,
  },
  timeline: {
    display: "flex",
    flexDirection: "column",
    gap: 8,
    maxHeight: 260,
    overflow: "auto",
    paddingRight: 4,
  },
  timelineItem: {
    display: "grid",
    gridTemplateColumns: "12px 1fr auto",
    gap: 10,
    alignItems: "center",
    border: "1px solid #e2e8f0",
    borderRadius: 10,
    padding: "10px 12px",
    background: "#f8fafc",
  },
  stateDot: {
    width: 10,
    height: 10,
    borderRadius: 999,
    background: "#0f766e",
    boxShadow: "0 0 0 4px #ccfbf1",
  },
  timelineMain: {
    display: "flex",
    flexDirection: "column",
    gap: 2,
    minWidth: 0,
    color: "#334155",
    fontSize: 13,
  },
  duration: {
    color: "#2563eb",
    fontSize: 13,
    fontWeight: 900,
    whiteSpace: "nowrap",
  },
  tableWrap: {
    maxHeight: 220,
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
    background: "#f8fafc",
    color: "#475569",
    textAlign: "left",
    padding: "10px 12px",
    borderBottom: "1px solid #e2e8f0",
  },
  td: {
    color: "#334155",
    padding: "10px 12px",
    borderBottom: "1px solid #f1f5f9",
  },
  empty: {
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    color: "#94a3b8",
    textAlign: "center",
  },
};
