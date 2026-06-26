# TBM 实验结果目录

本目录与 `backend/`、`frontend/` 平行，用于保存论文实验阶段的运行结果、统计表和实验报告。

当前后端主流程代码仍保留在 `backend/` 中；本目录只保存实验脚本说明和实验输出，不参与运行时 import。

## 目录规划

- `exp01_twin_full_run/`：第一阶段实验，91 天全量稳定性实验与 DailyConstructionTwin 覆盖率统计。

## 使用约定

- 实验结果优先保存为 CSV、JSON 和 Markdown。
- 大体量的逐日期完整中间结果可保留在本地，不建议直接提交到 Git。
- 本目录不用于存放后端业务代码、前端代码或 legacy 代码。
