# 项目瘦身归档记录（2026-07-06）

本次整理目标是让当前 TBM 施工日报项目目录更清晰，同时不删除历史结果、不改变后端主流程、不影响当前论文实验材料。

## 1. 未改动的当前主线

以下目录和链路保持不变：

- `backend/`：当前后端主流程、PLC preprocessing、Evidence Pack、Quality / Trace / Boundary、DailyConstructionTwin。
- `frontend/`：当前前端工作台。
- `experiments/exp02_llm_generation_modes/outputs_real_91dates_structured_trace_v1_merged/`：当前 91 天 structured_trace_v1 最终合并结果。
- `experiments/exp02_llm_generation_modes/outputs_real_15dates_structured_trace_v1_merged/`：当前 15 天 structured_trace_v1 合并结果。
- `experiments/exp02_llm_generation_modes/outputs_real_3dates_structured_trace_v1/`：当前 3 天 structured_trace_v1 检查结果。
- `experiments/exp03_indicator_robustness/outputs/`：指标稳健性实验结果。
- `experiments/exp_plc_preprocessing_validation/outputs_91days/`：PLC preprocessing 91 天冻结验证结果。
- `paper_materials/`：论文写作材料主目录。

## 2. 归档位置

旧输出、过程目录和临时运行结果统一移动到：

```text
_archive/local_ignored_snapshots/2026-07-06_project_slimming/
```

该目录在 `.gitignore` 中，作为本地历史快照保存，不进入 Git 提交。

## 3. 本次归档内容

### 根目录与后端临时输出

- `outputs/` 旧内容 → `_archive/local_ignored_snapshots/2026-07-06_project_slimming/root_outputs/`
- `backend/outputs/` → `_archive/local_ignored_snapshots/2026-07-06_project_slimming/backend_outputs/`

说明：根目录 `outputs/` 是若干测试和脚本默认使用的本地临时输出父目录。本次已归档其中旧内容，但保留/重建空 `outputs/` 目录供测试运行时写入临时文件。

### Exp01 旧输出

- `experiments/exp01_twin_full_run/outputs/`
- `experiments/exp01_twin_full_run/outputs_test/`
- `experiments/exp01_twin_full_run/outputs_fix01/` 中未跟踪的旧输出文件

说明：`outputs_fix01` 中已被 Git 跟踪的两个汇总文件已保留在原位置，避免产生误删。

### Exp02 旧版和过程输出

已归档旧版 v3.1、win fixed、单日修复、dry-run、test、retry 等输出目录，包括但不限于：

- `outputs_real_win_15dates_fixed*`
- `outputs_real_win_30dates_fixed_v31`
- `outputs_real_win_91dates_fixed_v31`
- `outputs_real_15dates_v3_1`
- `outputs_real_91dates_v3_1*`
- `outputs_real_3dates_after_plc_template`
- `outputs_real_15dates_structured_trace_v1` 过程目录
- `outputs_real_15dates_structured_trace_v1_retry*` 过程目录
- `outputs_real_91dates_structured_trace_v1` 过程目录

保留在原位的当前结果：

- `outputs_real_3dates_structured_trace_v1/`
- `outputs_real_15dates_structured_trace_v1_merged/`
- `outputs_real_91dates_structured_trace_v1_merged/`

### PLC preprocessing 临时输出

- `experiments/exp_plc_preprocessing_validation/outputs_check/`
- `experiments/exp_plc_preprocessing_validation/outputs_smoke_one/`

保留：

- `experiments/exp_plc_preprocessing_validation/outputs_91days/`

## 4. 论文材料整理

根目录下两个未跟踪说明文档已移动到论文材料目录：

```text
paper_materials/00_project_overview/PROJECT_METHOD_EXPLANATION_FOR_REVIEWER.md
paper_materials/00_project_overview/PROJECT_METHOD_STRUCTURE_DIAGRAMS.md
```

这样根目录只保留项目入口级文件，项目说明与论文材料统一进入 `paper_materials/`。

## 5. 本次没有归档的源码目录

以下目录虽然看起来像辅助模块，但仍被当前代码、脚本或测试使用，不应归档：

- `backend/services/`：证据库导入、SQLite 同步和相关测试仍使用。
- `backend/contracts/`：Quality / Grounding checker 的术语和字段契约仍使用。
- `backend/analysis/`：PLC response 相关基础分析仍依赖。
- `backend/evidence_governance/`、`backend/parsers/`：正式证据库构建与解析链路仍使用。

## 6. 后续建议

1. 暂时不要再清理 `backend/` 源码，除非先做完整 import 与测试审计。
2. 当前论文实验应默认使用 structured_trace_v1 的 merged 结果。
3. 若后续需要进一步瘦身，可优先处理本地缓存：
   - `.pytest_cache/`
   - `__pycache__/`
   - `frontend/node_modules/`
   - `frontend/dist/`
4. 这些缓存可以重新生成，不建议进入归档，也不建议提交。
