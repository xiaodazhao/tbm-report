# 根目录历史归档

本目录保存当前主线以外的旧版本材料。它们不参与当前后端主流程，也不应被当前后端 import。

更完整的当前项目说明见根目录 [PROJECT_FULL_EXPLANATION.md](../PROJECT_FULL_EXPLANATION.md)。根目录 `_archive/` 主要保存旧前端和本地历史快照；后端旧模块统一保存在 `backend/_archive/`。

当前有效主线在：

```text
backend/
```

当前主流程：

```text
routes.report
-> run_daily_report_pipeline
-> ConstructionStateCell
-> Evidence Pack
-> Report
-> Quality / Trace
```

## 归档目录

- `old_frontend/`：旧前端工程，仍依赖旧接口、Agent、旧报表页面，当前不作为主线维护。
- `root_old_experiments/`：旧实验文档已清空，当前不作为主线实验入口。
- `local_ignored_snapshots/`：本地代码快照或草稿文件，不建议提交到 GitHub。

## 使用约束

- 当前主流程不能从 `_archive/` import 代码。
- `_archive/` 仅用于历史参考。
- 如需恢复某个能力，应重新纳入当前后端结构，并补充测试后再接入。
