import { useMemo, useState } from "react";

// 接收 colorMap 属性
export default function RockBand({ segments, colorMap }) {
  if (!segments || segments.length === 0) {
    return <div style={{ padding: 20, color: "#999", textAlign: "center" }}>暂无分段数据</div>;
  }

  const [hoverInfo, setHoverInfo] = useState(null);

  // 默认备用颜色
  const defaultColors = {
    0: "#4A90E2", 1: "#50E3C2", 2: "#F5A623", 3: "#BD10E0", 4: "#7ED321",
  };
  const colors = colorMap || defaultColors;

  const toSec = (t) => {
    if (!t) return 0;
    if (typeof t !== "string") t = String(t);
    const timePart = t.includes(" ") ? t.split(" ")[1] : t;
    const parts = timePart.split(":").map(Number);
    if (parts.length < 2 || parts.some((x) => Number.isNaN(x))) return 0;
    const [h, m, s = 0] = parts;
    return h * 3600 + m * 60 + s;
  };

  const sorted = useMemo(
    () => [...segments].sort((a, b) => toSec(a.start) - toSec(b.start)),
    [segments]
  );

  const allStartSecs = sorted.map((s) => toSec(s.start));
  const allEndSecs = sorted.map((s) => toSec(s.end));
  const minSec = Math.min(...allStartSecs);
  const maxSec = Math.max(...allEndSecs);
  const totalSec = maxSec - minSec || 1;

  const ticks = [];
  const startHour = Math.floor(minSec / 3600);
  const endHour = Math.ceil(maxSec / 3600);
  for (let h = startHour; h <= endHour; h++) ticks.push(h);

  return (
    <div style={{ padding: "10px 0", position: "relative", userSelect: "none" }}>
      {/* 刻度尺 */}
      <div style={{ position: "relative", height: 24, marginBottom: 8 }}>
        {ticks.map((h) => {
          const pos = ((h * 3600 - minSec) / totalSec) * 100;
          if (pos < 0 || pos > 100) return null; // 防止超出
          return (
            <div
              key={h}
              style={{
                position: "absolute",
                left: `${pos}%`,
                transform: "translateX(-50%)",
                display: "flex",
                flexDirection: "column",
                alignItems: "center"
              }}
            >
              <div style={{ fontSize: 12, color: "#94a3b8", fontWeight: 500 }}>{h}:00</div>
              {/* 小竖线 */}
              <div style={{ width: 1, height: 4, background: "#cbd5e1", marginTop: 2 }}></div>
            </div>
          );
        })}
      </div>

      {/* 进度条轨道 */}
      <div
        style={{
          position: "relative",
          height: 48, // 加高一点
          borderRadius: 12,
          background: "#f1f5f9",
          overflow: "hidden",
          border: "1px solid #e2e8f0"
        }}
      >
        {sorted.map((s, i) => {
          const segStartSec = toSec(s.start);
          const segEndSec = toSec(s.end);
          const left = ((segStartSec - minSec) / totalSec) * 100;
          let width = ((segEndSec - segStartSec) / totalSec) * 100;
          if (width <= 0) width = 0.5;

          return (
            <div
              key={i}
              style={{
                position: "absolute",
                left: `${left}%`,
                width: `${width}%`,
                top: 0,
                bottom: 0,
                background: colors[s.label] || "#94a3b8",
                borderRight: "2px solid #fff", // 增加间隔感
                cursor: "pointer",
                transition: "opacity 0.2s"
              }}
              onMouseEnter={(e) => {
                e.currentTarget.style.opacity = 0.8; // 悬停变色
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.opacity = 1;
                setHoverInfo(null);
              }}
              onMouseMove={(e) => {
                setHoverInfo({
                  x: e.clientX,
                  y: e.clientY,
                  label: s.label,
                  start: s.start,
                  end: s.end,
                  duration: (s.duration / 60).toFixed(1),
                  color: colors[s.label]
                });
              }}
            />
          );
        })}
      </div>

      {/* 图例 */}
      <div style={{ marginTop: 16, display: "flex", gap: 20, flexWrap: "wrap" }}>
        {[...new Set(sorted.map((s) => s.label))].sort().map((label) => (
          <div key={label} style={{ display: "flex", alignItems: "center", gap: 8, fontSize: "13px", color: "#475569" }}>
            <div
              style={{
                width: 12,
                height: 12,
                borderRadius: "50%",
                background: colors[label] || "#999",
              }}
            />
            岩性 {label}
          </div>
        ))}
      </div>

      {/* 悬浮 Tooltip */}
      {hoverInfo && (
        <div
          style={{
            position: "fixed",
            left: hoverInfo.x + 16,
            top: hoverInfo.y + 16,
            padding: "12px 16px",
            background: "rgba(255, 255, 255, 0.95)", // 亮色背景更现代
            color: "#1e293b",
            borderRadius: 8,
            boxShadow: "0 10px 15px -3px rgba(0, 0, 0, 0.1), 0 4px 6px -2px rgba(0, 0, 0, 0.05)",
            fontSize: 13,
            pointerEvents: "none",
            zIndex: 9999,
            border: "1px solid #f1f5f9",
            minWidth: 150
          }}
        >
          <div style={{ fontWeight: "bold", marginBottom: 6, display: "flex", alignItems: "center", gap: 6 }}>
             <span style={{ width: 8, height: 8, borderRadius: "50%", background: hoverInfo.color }}></span>
             岩性 {hoverInfo.label}
          </div>
          <div style={{ color: "#64748b", marginBottom: 2 }}>⏱ {hoverInfo.start} - {hoverInfo.end}</div>
          <div style={{ color: "#334155", fontWeight: 500 }}>⌛ 持续 {hoverInfo.duration} 分钟</div>
        </div>
      )}
    </div>
  );
}