import { useEffect, useState } from "react";
import api from "../api/client";
import InfoCard from "../components/InfoCard";
import SimpleBarChart from "../components/SimpleBarChart"; // 假设这是封装好的图表组件

export default function SummaryPage() {
  const [data, setData] = useState(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    api.get("/api/tbm/summary")
      .then((res) => setData(res.data))
      .catch(() => setError(true));
  }, []);

  if (error) return <div style={{ padding: 40, color: 'red' }}>❌ 获取数据失败</div>;
  if (!data) return <div style={{ padding: 40 }}>加载中...</div>;

  // 1. 计算核心指标：利用率
  const totalTime = data.work_total_min + data.stop_total_min;
  // 防止除以 0
  const workRate = totalTime > 0 ? ((data.work_total_min / totalTime) * 100).toFixed(1) : 0;
  const stopRate = totalTime > 0 ? ((data.stop_total_min / totalTime) * 100).toFixed(1) : 0;

  // 定义主题色
  const COLOR_WORK = "#3b82f6"; // 蓝色 - 掘进
  const COLOR_STOP = "#f59e0b"; // 橙色 - 停机

  return (
    <div style={{ padding: "30px 40px", backgroundColor: "#f8fafc", minHeight: "100vh" }}>
      <header style={{ marginBottom: 30 }}>
        <h1 style={{ fontSize: "24px", color: "#1e293b", margin: 0 }}>📊 TBM 工况概览</h1>
        <p style={{ color: "#64748b", margin: "5px 0 0 0", fontSize: "14px" }}>
          实时监控掘进效率与设备停机状态
        </p>
      </header>

      {/* 第一行：关键指标卡片 */}
      <div style={{ display: "flex", gap: "20px", marginBottom: "24px", flexWrap: "wrap" }}>
        
        {/* 掘进组 */}
        <InfoCard 
          label="掘进段数" 
          value={data.work_count} 
          iconType="pickaxe" 
          color={COLOR_WORK} 
        />
        <InfoCard 
          label="总掘进时长" 
          value={`${data.work_total_min.toFixed(1)} min`} 
          subValue={`占总时间 ${workRate}%`} // ⭐ 增加百分比
          iconType="clock" 
          color={COLOR_WORK} 
        />

        {/* 停机组 */}
        <InfoCard 
          label="停机段数" 
          value={data.stop_count} 
          iconType="alert" 
          color={COLOR_STOP} 
        />
        <InfoCard 
          label="总停机时长" 
          value={`${data.stop_total_min.toFixed(1)} min`} 
          subValue={`占总时间 ${stopRate}%`} // ⭐ 增加百分比
          iconType="pause" 
          color={COLOR_STOP} 
        />
      </div>

      {/* 第二行：图表区域 */}
      <div
        style={{
          background: "#fff",
          borderRadius: "16px",
          padding: "30px",
          border: "1px solid #e2e8f0",
          boxShadow: "0 1px 3px rgba(0,0,0,0.05)",
          display: "flex",
          flexDirection: "column",
          gap: "20px"
        }}
      >
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <h2 style={{ fontSize: "18px", color: "#334155", margin: 0 }}>⏱️ 掘进/停机时长对比</h2>
          
          {/* 添加一个简单的图例 */}
          <div style={{ display: "flex", gap: "15px", fontSize: "13px", color: "#64748b" }}>
            <span style={{ display: "flex", alignItems: "center", gap: "6px" }}>
              <span style={{ width: 10, height: 10, borderRadius: "50%", background: COLOR_WORK }}></span> 掘进
            </span>
            <span style={{ display: "flex", alignItems: "center", gap: "6px" }}>
              <span style={{ width: 10, height: 10, borderRadius: "50%", background: COLOR_STOP }}></span> 停机
            </span>
          </div>
        </div>

        {/* 这里传入封装好的 Chart 组件。
           注意：将颜色传进去，保证图表和上面的卡片颜色一致 
        */}
        <div style={{ height: "320px", width: "100%" }}>
           <SimpleBarChart 
             data={[
               { name: "掘进", value: data.work_total_min, color: COLOR_WORK },
               { name: "停机", value: data.stop_total_min, color: COLOR_STOP },
             ]} 
           />
        </div>
      </div>
    </div>
  );
}