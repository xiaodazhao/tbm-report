# 地质超报增量导入说明

本文档说明项目当前如何处理新的 TSP/HSP/洞身素描 PDF 超前地质预报，以及如何把新报告增量写入 `evidence_db.csv`。

## 1. 设计目标

原来的全量流程是：

```text
扫描全部 TSP/HSP/SKETCH PDF
    -> 全部重新解析
    -> 重新生成 evidence_db.csv
```

这个方式适合首次建库，但不适合日常施工。实际施工中，超前地质预报通常会先于开挖发布，后续会不断新增。如果每来一份新超报都全量重建：

- 耗时更长；
- 旧记录难以追踪；
- parser 调整后容易让旧数据发生整体漂移；
- 不利于前端或接口做“只导入这份新报告”的操作。

所以项目新增了增量导入：

```text
新增 PDF
    -> 自动选择 parser
    -> 解析 EvidenceRecord
    -> 清洗和去重
    -> 与已有 evidence_db.csv 合并
    -> 写入前自动备份
```

## 2. 支持的报告类型

| 输入 `source_type` | 内部类型 | Parser |
| --- | --- | --- |
| `tsp` | `tsp` | `parse_tsp_pdf` |
| `hsp` | `sonic` | `parse_hsp_pdf` |
| `sonic` | `sonic` | `parse_hsp_pdf` |
| `sketch` | `sketch` | `parse_sketch_pdf` |

如果 `source_type` 留空，系统会尝试根据路径判断：

1. 是否位于配置的 `TSP_DIR`、`HSP_DIR`、`SKETCH_DIR` 下；
2. 文件夹名或文件名是否包含 `tsp`、`hsp`、`sonic`、`sketch` 等关键词。

无法推断时会报错，并提示显式传入 `source_type`。

## 3. 后端代码位置

核心服务：

```text
backend/services/evidence_import_service.py
```

命令行入口：

```text
backend/scripts/import_evidence_reports.py
```

API 入口：

```text
backend/routes/tbm.py
POST /api/tbm/evidence/import
```

前端入口：

```text
Frontend/src/features/evidence/EvidenceImportPage.jsx
```

请求 schema：

```text
backend/schemas/api.py
EvidenceImportRequest
```

## 4. API 用法

```http
POST /api/tbm/evidence/import
Content-Type: application/json
```

请求体：

```json
{
  "paths": [
    "G:/我的云端硬盘/TBM9/SKETCH/new_report.pdf"
  ],
  "source_type": "sketch",
  "dry_run": true,
  "replace_existing": false,
  "recursive": false
}
```

字段说明：

| 字段 | 类型 | 默认值 | 含义 |
| --- | --- | --- | --- |
| `paths` | `list[str]` | 必填 | PDF 文件或目录路径 |
| `source_type` | `str/null` | `null` | `tsp` / `hsp` / `sonic` / `sketch` |
| `dry_run` | `bool` | `false` | 只解析检查，不写入 CSV |
| `replace_existing` | `bool` | `false` | 已有同 `evidence_id` 时是否替换 |
| `recursive` | `bool` | `false` | 输入目录时是否递归扫描 PDF |

返回字段：

| 字段 | 含义 |
| --- | --- |
| `ok` | 是否全部文件解析成功 |
| `dry_run` | 是否为预检查 |
| `written` | 是否实际写入 |
| `evidence_db_path` | 目标证据库路径 |
| `backup_path` | 写入前生成的备份路径 |
| `pdf_count` | 扫描到的 PDF 数量 |
| `parsed_record_count` | parser 原始解析记录数 |
| `clean_record_count` | 清洗后新记录数 |
| `inserted_count` | 新插入记录数 |
| `replaced_count` | 替换旧记录数 |
| `skipped_existing_count` | 跳过重复记录数 |
| `skipped_existing_ids` | 被跳过的重复 ID |
| `total_before` | 导入前证据库记录数 |
| `total_after` | 导入后证据库记录数 |
| `file_results` | 每个 PDF 的解析结果 |
| `errors` | 解析失败列表 |

## 5. 命令行用法

进入后端目录：

```powershell
cd backend
```

先 dry-run：

```powershell
python scripts/import_evidence_reports.py "G:/我的云端硬盘/TBM9/SKETCH/new_report.pdf" --source-type sketch --dry-run
```

确认无误后正式导入：

```powershell
python scripts/import_evidence_reports.py "G:/我的云端硬盘/TBM9/SKETCH/new_report.pdf" --source-type sketch
```

导入一个目录：

```powershell
python scripts/import_evidence_reports.py "G:/我的云端硬盘/TBM9/SKETCH/new_folder" --source-type sketch
```

递归导入目录：

```powershell
python scripts/import_evidence_reports.py "G:/我的云端硬盘/TBM9/SKETCH/new_folder" --source-type sketch --recursive
```

替换已有同 ID 记录：

```powershell
python scripts/import_evidence_reports.py "G:/我的云端硬盘/TBM9/SKETCH/new_report.pdf" --source-type sketch --replace-existing
```

## 6. 清洗与去重规则

增量导入和全量建库共用同一类安全检查思想。

当前增量导入会：

1. 要求存在 `evidence_id`、`start_num`、`end_num`。
2. 把 `start_num`、`end_num` 转成数值。
3. 删除缺少有效里程的记录。
4. 删除 `start_num > end_num` 的记录。
5. 按 `evidence_id` 去重，保留最后一条。
6. 对 `source_level == segment` 的记录，过滤长度大于 300m 的异常区段。
7. 保留 `point` 级证据，不因区段长度规则误删。
8. 按 `source_type`、`report_id`、`start_num`、`end_num` 排序。

默认行为：

- 已存在同 `evidence_id` 时跳过新记录。
- 使用 `replace_existing=true` 时删除旧 ID 后写入新解析结果。
- 只在有插入或替换时写入 CSV。
- 写入前复制一份 `.bak_YYYYMMDD_HHMMSS.csv` 备份。

## 7. 推荐使用流程

```text
1. 收到新的超前地质预报 PDF
2. 放入对应 TSP/HSP/SKETCH 目录
3. 前端证据库控制台选择 source_type 并 dry_run
4. 检查解析记录数、重复记录数和 errors
5. 无误后正式导入
6. 打开地质融合页或运行 inspect_coupling_analysis.py 检查影响
```

示例检查命令：

```powershell
cd backend
python scripts/inspect_coupling_analysis.py --date 2023-12-30 --limit 5 --json
```

## 8. 什么时候仍然需要全量重建

以下情况建议全量重建 `evidence_db.csv`：

- parser 模板逻辑发生系统性变化；
- 需要重新清洗所有旧记录；
- 旧证据库字段结构发生变化；
- 发现某类报告过去整体解析错误；
- 需要做一次可复现实验，要求所有 PDF 在同一版 parser 下生成。

全量重建命令：

```powershell
cd backend
python scripts/build_evidence_db.py
```

## 9. 当前边界

1. 该功能默认 PDF 模板是固定的；模板变更仍需要改 parser。
2. 增量导入只能处理本机路径，前端目前不是浏览器文件上传。
3. `dry_run` 不会写入，也不会生成备份。
4. 旧记录不会因为 parser 更新自动变化。
5. 如果想刷新某份旧报告，需要使用 `replace_existing=true`。
