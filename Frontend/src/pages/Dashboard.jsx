import SummaryPage from "./SummaryPage";

import GeologyPage from "./GeologyPage";

import GasPage from "./GasPage";

import ReportPage from "./ReportPage";



export default function Dashboard() {

  return (

    <div

      style={{

        padding: 50,

        display: "grid",

        gridTemplateColumns: "1fr 1fr", // ⭐ 两列

        gridTemplateRows: "auto auto", // ⭐ 两 行

        gap: 30,                        // ⭐ 模块之间的间距

      }}

    >



      {/* 左上：工况概览 */}

      <div style={blockStyle}>

        <h2>📊 工况概览</h2>

        <SummaryPage compact={true} />

      </div>



      {/* 右上：围岩分析 */}

      <div style={blockStyle}>

        <h2>🪨 围岩分析</h2>

        <GeologyPage compact={true} />

      </div>



      {/* 左下：气体监测 */}

      <div style={blockStyle}>

        <h2>🌫 气体监测</h2>

        <GasPage compact={true} />

      </div>



      {/* 右下：自动报告 */}

      <div style={blockStyle}>

        <h2>📝 自动报告</h2>

        <ReportPage compact={true} />

      </div>



    </div>

  );

}



// ⭐ 通用卡片样式

const blockStyle = {

  background: "var(--card-bg)",

  padding: "20px",

  borderRadius: "12px",

  border: "1px solid var(--border)",

  minHeight: "300px",

  overflow: "hidden",

};