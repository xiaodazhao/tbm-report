# 完整实验教程（换电脑从零开始）

## 1. 这份教程是给谁用的

这份教程是给“在另一台电脑上把当前实验从零重新跑起来的人”准备的。它回答的是：

1. 代码拉下来以后先做什么
2. 环境怎么配
3. 数据路径怎么接
4. 每个实验脚本怎么跑
5. 每一步会生成什么文件
6. 结果怎么看

## 2. 先理解一件事：实验输出默认不跟着 Git 走

仓库中保留了实验脚本和实验配置，但 `experiments/outputs/` 下的大多数运行产物默认被 `.gitignore` 忽略。

这意味着在新电脑上：

- 你会拿到实验脚本
- 你不会自动拿到旧电脑生成的实验结果
- 你需要重新运行实验，重新生成 case、state、report 和 metrics

## 3. 新电脑需要准备什么

### 3.1 基础软件

- `Git`
- `Python 3.10+`
- `Node.js + npm`  
  只有需要启动前端时才需要

### 3.2 代码仓库

```powershell
git clone https://github.com/xiaodazhao/llmagent.git
cd llmagent
git pull
```

### 3.3 真实数据目录

你当前使用的真实数据根目录是：

```text
G:\我的云端硬盘\TBM9
```

至少要能访问这些目录：

- `TBM9_2023`
- `DB`
- `TSP`
- `HSP`
- `SKETCH`

### 3.4 LLM API Key

如果要正式生成报告，需要可用的：

- `DeepSeek` key
- 或 `Gemini` key

如果只是先跑 `prompt_only`，可以先不配置。

## 4. 环境搭建

### 4.1 Python 环境

```powershell
conda create -n tbmexp python=3.11 -y
conda activate tbmexp
```

### 4.2 安装后端依赖

```powershell
pip install -r backend/requirements.txt
```

### 4.3 前端依赖（可选）

```powershell
cd Frontend
npm install
cd ..
```

## 5. 配置 `.env`

```powershell
copy .env.example backend/.env
```

编辑 `backend/.env`。

### 5.1 模型配置

如果用 DeepSeek：

```text
LLM_PROVIDER=deepseek
DEEPSEEK_API_KEY=你的key
DEEPSEEK_MODEL=deepseek-chat
DEEPSEEK_BASE_URL=https://api.deepseek.com
```

如果用 Gemini：

```text
LLM_PROVIDER=google
GOOGLE_API_KEY=你的key
GOOGLE_MODEL=gemini-2.5-flash-lite
```

### 5.2 数据路径配置

最简单方式是只配置：

```text
DATA_ROOT=G:\我的云端硬盘\TBM9
```

如果目录结构不同，也可以显式配置：

```text
DATA_DIR=G:\我的云端硬盘\TBM9\TBM9_2023
TSP_DIR=G:\我的云端硬盘\TBM9\TSP
HSP_DIR=G:\我的云端硬盘\TBM9\HSP
SKETCH_DIR=G:\我的云端硬盘\TBM9\SKETCH
DB_DIR=G:\我的云端硬盘\TBM9\DB
APP_DB_PATH=G:\我的云端硬盘\TBM9\DB\tbm_app.sqlite3
EVIDENCE_DB_PATH=G:\我的云端硬盘\TBM9\DB\evidence_db.csv
```

## 6. 先做两个基础连通性检查

### 6.1 脚本可执行性

```powershell
python experiments/00_prepare_cases.py --help
python experiments/03_evaluate_reports.py --help
```

### 6.2 编译检查

```powershell
python -m compileall backend
python -m compileall experiments
```

## 7. 推荐实验顺序

推荐顺序如下：

1. `00_prepare_cases.py`
2. `01_export_cst_states.py`
3. `02_generate_reports.py`
4. `03_evaluate_reports.py`
5. `05_traceability_check.py`
6. `08_summarize_traceability.py`
7. `06_generate_ablation_reports.py`
8. `07_prepare_ablation_evaluation.py`
9. `09_generate_multisource_reports.py`
10. `10_prepare_multisource_evaluation.py`
11. `11_state_continuity_analysis.py`

## 8. Step 1：准备 case

### 命令

```powershell
python experiments/00_prepare_cases.py --limit 12
```

### 输出

目录：

```text
experiments/outputs/cases/
```

文件：

- `case_candidates.csv`
- `case_list.csv`

### 你怎么用

`case_candidates.csv` 是候选池。  
`case_list.csv` 是后续所有实验的正式输入。

当前已经使用过的一套样本是：

- `C01` 2023-09-24：`gas_attention`
- `C02` 2023-10-21：`geology_attention`
- `C03` 2023-10-24：`geology_attention`
- `C04` 2023-10-26：高强度 `geology_attention`
- `C05` 2023-11-01：`coupled_attention`
- `C06` 2023-11-18：`response_anomaly`

如果你不重新筛，就直接沿用这 6 个。

## 9. Step 2：导出 CST

### 命令

```powershell
python experiments/01_export_cst_states.py
```

### 输出

目录：

```text
experiments/outputs/states/
```

文件：

- `C01_state.json`
- `...`
- `C06_state.json`
- `state_summary.csv`

### 你怎么看

重点检查：

- `main_state`
- `GRS`
- `RAI`
- `GRCI`
- `forward_window`
- `persistent_hazards`
- `persistent_attention_segments`

说明：当前 `CST` 已经是正式的 `recursive CST v2`，不只是快照。

## 10. Step 3：生成三类报告

### 10.1 先生成 prompt

```powershell
python experiments/02_generate_reports.py --mode prompt_only
```

输出目录：

```text
experiments/outputs/reports/
```

典型文件：

- `C01_template.txt`
- `C01_direct_llm.prompt.txt`
- `C01_cst_llm.prompt.txt`

### 10.2 再正式调模型

```powershell
python experiments/02_generate_reports.py --mode call_llm --provider deepseek
```

或：

```powershell
python experiments/02_generate_reports.py --mode call_llm --provider gemini
```

输出：

- `C01_direct_llm.txt`
- `C01_cst_llm.txt`
- `...`

### 你怎么看

三类方法的角色是：

- `Template`：最稳定，但最简化
- `Direct-LLM`：覆盖高，但更依赖模型自行整合
- `CST-LLM`：基于正式 `CST` 状态层和受控约束

## 11. Step 4：主实验评分

### 初始化评分表

```powershell
python experiments/03_evaluate_reports.py --init-only
```

输出：

- `experiments/outputs/metrics/evaluation_sheet.csv`

### 评分字段

第一轮重点填：

- `ICS_operation`
- `ICS_geology`
- `ICS_gas`
- `ICS_forward`
- `factual_errors_count`
- `key_facts_count`
- `unsupported_claims_count`
- `key_claims_count`
- `RDR_score`
- `EOR_score`

### 汇总

```powershell
python experiments/03_evaluate_reports.py
```

输出：

- `report_metrics.csv`

## 12. Step 5：追溯实验

### 生成追溯表

```powershell
python experiments/05_traceability_check.py
```

输出：

- `traceability_C01.csv`
- `...`
- `traceability_C06.csv`

### 汇总追溯

```powershell
python experiments/08_summarize_traceability.py
```

输出：

- `traceability_summary.csv`

## 13. Step 6：消融实验

### 生成核心消融报告

```powershell
python experiments/06_generate_ablation_reports.py
```

当前核心变体：

- `full`
- `wo_geo`
- `wo_alignment`
- `wo_constraints`

### 准备评分表

```powershell
python experiments/07_prepare_ablation_evaluation.py
```

输出：

- `ablation_evaluation_sheet.csv`
- `ablation_metrics.csv`

## 14. Step 7：多源贡献实验

### 生成多源报告

```powershell
python experiments/09_generate_multisource_reports.py
```

当前变体：

- `plc_only`
- `plc_geo`
- `full`

### 准备评分表

```powershell
python experiments/10_prepare_multisource_evaluation.py
```

输出：

- `multisource_evaluation_sheet.csv`
- `multisource_metrics.csv`

## 15. Step 8：状态连续性分析

### 命令

```powershell
python experiments/11_state_continuity_analysis.py
```

输出：

- `state_continuity_summary.csv`
- `state_continuity_overview.md`

当前这一步是轻量级 continuity analysis，不是完整动力学实验。

## 16. 当前已经完成了什么

当前项目已经做过：

- 主实验
- 追溯实验
- 消融实验
- 多源贡献实验
- 轻量级状态连续性分析

所以你在新电脑上主要是复现，而不是从零设计实验。

## 17. 目前还缺什么

如果继续往前做，当前主要缺：

- 更好的 `normal case`
- `w/o indicators`
- 更强的人工复核
- 更重的动态更新实验

## 18. 一句话总结

换电脑后，你真正要做的事情只有一句话：

**重新接上真实数据路径，按 `case -> CST -> reports -> metrics -> traceability -> ablation -> multisource -> continuity` 这条链把实验重新跑出来。**
