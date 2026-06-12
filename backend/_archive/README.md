# 后端历史代码归档

`_archive/` 只保存历史版本代码和旧实验脚本，不参与当前后端主流程。

当前主流程仍然是：

```text
routes.report
-> run_daily_report_pipeline
-> ConstructionStateCell
-> Evidence Pack
-> Report
-> Quality / Trace
```

## 目录说明

- `legacy_previous/`：此前瘦身时已经从主目录剥离的旧代码统一归档。

`legacy_previous/` 中包括：

- 旧 Agent 问答模块；
- 旧 `routes/tbm.py`；
- 旧 services 主流程；
- 旧 history memory；
- 旧 digital twin 展示快照；
- 旧 geology 融合链路；
- 旧 segment 级 GRCI；
- 旧 prompt builder；
- 旧测试和调试脚本。

## 使用约束

- 当前主流程不能从 `_archive/` import 任何内容。
- `_archive/` 仅用于历史参考、代码追溯或以后人工迁移参考。
- 如果未来确实需要恢复某段历史能力，应先复制到新的主流程模块，并重新补测试；不要直接从 `_archive/` 接回生产路径。
