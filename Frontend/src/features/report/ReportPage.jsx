import { useEffect, useState } from "react";
import ReactMarkdown from "react-markdown";

import api, { getApiErrorMessage } from "@/api/client";

export default function ReportPage({ date }) {
  const [loading, setLoading] = useState(false);
  const [report, setReport] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    setReport("");
    setError("");
  }, [date]);

  const handleGenerate = async () => {
    if (!date) return;
    setLoading(true);
    setReport("");
    setError("");

    try {
      const res = await api.post("/api/tbm/report", { date });
      setReport(res.data.report || "");
    } catch (err) {
      console.error("日报生成失败", err);
      setError(getApiErrorMessage(err, "日报生成失败，请检查后端服务或 LLM 配置。"));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={styles.wrapper}>
      <div style={styles.toolbar}>
        <div>
          <div style={styles.title}>工程智能日报</div>
          <div style={styles.sub}>日期：{date || "--"}</div>
        </div>
        <button
          type="button"
          onClick={handleGenerate}
          disabled={loading || !date}
          style={{ ...styles.primaryButton, opacity: loading || !date ? 0.6 : 1 }}
        >
          {loading ? "生成中..." : "生成日报"}
        </button>
      </div>

      {error && <div style={styles.error}>{error}</div>}

      <div style={styles.reportBox}>
        {loading ? (
          <Empty title="正在生成日报" text="系统正在汇总工况、地质、气体与风险信息。" />
        ) : report ? (
          <div className="markdown-body" style={styles.markdown}>
            <ReactMarkdown components={markdownComponents}>{report}</ReactMarkdown>
          </div>
        ) : (
          <Empty title="尚未生成日报" text={`点击右上角按钮，生成 ${date || "当前日期"} 的工程日报。`} />
        )}
      </div>
    </div>
  );
}

function Empty({ title, text }) {
  return (
    <div style={styles.empty}>
      <strong>{title}</strong>
      <span>{text}</span>
    </div>
  );
}

const markdownComponents = {
  table: ({ children, ...props }) => (
    <div style={{ width: "100%", overflowX: "auto" }}>
      <table {...props} style={styles.mdTable}>
        {children}
      </table>
    </div>
  ),
  th: ({ children, ...props }) => (
    <th {...props} style={styles.mdTh}>
      {children}
    </th>
  ),
  td: ({ children, ...props }) => (
    <td {...props} style={styles.mdTd}>
      {children}
    </td>
  ),
};

const styles = {
  wrapper: {
    height: "100%",
    display: "flex",
    flexDirection: "column",
    gap: 14,
  },
  toolbar: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    gap: 14,
  },
  title: {
    color: "#0f172a",
    fontSize: 17,
    fontWeight: 900,
  },
  sub: {
    color: "#64748b",
    fontSize: 13,
    marginTop: 4,
  },
  primaryButton: {
    border: "none",
    borderRadius: 10,
    background: "#0f766e",
    color: "#fff",
    padding: "10px 14px",
    fontWeight: 900,
    cursor: "pointer",
    whiteSpace: "nowrap",
  },
  error: {
    border: "1px solid #fecaca",
    background: "#fef2f2",
    color: "#b91c1c",
    borderRadius: 10,
    padding: 10,
    fontSize: 13,
  },
  reportBox: {
    flex: 1,
    minHeight: 0,
    overflow: "auto",
    background: "#fff",
    border: "1px solid #e2e8f0",
    borderRadius: 12,
    padding: 18,
  },
  markdown: {
    color: "#334155",
    lineHeight: 1.75,
    wordBreak: "break-word",
  },
  empty: {
    height: "100%",
    minHeight: 360,
    display: "flex",
    flexDirection: "column",
    alignItems: "center",
    justifyContent: "center",
    gap: 8,
    color: "#94a3b8",
    textAlign: "center",
  },
  mdTable: {
    width: "100%",
    borderCollapse: "collapse",
    margin: "10px 0",
  },
  mdTh: {
    border: "1px solid #e2e8f0",
    background: "#f8fafc",
    padding: "8px 10px",
    textAlign: "left",
    whiteSpace: "nowrap",
  },
  mdTd: {
    border: "1px solid #e2e8f0",
    padding: "8px 10px",
    verticalAlign: "top",
  },
};
