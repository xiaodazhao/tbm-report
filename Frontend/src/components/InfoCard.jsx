import React from "react";

// 简单的 SVG 图标组件（如果没有引入图标库）
const Icons = {
  pickaxe: (color) => <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M14.5 2L22 9.5"/><path d="M12 14l-9 9"/><path d="M22 9.5l-5 5"/><path d="M9.5 22l5-5"/></svg>,
  pause: (color) => <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><rect x="6" y="4" width="4" height="16"/><rect x="14" y="4" width="4" height="16"/></svg>,
  clock: (color) => <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>,
  alert: (color) => <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>,
};

export default function InfoCard({ label, value, subValue, iconType, color = "#333" }) {
  return (
    <div
      style={{
        flex: 1,
        padding: "20px 24px",
        background: "#fff",
        borderRadius: "16px",
        border: "1px solid #f1f5f9",
        boxShadow: "0 4px 6px -1px rgba(0, 0, 0, 0.05)",
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        minWidth: "200px" // 防止缩得太小
      }}
    >
      <div>
        <div style={{ color: "#64748b", fontSize: "13px", fontWeight: 500, marginBottom: "4px" }}>
          {label}
        </div>
        <div style={{ color: "#0f172a", fontSize: "28px", fontWeight: "700", letterSpacing: "-0.5px" }}>
          {value}
        </div>
        {subValue && (
          <div style={{ fontSize: "12px", color: color, marginTop: "4px", fontWeight: 600 }}>
            {subValue}
          </div>
        )}
      </div>
      
      {/* 右侧图标装饰 */}
      <div style={{ 
        width: "48px", height: "48px", 
        borderRadius: "12px", 
        background: `${color}15`, // 15 是透明度 hex
        display: "flex", alignItems: "center", justifyContent: "center" 
      }}>
        {Icons[iconType] ? Icons[iconType](color) : null}
      </div>
    </div>
  );
}