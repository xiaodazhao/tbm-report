import { useState } from "react";
import ReactMarkdown from "react-markdown";
import api from "../api/client";

// 图标组件
const Icons = {
  sparkles: <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01L12 2z"/></svg>,
  copy: <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>,
  download: <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>,
};

export default function ReportPage() {
  const [loading, setLoading] = useState(false);
  const [report, setReport] = useState("");
  const [error, setError] = useState("");
  const [copyStatus, setCopyStatus] = useState("复制");

  const handleGenerate = async () => {
    setLoading(true);
    setReport("");
    setError("");

    try {
      const res = await api.post("/api/tbm/report", {}, { timeout: 120000 });
      setReport(res.data.report);
    } catch (err) {
      console.error(err);
      setError("❌ 报告生成失败，请检查网络或后端服务。");
    } finally {
      setLoading(false);
    }
  };

  const handleCopy = () => {
    if (!report) return;
    navigator.clipboard.writeText(report);
    setCopyStatus("已复制!");
    setTimeout(() => setCopyStatus("复制"), 2000);
  };

  const handleDownload = () => {
    if (!report) return;
    const blob = new Blob([report], { type: "text/markdown" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `TBM_智能报告_${new Date().toISOString().slice(0, 10)}.md`;
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div style={{ padding: "30px 40px", backgroundColor: "#f8fafc", minHeight: "100vh" }}>
      
      {/* 🟢 全局样式：美化滚动条 */}
      <style>{`
        /* 让滚动条变细、变好看 */
        .custom-scroll::-webkit-scrollbar {
          width: 8px;
        }
        .custom-scroll::-webkit-scrollbar-track {
          background: #f1f5f9; 
          border-radius: 4px;
        }
        .custom-scroll::-webkit-scrollbar-thumb {
          background: #cbd5e1; 
          border-radius: 4px;
        }
        .custom-scroll::-webkit-scrollbar-thumb:hover {
          background: #94a3b8; 
        }
      `}</style>

      <header style={{ marginBottom: 30, textAlign: "center" }}>
        <h1 style={{ fontSize: "28px", color: "#1e293b", marginBottom: "10px" }}>📄 TBM 智能工况报告</h1>
        <p style={{ color: "#64748b" }}>基于实时监测数据与掘进历史，自动生成施工建议。</p>
      </header>

      <div style={{ display: "flex", justifyContent: "center", marginBottom: "30px" }}>
        <button
          onClick={handleGenerate}
          disabled={loading}
          style={{
            display: "flex", alignItems: "center", gap: "10px",
            padding: "14px 32px",
            background: loading ? "#94a3b8" : "linear-gradient(135deg, #3b82f6 0%, #2563eb 100%)",
            color: "white", border: "none", borderRadius: "50px",
            cursor: loading ? "not-allowed" : "pointer",
            fontSize: "16px", fontWeight: "600",
            boxShadow: "0 4px 12px rgba(59, 130, 246, 0.3)",
            transition: "all 0.2s"
          }}
        >
          {loading ? <>⏳ 正在深度分析数据...</> : <>{Icons.sparkles} 生成/刷新报告</>}
        </button>
      </div>

      {error && (
        <div style={{ maxWidth: "800px", margin: "0 auto 20px", padding: 16, background: "#fee2e2", color: "#991b1b", borderRadius: 12, textAlign: "center" }}>
          {error}
        </div>
      )}

      {/* 📄 报告卡片区域 */}
      {(report || loading) && (
        <div style={{
          maxWidth: "800px",
          margin: "0 auto",
          background: "#fff",
          borderRadius: "12px", // 圆角稍微大一点
          boxShadow: "0 4px 20px rgba(0,0,0,0.08)",
          border: "1px solid #e2e8f0",
          overflow: "hidden", // 防止子元素溢出圆角
          position: "relative"
        }}>
          
          {/* A. 顶部固定工具栏 (这样滚动时按钮一直都在！) */}
          {!loading && report && (
            <div style={{ 
              padding: "15px 25px", 
              borderBottom: "1px solid #f1f5f9", 
              display: "flex", 
              justifyContent: "flex-end",
              gap: 10,
              background: "#fafafa" // 稍微有点灰的背景，区分内容区
            }}>
              <button onClick={handleCopy} style={toolBtnStyle} title="复制内容">
                {Icons.copy} {copyStatus}
              </button>
              <button onClick={handleDownload} style={toolBtnStyle} title="下载 Markdown">
                {Icons.download} 下载
              </button>
            </div>
          )}

          {/* B. 滚动内容区域 */}
          <div 
            className="custom-scroll" // 应用上面定义的 CSS 类
            style={{
              padding: "40px",
              // ⭐⭐ 核心修改在这里 ⭐⭐
              height: "600px",       // 设定固定高度 (或者用 '65vh' 适应屏幕)
              overflowY: "auto",     // 超出高度时出现滚动条
              // ⭐⭐ 结束修改 ⭐⭐
            }}
          >
            {loading && <LoadingSkeleton />}

            {!loading && report && (
              <div className="markdown-body" style={{ lineHeight: 1.8, color: "#334155" }}>
                <ReactMarkdown
                   components={{
                     h1: ({node, ...props}) => <h1 style={{borderBottom: "1px solid #eee", paddingBottom: 10, color: "#1e293b", marginTop: 0}} {...props} />,
                     h2: ({node, ...props}) => <h2 style={{color: "#334155", marginTop: 30}} {...props} />,
                     h3: ({node, ...props}) => <h3 style={{color: "#475569", marginTop: 20}} {...props} />,
                     strong: ({node, ...props}) => <strong style={{color: "#0f172a", fontWeight: 700}} {...props} />,
                     li: ({node, ...props}) => <li style={{marginBottom: 8}} {...props} />,
                     // 处理代码块溢出
                     pre: ({node, ...props}) => <pre style={{background: "#f1f5f9", padding: 10, borderRadius: 6, overflowX: "auto"}} {...props} />
                   }}
                >
                  {report}
                </ReactMarkdown>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

// 样式组件保持不变
const toolBtnStyle = {
  background: "#fff",
  border: "1px solid #e2e8f0",
  borderRadius: "6px",
  padding: "6px 12px",
  cursor: "pointer",
  color: "#64748b",
  fontSize: "13px",
  display: "flex",
  alignItems: "center",
  gap: 6,
  transition: "all 0.2s"
};

function LoadingSkeleton() {
  return (
    <div style={{ marginTop: 10 }}>
      {[80, 90, 60, 95, 40].map((width, i) => (
        <div key={i} style={{
          height: 16,
          background: "#f1f5f9",
          marginBottom: 16,
          borderRadius: 4,
          width: `${width}%`,
          animation: "pulse 1.5s infinite ease-in-out"
        }}></div>
      ))}
      <div style={{ height: 200, background: "#f8fafc", borderRadius: 8, marginTop: 30, animation: "pulse 1.5s infinite ease-in-out" }}></div>
      <style>{`@keyframes pulse { 0% { opacity: 0.6; } 50% { opacity: 1; } 100% { opacity: 0.6; } }`}</style>
    </div>
  );
}