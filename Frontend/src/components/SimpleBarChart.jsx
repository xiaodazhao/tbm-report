import React from "react";
import { 
  BarChart, 
  Bar, 
  XAxis, 
  YAxis, 
  Tooltip, 
  ResponsiveContainer, 
  Cell, 
  CartesianGrid 
} from "recharts";

export default function SimpleBarChart({ data }) {
  return (
    <ResponsiveContainer width="100%" height="100%">
      {/* layout="vertical" 让柱状图横过来展示 */}
      <BarChart 
        data={data} 
        layout="vertical" 
        margin={{ top: 5, right: 30, left: 20, bottom: 5 }}
      >
        <CartesianGrid strokeDasharray="3 3" horizontal={false} stroke="#eee" />
        
        {/* X轴隐藏，不需要看具体数值刻度 */}
        <XAxis type="number" hide />
        
        {/* Y轴显示名称 (掘进/停机) */}
        <YAxis 
          dataKey="name" 
          type="category" 
          tick={{ fill: "#64748b", fontSize: 14, fontWeight: 500 }} 
          width={60}
          axisLine={false}
          tickLine={false}
        />
        
        <Tooltip 
          cursor={{ fill: 'transparent' }}
          contentStyle={{ borderRadius: 8, border: "none", boxShadow: "0 4px 12px rgba(0,0,0,0.1)" }}
        />
        
        <Bar dataKey="value" barSize={40} radius={[0, 4, 4, 0]} animationDuration={1000}>
          {data.map((entry, index) => (
            /* 这里的 entry.color 对应 SummaryPage 传进来的掘进蓝/停机橙 */
            <Cell key={`cell-${index}`} fill={entry.color || "#8884d8"} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}