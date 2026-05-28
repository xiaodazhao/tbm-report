# 数字孪生和大语言模型协同驱动的 TBM 施工报告自动化生成

这是一个面向 TBM 隧道施工场景的研究型全栈系统。项目目标不是让大语言模型直接读取原始 `CSV + PDF`，而是先把 TBM 施工数据、超前地质预报和掌子面素描组织成统一、可解释、可追溯的 `Construction State Twin`，再由大语言模型生成日报、时段报告和问答解释。

## 文档导航

- [项目总说明](docs/research_overview.md)
- [最终版方法框架](docs/final_method_framework.md)
- [实验操作教程](docs/experiment_tutorial.md)
- [论文实验部分草稿](docs/experiment_section_draft.md)
- [论文大纲建议](docs/paper_outline.md)
- [后端清单](docs/backend_inventory.md)
- [Agent 设计说明](docs/agent_v2.md)
- [证据导入说明](docs/evidence_import.md)

如果你想快速了解项目，优先阅读 [项目总说明](docs/research_overview.md)。

## 当前主线

1. 读取 TBM 日运行 `CSV`
2. 解析 `TSP / HSP / 掌子面素描` PDF
3. 按统一里程轴做地质-施工融合
4. 计算区段级 `GRS / RAI / GRCI`
5. 构建 `Construction State Twin`
6. 基于 `CST` 生成 state-aware prompt
7. 生成日报、时段报告和 Agent 问答结果

## 当前版本的核心状态层

项目当前已经实现了正式的 `recursive CST v2`：

- 有统一 `CST schema`
- 主分析链正式产出 `cst_state`
- `CST` 会持久化到 `SQLite`
- 会读取 `t-1` 做递推更新
- 记录 `changed_fields / state_confidence / state_stability / trend_label`
- 维护 `persistent_hazards / persistent_attention_segments`
- API、Agent、实验脚本共用同一状态对象

这意味着项目已经从“分析结果集合”升级成“围绕正式状态对象组织的系统”。

## 当前算法版本

- `GRS`
  - 区段地质关注度表征
  - 基于分量归一化与平权聚合
  - 加入高斯衰减平滑与响应修正
- `RAI`
  - 区段施工响应异常表征
  - 基于 `Isolation Forest`
  - 对常规环级停顿做异常惩罚折减
- `GRCI`
  - 地质关注与施工响应的耦合验证指标
  - 综合同步、滞后、变化和一致性信息

## 项目定位

这个项目更准确的定位不是“TBM 风险识别系统”，而是：

**一个面向 TBM 施工报告自动化生成的 Construction State Twin + LLM 协同框架。**

其中：

- `Construction State Twin` 负责状态组织、时空对齐、证据约束和历史递推
- `LLM` 负责正式工程文本生成

## 技术栈

- 前端：React、Vite、Recharts、Axios
- 后端：FastAPI、Pydantic、Pandas、scikit-learn
- 数据：CSV、PDF、SQLite
- 测试：pytest

## 快速启动

### 1. 配置环境变量

```powershell
copy .env.example backend/.env
```

### 2. 启动后端

```powershell
cd backend
pip install -r requirements.txt
uvicorn app:app --reload --port 8000
```

后端地址：

```text
http://127.0.0.1:8000
http://127.0.0.1:8000/docs
```

### 3. 启动前端

```powershell
cd Frontend
npm install
npm.cmd run dev
```

前端地址：

```text
http://127.0.0.1:5173
```

## 常用接口

- `GET /api/tbm/dates`
- `GET /api/tbm/summary`
- `GET /api/tbm/state`
- `GET /api/tbm/gas`
- `GET /api/tbm/geology`
- `GET /api/tbm/risk_profile`
- `GET /api/tbm/digital_twin_state`
- `GET /api/tbm/history_memory`
- `POST /api/tbm/report`
- `POST /api/tbm/report_by_time`
- `POST /api/tbm/agent_v2`
- `GET /api/tbm/agent_v2/session`
- `POST /api/tbm/evidence/import`

## 论文实验目录

根目录的 [experiments](experiments/README.md) 用于承载论文实验脚本、配置和输出。当前已经覆盖：

- case 冻结
- `CST` 状态导出
- `Template / Direct-LLM / CST-LLM` 报告生成
- 主实验评分与指标汇总
- 追溯实验
- 消融实验
- 多源贡献实验
- 轻量级状态连续性分析

## 验证

后端测试：

```powershell
cd backend
python -m pytest tests
```

前端构建：

```powershell
cd Frontend
npm.cmd run build
```
