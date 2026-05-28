import { Suspense, lazy, useEffect, useMemo, useState } from "react";

import api, { getApiErrorMessage } from "@/api/client";

const SummaryPage = lazy(() => import("@/features/summary/SummaryPage"));
const GeologyPage = lazy(() => import("@/features/geology/GeologyPage"));
const StatePage = lazy(() => import("@/features/state/StatePage"));
const GasPage = lazy(() => import("@/features/gas/GasPage"));
const ReportPage = lazy(() => import("@/features/report/ReportPage"));
const TimeWindowPage = lazy(() => import("@/features/report/TimeWindowPage"));
const RiskProfilePage = lazy(() => import("@/features/risk/RiskProfilePage"));
const AgentPage = lazy(() => import("@/features/agent/AgentPage"));
const EvidenceImportPage = lazy(() => import("@/features/evidence/EvidenceImportPage"));

export default function Dashboard() {
  const [dates, setDates] = useState([]);
  const [currentDate, setCurrentDate] = useState("");
  const [loading, setLoading] = useState(true);
  const [agentOpen, setAgentOpen] = useState(false);
  const [loadError, setLoadError] = useState("");

  useEffect(() => {
    const fetchDates = async () => {
      try {
        const res = await api.get("/api/tbm/dates");
        const list = res.data.dates || [];
        setDates(list);
        if (list.length > 0) setCurrentDate(list[0]);
        setLoadError("");
      } catch (err) {
        console.error("日期加载失败", err);
        setLoadError(getApiErrorMessage(err, "日期列表加载失败，请检查后端服务或数据目录。"));
      } finally {
        setLoading(false);
      }
    };

    fetchDates();
  }, []);

  useEffect(() => {
    if (!agentOpen) return undefined;

    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";

    const handleKeyDown = (event) => {
      if (event.key === "Escape") {
        setAgentOpen(false);
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => {
      document.body.style.overflow = previousOverflow;
      window.removeEventListener("keydown", handleKeyDown);
    };
  }, [agentOpen]);

  const projectStatus = useMemo(() => {
    if (loadError) return loadError;
    if (!currentDate) return "等待选择数据日期";
    return `正在查看 ${currentDate} 的掘进数据`;
  }, [currentDate, loadError]);

  if (loading) {
    return <div style={styles.loading}>正在初始化 TBM 监测驾驶舱...</div>;
  }

  return (
    <main style={styles.page}>
      <section style={styles.hero}>
        <div style={styles.heroMain}>
          <span style={styles.kicker}>隧道掘进智能分析平台</span>
          <h1 style={styles.title}>TBM 施工态势驾驶舱</h1>
          <p style={styles.subtitle}>{projectStatus}</p>
        </div>

        <div style={styles.heroPanel}>
          <label style={styles.dateLabel}>数据日期</label>
          <select
            value={currentDate}
            onChange={(event) => setCurrentDate(event.target.value)}
            style={styles.select}
          >
            {dates.map((item) => (
              <option key={item} value={item}>
                {item}
              </option>
            ))}
          </select>
          <div style={styles.dateHint}>已接入 {dates.length} 个可分析日期</div>
        </div>
      </section>

      <section style={styles.quickBar}>
        <QuickStat label="当前日期" value={currentDate || "--"} />
        <QuickStat label="核心模块" value="7 个" />
        <QuickStat label="分析模式" value="日报 / 时段 / 问答" />
        <QuickStat label="问答助手" value={agentOpen ? "已打开" : "待唤起"} />
      </section>

      {loadError && <div style={styles.errorBanner}>{loadError}</div>}

      <SectionSuspense text="正在加载证据导入模块...">
        <EvidenceImportPage />
      </SectionSuspense>

      <section style={styles.grid}>
        <Panel title="工况概览" eyebrow="施工节奏">
          <SectionSuspense text="正在加载工况概览...">
            <SummaryPage date={currentDate} />
          </SectionSuspense>
        </Panel>

        <Panel title="地质融合分析" eyebrow="围岩与风险">
          <SectionSuspense text="正在加载地质融合分析...">
            <GeologyPage date={currentDate} />
          </SectionSuspense>
        </Panel>

        <Panel title="施工状态识别" eyebrow="状态片段">
          <SectionSuspense text="正在加载施工状态识别...">
            <StatePage date={currentDate} />
          </SectionSuspense>
        </Panel>

        <Panel title="气体监测" eyebrow="安全监测" span={3} minHeight={420}>
          <SectionSuspense text="正在加载气体监测...">
            <GasPage date={currentDate} />
          </SectionSuspense>
        </Panel>

        <Panel title="空间风险剖面" eyebrow="里程关联" span={3} minHeight={420}>
          <SectionSuspense text="正在加载空间风险剖面...">
            <RiskProfilePage date={currentDate} />
          </SectionSuspense>
        </Panel>

        <Panel title="智能日报" eyebrow="AI 报告" span={3} height={700}>
          <SectionSuspense text="正在加载智能日报...">
            <ReportPage date={currentDate} />
          </SectionSuspense>
        </Panel>

        <Panel title="时间段分析" eyebrow="局部复盘" span={3} height={700}>
          <SectionSuspense text="正在加载时间段分析...">
            <TimeWindowPage date={currentDate} />
          </SectionSuspense>
        </Panel>
      </section>

      <button
        type="button"
        onClick={() => setAgentOpen((open) => !open)}
        style={styles.agentButton}
      >
        {agentOpen ? "收起问答" : "智能问答"}
      </button>

      {agentOpen && <div style={styles.agentBackdrop} onClick={() => setAgentOpen(false)} />}

      <aside
        style={{
          ...styles.agentDrawer,
          transform: agentOpen ? "translateX(0)" : "translateX(calc(100% + 24px))",
          pointerEvents: agentOpen ? "auto" : "none",
        }}
        aria-hidden={!agentOpen}
      >
        <div style={styles.agentWindowHeader}>
          <div>
            <h2 style={styles.agentWindowTitle}>TBM 智能问答</h2>
            <p style={styles.agentWindowSubtitle}>当前日期：{currentDate || "--"}</p>
          </div>
          <button
            type="button"
            onClick={() => setAgentOpen(false)}
            style={styles.closeButton}
            aria-label="关闭问答抽屉"
          >
            关闭
          </button>
        </div>
        <div style={styles.agentDrawerBody}>
          <SectionSuspense text="正在加载智能问答...">
            <AgentPage date={currentDate} compact />
          </SectionSuspense>
        </div>
      </aside>
    </main>
  );
}

function Panel({ title, eyebrow, children, span = 2, minHeight = 520, height }) {
  return (
    <article
      style={{
        ...styles.panel,
        gridColumn: `span ${span}`,
        minHeight,
        ...(height ? { height } : {}),
      }}
    >
      <header style={styles.panelHeader}>
        <div>
          <div style={styles.panelEyebrow}>{eyebrow}</div>
          <h2 style={styles.panelTitle}>{title}</h2>
        </div>
      </header>
      <div style={styles.panelBody}>{children}</div>
    </article>
  );
}

function QuickStat({ label, value }) {
  return (
    <div style={styles.quickItem}>
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function SectionSuspense({ children, text }) {
  return <Suspense fallback={<InlineLoader text={text} />}>{children}</Suspense>;
}

function InlineLoader({ text }) {
  return <div style={styles.inlineLoader}>{text}</div>;
}

const styles = {
  page: {
    minHeight: "100vh",
    padding: "32px",
  },
  hero: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "stretch",
    gap: 24,
    padding: 28,
    borderRadius: 18,
    background: "linear-gradient(135deg, #0f2a4a 0%, #164e63 52%, #116466 100%)",
    color: "#fff",
    boxShadow: "0 24px 60px rgba(15, 42, 74, 0.22)",
  },
  heroMain: {
    display: "flex",
    flexDirection: "column",
    justifyContent: "center",
    minWidth: 0,
  },
  kicker: {
    fontSize: 13,
    color: "#bae6fd",
    fontWeight: 700,
    marginBottom: 10,
  },
  title: {
    margin: 0,
    fontSize: 34,
    lineHeight: 1.15,
    letterSpacing: 0,
  },
  subtitle: {
    margin: "12px 0 0",
    color: "#dbeafe",
    fontSize: 15,
  },
  heroPanel: {
    width: 280,
    borderRadius: 14,
    background: "rgba(255,255,255,0.12)",
    border: "1px solid rgba(255,255,255,0.2)",
    padding: 18,
    display: "flex",
    flexDirection: "column",
    justifyContent: "center",
    gap: 10,
  },
  dateLabel: {
    color: "#dbeafe",
    fontSize: 13,
    fontWeight: 700,
  },
  select: {
    width: "100%",
    padding: "11px 12px",
    borderRadius: 10,
    border: "1px solid rgba(255,255,255,0.3)",
    background: "#fff",
    color: "#0f172a",
    fontWeight: 800,
    outline: "none",
  },
  dateHint: {
    color: "#bfdbfe",
    fontSize: 12,
  },
  quickBar: {
    display: "grid",
    gridTemplateColumns: "repeat(4, minmax(0, 1fr))",
    gap: 16,
    margin: "22px 0",
  },
  quickItem: {
    background: "rgba(255,255,255,0.78)",
    border: "1px solid rgba(203, 213, 225, 0.8)",
    borderRadius: 12,
    padding: "14px 16px",
    boxShadow: "0 10px 30px rgba(15, 23, 42, 0.06)",
    display: "flex",
    justifyContent: "space-between",
    gap: 12,
    alignItems: "center",
  },
  errorBanner: {
    margin: "0 0 18px",
    borderRadius: 12,
    border: "1px solid #fecaca",
    background: "#fef2f2",
    color: "#b91c1c",
    padding: "12px 14px",
    fontSize: 13,
    fontWeight: 700,
  },
  grid: {
    display: "grid",
    gridTemplateColumns: "repeat(6, minmax(0, 1fr))",
    gap: 20,
    alignItems: "stretch",
  },
  panel: {
    background: "rgba(255, 255, 255, 0.92)",
    border: "1px solid rgba(203, 213, 225, 0.85)",
    borderRadius: 14,
    padding: 18,
    display: "flex",
    flexDirection: "column",
    overflow: "hidden",
    boxShadow: "0 14px 40px rgba(15, 23, 42, 0.08)",
  },
  panelHeader: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    paddingBottom: 12,
    marginBottom: 14,
    borderBottom: "1px solid #e2e8f0",
  },
  panelEyebrow: {
    color: "#0f766e",
    fontSize: 12,
    fontWeight: 800,
    marginBottom: 4,
  },
  panelTitle: {
    margin: 0,
    color: "#0f172a",
    fontSize: 18,
    lineHeight: 1.25,
  },
  panelBody: {
    flex: 1,
    minHeight: 0,
    overflow: "auto",
  },
  inlineLoader: {
    minHeight: 180,
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    borderRadius: 12,
    background: "linear-gradient(135deg, rgba(236, 254, 255, 0.95) 0%, rgba(248, 250, 252, 0.96) 100%)",
    color: "#475569",
    fontSize: 14,
    fontWeight: 700,
  },
  agentButton: {
    position: "fixed",
    right: 28,
    bottom: 28,
    zIndex: 30,
    border: "none",
    borderRadius: 999,
    background: "#0f766e",
    color: "#fff",
    boxShadow: "0 16px 34px rgba(15, 118, 110, 0.3)",
    cursor: "pointer",
    fontSize: 15,
    fontWeight: 800,
    padding: "14px 20px",
  },
  agentBackdrop: {
    position: "fixed",
    inset: 0,
    background: "rgba(15, 23, 42, 0.28)",
    backdropFilter: "blur(2px)",
    zIndex: 30,
  },
  agentDrawer: {
    position: "fixed",
    top: 0,
    right: 0,
    zIndex: 31,
    width: "min(720px, 100vw)",
    height: "100vh",
    background: "#ffffff",
    borderLeft: "1px solid #cbd5e1",
    boxShadow: "-24px 0 80px rgba(15, 23, 42, 0.22)",
    padding: "20px 20px 16px",
    display: "flex",
    flexDirection: "column",
    gap: 14,
    transition: "transform 220ms ease",
  },
  agentWindowHeader: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    borderBottom: "1px solid #e2e8f0",
    paddingBottom: 12,
    gap: 12,
  },
  agentWindowTitle: {
    margin: 0,
    color: "#0f172a",
    fontSize: 18,
  },
  agentWindowSubtitle: {
    margin: "4px 0 0",
    color: "#64748b",
    fontSize: 13,
  },
  agentDrawerBody: {
    flex: 1,
    minHeight: 0,
    overflow: "hidden",
  },
  closeButton: {
    borderRadius: 9,
    border: "1px solid #cbd5e1",
    background: "#fff",
    color: "#334155",
    cursor: "pointer",
    fontWeight: 800,
    padding: "8px 12px",
  },
  loading: {
    height: "100vh",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    fontSize: 20,
    color: "#64748b",
  },
};
