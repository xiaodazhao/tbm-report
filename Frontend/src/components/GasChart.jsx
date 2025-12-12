import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  Legend,
  ResponsiveContainer,
  CartesianGrid, // 新增：辅助网格
} from "recharts";

const SHORT_NAMES = {
  "氧气浓度": "O₂",
  "一氧化碳浓度": "CO",
  "硫化氢浓度": "H₂S",
  "粉尘含量": "Dust",
  "主驱动甲烷含量": "CH₄-M1",
  "连接桥甲烷含量": "CH₄-M2",
  "除尘风机出口甲烷含量": "CH₄-Fan",
  "二氧化碳含量": "CO₂",
  "一氧化氮含量": "NO",
  "二氧化硫含量": "SO₂",
};

// 自定义悬浮提示（Tooltip）
const CustomTooltip = ({ active, payload, label }) => {
  if (active && payload && payload.length) {
    return (
      <div style={{
        backgroundColor: "rgba(255, 255, 255, 0.95)",
        border: "1px solid #ddd",
        padding: "10px",
        borderRadius: "4px",
        boxShadow: "0 2px 5px rgba(0,0,0,0.1)",
        fontSize: "13px"
      }}>
        <p style={{ fontWeight: "bold", marginBottom: 5 }}>{label}</p>
        {payload.map((entry, index) => (
          <p key={index} style={{ color: entry.color, margin: 0 }}>
            {entry.name}: {Number(entry.value).toFixed(2)}
            {/* 这里可以根据气体类型判断单位，目前假设通用 */}
          </p>
        ))}
      </div>
    );
  }
  return null;
};

export default function GasChart({ gasData }) {
  // 整理数据 + 数据清洗（去除负数）
  const data = Object.keys(gasData)
    .filter((k) => gasData[k].max !== 0 || gasData[k].min !== 0)
    .map((k) => ({
      gas: SHORT_NAMES[k] ?? k,
      // Math.max(0, ...) 防止传感器漂移导致的负数出现在图表上
      min: Math.max(0, gasData[k].min),
      mean: Math.max(0, gasData[k].mean),
      max: Math.max(0, gasData[k].max),
    }));

  return (
    <div style={{ height: 350 }}>
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} barGap={6} barCategoryGap={30}>
          {/* 增加虚线网格，提升可读性 */}
          <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#eee" />
          
          <XAxis 
            dataKey="gas" 
            tick={{ fill: "#666", fontSize: 12 }} 
            axisLine={{ stroke: "#e0e0e0" }}
          />
          <YAxis 
            tick={{ fill: "#999", fontSize: 12 }} 
            axisLine={false} 
            tickLine={false}
          />
          
          <Tooltip content={<CustomTooltip />} cursor={{ fill: 'transparent' }} />
          <Legend iconType="circle" wrapperStyle={{ paddingTop: "10px" }}/>

          {/* 稍微调亮一点颜色，看起来更现代 */}
          <Bar dataKey="min" fill="#34d399" name="最小值" radius={[4, 4, 0, 0]} animationDuration={1000} />
          <Bar dataKey="mean" fill="#60a5fa" name="平均值" radius={[4, 4, 0, 0]} animationDuration={1000} />
          <Bar dataKey="max" fill="#f87171" name="最大值" radius={[4, 4, 0, 0]} animationDuration={1000} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}