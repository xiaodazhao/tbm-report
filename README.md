# TBM 施工日报可信生成研究原型

本项目是一个面向 TBM 施工日报自动生成的研究原型。当前主线不是“直接让大语言模型自由写日报”，而是：

```text
多源工程数据
-> 工程证据治理
-> 10 m 施工状态单元
-> 日施工状态孪生
-> Evidence Pack
-> 模板或 LLM 受控生成
-> Quality / Grounding / Boundary / Structured Trace
-> Reviser
-> 可追溯施工日报与审计结果
```

日报是最终输出之一。项目真正研究的是：如何把 PLC、地质预报、掌子面素描和气体监测等多源资料组织成可追溯、可约束、可审计的工程证据，并在此基础上约束大语言模型生成施工日报。

## 当前核心入口

| 内容 | 路径 |
|---|---|
| 项目全貌说明书 | [`PROJECT_FULL_EXPLANATION.md`](PROJECT_FULL_EXPLANATION.md) |
| 后端主工程 | [`backend/`](backend/) |
| 后端说明 | [`backend/README.md`](backend/README.md) |
| 后端字段契约 | [`backend/docs/backend_field_contract.md`](backend/docs/backend_field_contract.md) |
| PLC 预处理方法 | [`backend/docs/plc_preprocessing_method.md`](backend/docs/plc_preprocessing_method.md) |
| 前端工作台 | [`frontend/`](frontend/) |
| 实验目录 | [`experiments/`](experiments/) |
| 论文材料 | [`paper_materials/`](paper_materials/) |

## 后端主流程

主入口：

```text
backend/routes/report.py
-> backend/pipeline/daily_report_pipeline.py::run_daily_report_pipeline
```

核心链路：

```text
load_daily_inputs(date)
-> PLC preprocessing / cell response
-> geology evidence scope
-> ConstructionStateCell
-> RAI / GRS / GRCI
-> DailyConstructionTwin
-> Evidence Pack
-> template or LLM generation
-> Quality / Grounding / Boundary / Structured Trace
-> report + debug + export
```

不要从 `_archive/` 或 `backend/_archive/` import 当前主流程代码。

## 关键方法边界

- `daily_plc_range` / `daily_advance_m` 是 PLC 实测推进范围和推进量。
- `daily_excavated_scope` 是 10 m cell 对齐后的已掘复核范围，不是实际推进范围。
- `forward_attention` 只能表示当前掌子面前方关注提示，不能写成已发生事实。
- `RAI` 是施工响应关注指标，不是设备故障概率。
- `GRS` 是地质证据关注指标，不是灾害概率。
- `GRCI` 是已掘区段地质-施工响应耦合关注指标，只用于 `daily_review`，不用于 `forward_attention`。
- PLC proxy 指标只用于已掘区段施工响应解释，不能写成严格物理功率、严格比能或地质风险证明。
- LLM 不直接读取原始 PLC CSV 或完整 evidence_db，只消费 Evidence Pack、生成约束和必要摘要。

## 当前最终实验结果

### Exp01：后端主流程稳定性

Exp01 用于验证 no-LLM 主流程、DailyConstructionTwin、Evidence Pack、Quality、Trace、Boundary 和导出链路。

| 内容 | 路径 |
|---|---|
| Exp01 结果目录 | [`experiments/exp01_twin_full_run/outputs_fix02/`](experiments/exp01_twin_full_run/outputs_fix02/) |
| Exp01 说明 | [`experiments/exp01_twin_full_run/README.md`](experiments/exp01_twin_full_run/README.md) |

### Exp02：真实 LLM 生成模式对比

当前最终结果为 `structured_trace_v1` 的 91 天全量真实 LLM 回归：

```text
91 dates x 5 modes = 455 runs
failed_count = 0
```

| 内容 | 路径 |
|---|---|
| Exp02 最终结果目录 | `experiments/exp02_llm_generation_modes/outputs_real_91dates_structured_trace_v1_merged/` |
| Exp02 说明 | [`experiments/exp02_llm_generation_modes/README.md`](experiments/exp02_llm_generation_modes/README.md) |

五种模式：

| 模式 | 含义 |
|---|---|
| M0 | 确定性模板基线 |
| M1 | 基础统计直接 LLM |
| M2 | 原始证据输入 LLM |
| M3 | ConstructionStateCell + Evidence Pack LLM |
| M4 | Twin + Evidence Pack + Planning + Boundary + Structured Trace + Reviser |

91 天最终核心结果：

| 模式 | 平均质量分 | 证据支撑率 | unsupported | numeric | boundary | 缺章 |
|---|---:|---:|---:|---:|---:|---:|
| M0 | 100.00 | 1.0000 | 0 | 0 | 0 | 0 |
| M1 | 70.76 | 0.7295 | 1143 | 445 | 10 | 182 |
| M2 | 72.96 | 0.7253 | 1221 | 334 | 23 | 182 |
| M3 | 68.93 | 0.7592 | 1256 | 226 | 2 | 184 |
| M4 | 94.18 | 0.9153 | 376 | 78 | 0 | 0 |

M4 修订效果：

```text
pre_revision_unsupported_total = 637
post_revision_unsupported_total = 376
reduction_rate = 40.97%
```

### Exp03：RAI / GRS / GRCI 指标稳健性

Exp03 只做旁路复算和排序稳健性分析，不改变主流程、不改变 Exp02 结果。

| 内容 | 路径 |
|---|---|
| Exp03 目录 | [`experiments/exp03_indicator_robustness/`](experiments/exp03_indicator_robustness/) |
| 论文材料 | [`paper_materials/04_indicator_robustness/`](paper_materials/04_indicator_robustness/) |

## 论文材料

论文写作材料集中在：

```text
paper_materials/
```

推荐阅读顺序：

1. [`paper_materials/01_exp02_results/analysis/exp02_results_section_draft.md`](paper_materials/01_exp02_results/analysis/exp02_results_section_draft.md)
2. [`paper_materials/02_statistics/exp02_statistical_significance_analysis.md`](paper_materials/02_statistics/exp02_statistical_significance_analysis.md)
3. [`paper_materials/03_case_studies/exp02_case_study_draft.md`](paper_materials/03_case_studies/exp02_case_study_draft.md)
4. [`paper_materials/04_indicator_robustness/paper_exp03_indicator_robustness_analysis.md`](paper_materials/04_indicator_robustness/paper_exp03_indicator_robustness_analysis.md)
5. [`paper_materials/06_full_paper_draft/full_paper_draft_v2_autcon_style.md`](paper_materials/06_full_paper_draft/full_paper_draft_v2_autcon_style.md)

## 后端常用命令

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

当前 API：

```text
GET  /api/tbm/health
GET  /api/tbm/dates
POST /api/tbm/report
POST /api/tbm/report/debug
```

## 前端

前端是轻量 TBM 施工日报生成工作台，只消费后端 API，不在前端计算 GRCI、不处理原始 PLC、不拼 Evidence Pack。

```powershell
cd frontend
npm install
npm run dev
npm run build
```

## 配置

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

真实 DeepSeek / OpenAI-compatible 调用必须显式允许外发。不要在未确认数据脱敏和外发许可前，把 Evidence Pack、prompt 或施工数据发送给外部模型。不要提交 API key。

## 归档说明

历史前端、旧接口、旧 Agent、旧服务和旧代码保留在：

```text
_archive/
backend/_archive/
```

归档内容只作历史参考，不参与当前主流程。

## 当前建议

当前不建议继续大改主代码。后续工作重点应转向：

1. 论文方法章节打磨；
2. 自动评价体系公式化；
3. 统计检验与效应量整理；
4. 典型案例分析；
5. 人工复核材料准备；
6. 参考文献补齐。
