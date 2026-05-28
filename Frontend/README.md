# Frontend

前端基于 `React + Vite`，负责把后端分析结果组织成一个可交互的 TBM 施工分析看板。

## 功能模块

- 日期选择与总览驾驶舱
- 工况概览
- 施工状态识别
- 地质融合与耦合分析
- 气体监测
- 风险 / 速度剖面
- 智能日报与时间窗分析
- 抽屉式 Agent 问答
- 证据 PDF 导入

## 启动

```powershell
npm install
npm.cmd run dev
```

默认地址：

```text
http://127.0.0.1:5173
```

## 构建

```powershell
npm.cmd run build
```

## 环境变量

在 `Frontend/.env` 中配置后端地址：

```env
VITE_API_BASE_URL=http://127.0.0.1:8000
```

## 目录结构

```text
src/api/                  接口封装
src/features/dashboard/   仪表盘外壳
src/features/summary/     工况概览
src/features/state/       施工状态识别
src/features/geology/     地质融合分析
src/features/gas/         气体监测
src/features/risk/        风险剖面
src/features/report/      报告生成
src/features/agent/       智能问答
src/features/evidence/    证据导入
```

## 说明

- 当前已经做了懒加载与基础拆包，首页加载比早期版本更轻。
- 智能问答已升级为右侧抽屉式交互，并支持会话恢复、上下文追问和调度轨迹展开。
- 构建通过后，产物会生成在 `Frontend/dist/`。
