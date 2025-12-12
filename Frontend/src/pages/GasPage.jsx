import { useEffect, useState } from "react";
import api from "../api/client"; // 假设路径没变
import GasChart from "../components/GasChart";

// 辅助组件：单个数据小卡片
const StatCard = ({ label, value, unit = "", color = "#333" }) => (
  <div style={{ 
    background: "#f8fafc", 
    padding: "15px", 
    borderRadius: "12px", 
    flex: 1,
    textAlign: "center",
    border: "1px solid #e2e8f0"
  }}>
    <div style={{ color: "#64748b", fontSize: "14px", marginBottom: "5px" }}>{label}</div>
    <div style={{ color: color, fontSize: "24px", fontWeight: "bold" }}>
      {typeof value === 'number' ? value.toFixed(2) : value}
      <span style={{ fontSize: "14px", marginLeft: "4px", color: "#94a3b8" }}>{unit}</span>
    </div>
  </div>
);

export default function GasPage() {
  const [gas, setGas] = useState(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    // 模拟数据结构，实际使用时请保留你的 api 调用
    api
      .get("/api/tbm/gas")
      .then((res) => setGas(res.data))
      .catch(() => setError(true));
  }, []);

  if (error) return <div style={{ padding: 40, color: 'red' }}>❌ 气体数据获取失败</div>;
  if (!gas) return <div style={{ padding: 40 }}>加载中…</div>;

  const o2 = gas["氧气浓度"] ?? {};

  return (
    <div style={{ padding: "30px 40px", backgroundColor: "#f3f4f6", minHeight: "100vh" }}>
      <h1 style={{ marginBottom: 25, fontSize: "28px", color: "#1e293b" }}>气体监测</h1>

      {/* 模块 1：氧气浓度仪表盘 */}
      <div style={{
        background: "#fff",
        padding: "24px",
        borderRadius: 16,
        marginBottom: 24,
        boxShadow: "0 1px 3px rgba(0,0,0,0.05)"
      }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "20px" }}>
           <h2 style={{ margin: 0, fontSize: "20px", color: "#334155" }}>🔵 氧气浓度 (O₂)</h2>
           {/* 可以放个状态标签，例如 "正常" */}
           <span style={{ 
             background: o2.exceed_count > 0 ? "#fee2e2" : "#dcfce7", 
             color: o2.exceed_count > 0 ? "#ef4444" : "#166534",
             padding: "4px 12px", borderRadius: "20px", fontSize: "13px", fontWeight: "bold" 
           }}>
             {o2.exceed_count > 0 ? "异常" : "正常"}
           </span>
        </div>

        {/* 使用 Flex 布局横向排列数据卡片 */}
        <div style={{ display: "flex", gap: "20px", flexWrap: "wrap" }}>
          <StatCard label="当前平均值" value={o2.mean} unit="%" color="#3b82f6" />
          <StatCard label="监测最大值" value={o2.max} unit="%" />
          <StatCard label="监测最小值" value={o2.min} unit="%" />
          <StatCard label="超标次数" value={o2.exceed_count ?? 0} unit="次" color={o2.exceed_count > 0 ? "#ef4444" : "#333"} />
        </div>
      </div>

      {/* 模块 2：气体统计图表 */}
      <div style={{
        background: "#fff",
        padding: "30px",
        borderRadius: 16,
        boxShadow: "0 1px 3px rgba(0,0,0,0.05)"
      }}>
        <h2 style={{ marginBottom: 25, fontSize: "20px", color: "#334155" }}>📊 全局气体统计</h2>
        <GasChart gasData={gas} />
      </div>
    </div>
  );
}