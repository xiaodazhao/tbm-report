# TBM 施工可信知识生成与日报自动生成研究原型

本项目是一个面向 TBM 连续掘进过程的研究型系统。当前主线不再是“直接让大语言模型自由写日报”，而是：

```text
PLC 施工响应证据治理
+ 多源地质证据治理
-> ConstructionStateCell
-> DailyConstructionTwin
-> Evidence Pack
-> template / LLM 受控生成
-> Quality / Grounding / Boundary / Structured Trace
-> Reviser
-> 可追溯施工日报与审计结果
```

换句话说，日报只是系统的一个输出形式；项目真正研究的是 **多源工程证据约束下的 TBM 施工可信知识生成**。

## 1. 当前最重要的入口

| 内容 | 路径 |
|---|---|
| 后端主工程 | [`backend/`](backend/) |
| 前端工作台 | [`frontend/`](frontend/) |
| 实验目录 | [`experiments/`](experiments/) |
| 论文材料 | [`paper_materials/`](paper_materials/) |
| 项目结构说明 | [`PROJECT_STRUCTURE.md`](PROJECT_STRUCTURE.md) |
| 后端文档入口 | [`backend/docs/README.md`](backend/docs/README.md) |
| 本轮瘦身归档记录 | [`docs/project_slimming_archive_2026-07-06.md`](docs/project_slimming_archive_2026-07-06.md) |

## 2. 当前后端主流程

后端主入口仍然是：

```text
backend/routes/report.py
-> backend/pipeline/daily_report_pipeline.py::run_daily_report_pipeline
```

核心数据对象和逻辑顺序为：

```text
load_daily_inputs(date)
-> PLC preprocessing / cell response
-> geology evidence scope
-> ConstructionStateCell
-> RAI / GRS / GRCI
-> DailyConstructionTwin
-> Evidence Pack
-> template or LLM generation
-> Quality / Trace / Boundary
-> report + debug + export
```

当前不应从 `_archive/` 或 `backend/_archive/` 引入任何主流程代码。

## 3. 关键方法边界

- `daily_plc_range` 是 PLC 实测当日推进范围和日推进量。
- `daily_excavated_scope` 是按 10 m cell 对齐后的已掘复核范围，不是实际推进范围。
- `forward_attention` 只表示当前掌子面前方关注提示，不能写成已发生事实。
- `RAI` 是施工响应关注度，不是设备故障概率。
- `GRS` 是地质证据关注度，不是灾害概率。
- `GRCI` 是已掘区段地质-施工响应耦合关注度，只用于 `daily_review`，不用于 `forward_attention`。
- PLC proxy 指标只用于已掘区段施工响应解释，不能写成严格物理功率、严格比能或地质风险证明。
- LLM 不直接读取原始 PLC CSV 或完整正式 evidence_db，只消费 Evidence Pack 和生成约束。

## 4. 当前主要实验结果入口

### Exp01：后端主流程与 Twin 全链路

| 内容 | 路径 |
|---|---|
| 当前保留结果 | [`experiments/exp01_twin_full_run/outputs_fix02/`](experiments/exp01_twin_full_run/outputs_fix02/) |
| PLC preprocessing 检查 | [`experiments/exp01_twin_full_run/outputs_plc_preprocessing_check/`](experiments/exp01_twin_full_run/outputs_plc_preprocessing_check/) |
| template 章节对齐检查 | [`experiments/exp01_twin_full_run/outputs_template_section_alignment/`](experiments/exp01_twin_full_run/outputs_template_section_alignment/) |

### Exp02：真实 LLM 生成模式对比

当前最重要结果是 structured trace v1：

| 内容 | 路径 |
|---|---|
| 3 天检查结果 | [`experiments/exp02_llm_generation_modes/outputs_real_3dates_structured_trace_v1/`](experiments/exp02_llm_generation_modes/outputs_real_3dates_structured_trace_v1/) |
| 15 天 merged 结果 | [`experiments/exp02_llm_generation_modes/outputs_real_15dates_structured_trace_v1_merged/`](experiments/exp02_llm_generation_modes/outputs_real_15dates_structured_trace_v1_merged/) |
| 91 天 merged 结果 | [`experiments/exp02_llm_generation_modes/outputs_real_91dates_structured_trace_v1_merged/`](experiments/exp02_llm_generation_modes/outputs_real_91dates_structured_trace_v1_merged/) |

91 天真实 LLM 回归规模：

```text
91 dates × 5 modes = 455 runs
failed_count = 0
```

五种模式：

| 模式 | 含义 |
|---|---|
| M0 | 确定性模板基线 |
| M1 | 直接 LLM 生成 |
| M2 | 原始证据输入 LLM |
| M3 | ConstructionStateCell + Evidence Pack |
| M4 | Twin + Evidence Pack + 规划约束 + Boundary + Structured Trace + Reviser |

### Exp03：RAI / GRS / GRCI 指标稳健性

| 内容 | 路径 |
|---|---|
| 指标稳健性实验 | [`experiments/exp03_indicator_robustness/`](experiments/exp03_indicator_robustness/) |
| 输出结果 | [`experiments/exp03_indicator_robustness/outputs/`](experiments/exp03_indicator_robustness/outputs/) |

Exp03 只做旁路复算和排序稳健性比较，不改变 Exp02，不改变主流程公式。

## 5. 论文材料

论文写作材料集中在：

```text
paper_materials/
```

当前建议阅读顺序：

1. [`paper_materials/00_project_overview/`](paper_materials/00_project_overview/)：项目全貌与结构图。
2. [`paper_materials/01_exp02_results/`](paper_materials/01_exp02_results/)：91 天主实验表格、图和分析。
3. [`paper_materials/02_statistics/`](paper_materials/02_statistics/)：统计检验与效应量材料。
4. [`paper_materials/03_case_studies/`](paper_materials/03_case_studies/)：典型案例材料。
5. [`paper_materials/04_indicator_robustness/`](paper_materials/04_indicator_robustness/)：指标稳健性材料。
6. [`paper_materials/06_full_paper_draft/`](paper_materials/06_full_paper_draft/)：完整论文草稿。

## 6. 后端常用命令

进入后端：

```powershell
cd backend
```

运行测试：

```powershell
python -m pytest tests -q
```

三日期 no-LLM smoke：

```powershell
python scripts/smoke_test_daily_pipeline.py --dates 2023-12-30,2023-12-28,2023-09-15 --no-llm --out outputs/smoke_summary.json
```

导出单日完整中间结果：

```powershell
python scripts/export_daily_pipeline_outputs.py --dates 2023-12-30,2023-12-28 --no-llm --out-dir outputs/pipeline_exports
```

启动 FastAPI：

```powershell
uvicorn app:app --reload --port 8000
```

当前对外 API：

```text
GET  /api/tbm/health
GET  /api/tbm/dates
POST /api/tbm/report
POST /api/tbm/report/debug
```

## 7. 前端

前端是一个轻量 TBM 施工日报生成工作台，只消费后端 API，不在前端计算 GRCI、不处理原始 PLC、不拼 Evidence Pack。

```powershell
cd frontend
npm install
npm run dev
npm run build
```

## 8. 配置

复制模板：

```powershell
copy backend\.env.example backend\.env
```

至少配置：

```env
DATA_ROOT=G:/我的云端硬盘/TBM9
DATA_DIR=G:/我的云端硬盘/TBM9/TBM9_2023
EVIDENCE_DB_PATH=G:/我的云端硬盘/TBM9/DB/evidence_db.csv
USE_LLM=false
```

真实 DeepSeek / OpenAI-compatible 调用必须显式允许外发。不要在未确认数据脱敏和外发许可前，把 Evidence Pack、prompt 或施工数据发送给外部模型。

## 9. 归档与瘦身说明

历史前端、旧接口、旧 Agent、旧服务、旧实验和旧输出已归档到：

```text
_archive/
backend/_archive/
_archive/local_ignored_snapshots/
```

本轮项目瘦身记录：

```text
docs/project_slimming_archive_2026-07-06.md
```

归档内容只作历史参考，不参与当前主流程。

## 10. 当前建议

当前不建议继续大改主代码。后续工作重点应转向：

1. 论文方法章节打磨；
2. 自动评价体系公式化；
3. 统计检验与效应量整理；
4. 典型案例分析；
5. 人工复核材料准备；
6. 参考文献补齐。

