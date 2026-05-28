import { useEffect, useState } from "react";
import ReactMarkdown from "react-markdown";

import api, { getApiErrorMessage } from "@/api/client";

export default function TimeWindowPage({ date }) {
  const [startTime, setStartTime] = useState("");
  const [endTime, setEndTime] = useState("");
  const [report, setReport] = useState("");
  const [loading, setLoading] = useState(false);
  const [errorMsg, setErrorMsg] = useState("");

  useEffect(() => {
    if (!date) return;
    setStartTime(`${date}T08:00`);
    setEndTime(`${date}T12:00`);
    setReport("");
    setErrorMsg("");
  }, [date]);

  const handleGenerate = async () => {
    if (!startTime || !endTime) {
      setErrorMsg("请选择开始时间和结束时间。");
      return;
    }
    if (startTime >= endTime) {
      setErrorMsg("结束时间必须晚于开始时间。");
      return;
    }

    setLoading(true);
    setReport("");
    setErrorMsg("");

    try {
      const res = await api.post("/api/tbm/report_by_time", {
        start_time: startTime,
        end_time: endTime,
      });
      setReport(res.data.report || "");
    } catch (err) {
      console.error("时间段报告生成失败", err);
      setErrorMsg(getApiErrorMessage(err, "时间段报告生成失败，请检查后端服务。"));
    } finally {
      setLoading(false);
    }
  };

  if (!date) {
    return <div style={styles.empty}>请先选择数据日期。</div>;
  }

  return (
    <div style={styles.wrapper}>
      <div style={styles.toolbar}>
        <div>
          <div style={styles.title}>时间段智能分析</div>
          <div style={styles.sub}>日期：{date}</div>
        </div>
      </div>

      <div style={styles.form}>
        <Field label="开始时间" value={startTime} onChange={setStartTime} date={date} />
        <Field label="结束时间" value={endTime} onChange={setEndTime} date={date} />
        <button
          type="button"
          onClick={handleGenerate}
          disabled={loading}
          style={{ ...styles.primaryButton, opacity: loading ? 0.65 : 1 }}
        >
          {loading ? "分析中..." : "生成报告"}
        </button>
      </div>

      {errorMsg && <div style={styles.error}>{errorMsg}</div>}

      <div style={styles.reportBox}>
        {loading ? (
          <Empty title="正在分析时间段" text="系统正在截取所选时间窗并生成分析报告。" />
        ) : report ? (
          <div className="markdown-body" style={styles.markdown}>
            <ReactMarkdown>{report}</ReactMarkdown>
          </div>
        ) : (
          <Empty title="尚未生成时间段报告" text="选择起止时间后，点击生成报告。" />
        )}
      </div>
    </div>
  );
}

function Field({ label, value, onChange, date }) {
  return (
    <label style={styles.field}>
      <span>{label}</span>
      <input
        type="datetime-local"
        value={value}
        min={`${date}T00:00`}
        max={`${date}T23:59`}
        onChange={(event) => onChange(event.target.value)}
        style={styles.input}
      />
    </label>
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
  form: {
    display: "grid",
    gridTemplateColumns: "1fr 1fr auto",
    gap: 10,
    alignItems: "end",
    background: "#f8fafc",
    border: "1px solid #e2e8f0",
    borderRadius: 12,
    padding: 14,
  },
  field: {
    display: "flex",
    flexDirection: "column",
    gap: 6,
    color: "#64748b",
    fontSize: 12,
    fontWeight: 800,
  },
  input: {
    width: "100%",
    border: "1px solid #cbd5e1",
    borderRadius: 9,
    padding: "9px 10px",
    color: "#334155",
    background: "#fff",
    outline: "none",
  },
  primaryButton: {
    border: "none",
    borderRadius: 9,
    background: "#2563eb",
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
  },
  empty: {
    height: "100%",
    minHeight: 320,
    display: "flex",
    flexDirection: "column",
    alignItems: "center",
    justifyContent: "center",
    gap: 8,
    color: "#94a3b8",
    textAlign: "center",
  },
};
