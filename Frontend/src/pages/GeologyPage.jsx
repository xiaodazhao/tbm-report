import { useEffect, useState } from "react";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Cell
} from "recharts";
import api from "../api/client";
import RockBand from "../components/RockBand";

// ⭐ 1. 统一定义颜色，确保全页面一致
const ROCK_COLORS = {
  0: "#3b82f6", // 蓝
  1: "#10b981", // 绿
  2: "#f59e0b", // 橙
  3: "#8b5cf6", // 紫
  4: "#ec4899", // 粉
};

export default function GeologyPage() {
  const [data, setData] = useState(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    api.get("/api/tbm/lithology")
      .then((res) => setData(res.data))
      .catch(() => setError(true));
  }, []);

  if (error) return <div style={{ padding: 40, color: 'red' }}>❌ 围岩数据加载失败</div>;
  if (!data) return <div style={{ padding: 40 }}>加载中…</div>;

  // ⭐ 2. 数据转换：为效率数据添加颜色字段，方便图表使用
  const chartData = data.efficiency.map(item => ({
    ...item,
    name: `岩性 ${item["岩性编码"]}`,
    color: ROCK_COLORS[item["岩性编码"]] || "#94a3b8"
  }));

  return (
    <div style={{ padding: "30px 40px", backgroundColor: "#f8fafc", minHeight: "100vh" }}>
      <header style={{ marginBottom: 30, display: "flex", alignItems: "center", gap: 12 }}>
        <div style={{ fontSize: "32px" }}>🪨</div>
        <div>
          <h1 style={{ fontSize: "24px", color: "#1e293b", margin: 0 }}>围岩智能分析</h1>
          <p style={{ margin: "4px 0 0 0", color: "#64748b", fontSize: "14px" }}>
            实时监控岩性分布与掘进效能对比
          </p>
        </div>
      </header>

      {/* 🟢 模块一：时间轴分布 */}
      <div style={{ 
        background: "#fff", 
        padding: "24px", 
        borderRadius: "16px", 
        marginBottom: "24px",
        boxShadow: "0 1px 3px rgba(0,0,0,0.05)"
      }}>
        <h2 style={{ fontSize: "18px", color: "#334155", marginBottom: "20px" }}>⏳ 岩性分段分布</h2>
        {/* 把颜色传进去，保证一致性 */}
        <RockBand segments={data.segments} colorMap={ROCK_COLORS} />
      </div>

      {/* 🟢 模块二：效率对比 (左右布局) */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "24px" }}>
        
        {/* 左侧：详细数据卡片 */}
        <div style={{ display: "flex", flexDirection: "column", gap: "16px" }}>
          <h3 style={{ margin: 0, fontSize: "16px", color: "#64748b" }}>详细指标</h3>
          {chartData.map((row, idx) => (
            <RockStatCard key={idx} data={row} />
          ))}
        </div>

        {/* 右侧：可视化图表 */}
        <div style={{ 
          background: "#fff", 
          padding: "24px", 
          borderRadius: "16px", 
          boxShadow: "0 1px 3px rgba(0,0,0,0.05)"
        }}>
          <h2 style={{ fontSize: "18px", color: "#334155", marginBottom: "20px" }}>📊 掘进速度对比 (mm/min)</h2>
          <div style={{ height: "300px" }}>
             <ResponsiveContainer width="100%" height="100%">
               <BarChart data={chartData} barSize={30}>
                 <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#eee" />
                 <XAxis dataKey="name" tick={{fill: "#64748b", fontSize: 12}} axisLine={false} tickLine={false} />
                 <YAxis axisLine={false} tickLine={false} tick={{fill: "#94a3b8"}} />
                 <Tooltip 
                    cursor={{fill: '#f1f5f9'}}
                    contentStyle={{ borderRadius: 8, border: "none", boxShadow: "0 4px 12px rgba(0,0,0,0.1)" }}
                 />
                 <Bar dataKey="平均推进速度" name="推进速度" radius={[6,6,0,0]} animationDuration={1000}>
                    {chartData.map((entry, index) => (
                        <Cell key={`cell-${index}`} fill={entry.color} />
                    ))}
                 </Bar>
               </BarChart>
             </ResponsiveContainer>
          </div>
        </div>

      </div>
    </div>
  );
}

// ✨ 子组件：美化后的数据卡片
function RockStatCard({ data }) {
  return (
    <div style={{ 
      background: "#fff", 
      padding: "20px", 
      borderRadius: "12px", 
      borderLeft: `6px solid ${data.color}`, 
      boxShadow: "0 1px 2px rgba(0,0,0,0.05)",
      display: "flex",
      justifyContent: "space-between",
      alignItems: "center",
      transition: "transform 0.2s",
    }}>
      <div>
        <h3 style={{ margin: "0 0 10px 0", fontSize: "16px", color: "#334155", display:"flex", alignItems:"center", gap: 8 }}>
          <span style={{width:10, height:10, borderRadius:"50%", background: data.color}}></span>
          {data.name}
        </h3>
        <div style={{ display: "flex", gap: "30px" }}>
           <div>
             <div style={{ fontSize: "12px", color: "#94a3b8" }}>平均速度</div>
             <div style={{ fontSize: "20px", fontWeight: "700", color: "#1e293b" }}>
               {data["平均推进速度"]?.toFixed(2)} <span style={{ fontSize: "12px", fontWeight: "normal", color:"#cbd5e1" }}>mm/min</span>
             </div>
           </div>
           <div>
             <div style={{ fontSize: "12px", color: "#94a3b8" }}>平均贯入度</div>
             <div style={{ fontSize: "20px", fontWeight: "700", color: "#1e293b" }}>
               {data["平均贯入度"]?.toFixed(2)} <span style={{ fontSize: "12px", fontWeight: "normal", color:"#cbd5e1" }}>mm/r</span>
             </div>
           </div>
        </div>
      </div>
    </div>
  );
}