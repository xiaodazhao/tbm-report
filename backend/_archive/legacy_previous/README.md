# Legacy Modules

这些文件已经从日报主流程中断开，只作为历史参考保留。

当前唯一主入口是：

```text
pipeline.daily_report_pipeline.run_daily_report_pipeline
```

当前唯一 API 注册文件是：

```text
routes.report
```

legacy 下的旧 Agent、旧 `routes.tbm`、旧 `services.tbm_analysis_service`、
旧 `geology/` 链路和旧 segment 级 GRCI 不再参与主报告生成。

