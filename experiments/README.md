# Experiments

This directory contains the paper experiment workflow built on top of the production CST-enabled backend. It is intentionally separated from the online API path.

## Read These First

- [Full Experiment Tutorial](../docs/experiment_tutorial.md)
- [Experiment Section Draft](../docs/experiment_section_draft.md)
- [Final Method Framework](../docs/final_method_framework.md)
- [Paper Outline](../docs/paper_outline.md)

## Directory Purpose

The `experiments/` folder is used to:

- freeze experiment cases
- export formal `cst_state` assets
- generate baseline and CST-driven reports
- prepare evaluation sheets
- summarize traceability
- run ablation and multi-source comparison workflows
- run lightweight CST continuity analysis

It should not be treated as part of the production API service.

## Recommended Execution Order

1. `00_prepare_cases.py`
   - Generate or refine `case_list.csv`.
2. `01_export_cst_states.py`
   - Export formal `cst_state` JSON files for each case.
3. `02_generate_reports.py`
   - Generate `Template / Direct-LLM / CST-LLM` report prompts or reports.
4. `03_evaluate_reports.py`
   - Initialize and aggregate main experiment scoring sheets.
5. `04_ablation_study.py`
   - Build the ablation plan.
6. `05_traceability_check.py`
   - Generate traceability tables.
7. `06_generate_ablation_reports.py`
   - Generate ablation reports.
8. `07_prepare_ablation_evaluation.py`
   - Prepare ablation scoring sheets and metric summaries.
9. `08_summarize_traceability.py`
   - Summarize traceability statistics.
10. `09_generate_multisource_reports.py`
    - Generate multi-source comparison reports.
11. `10_prepare_multisource_evaluation.py`
    - Prepare multi-source scoring sheets and summaries.
12. `11_state_continuity_analysis.py`
    - Generate lightweight CST continuity results.

## Key Outputs

Typical outputs are written under `experiments/outputs/`:

- `cases/`
  - case candidates and frozen case list
- `states/`
  - exported `cst_state` JSON files and summary CSVs
- `reports/`
  - main experiment outputs
- `reports_ablation/`
  - ablation report outputs
- `reports_multisource/`
  - multi-source comparison outputs
- `metrics/`
  - evaluation sheets and aggregated metrics
- `tables/`
  - traceability tables, case-study notes, continuity summaries

## Current Experiment Scope

The current experiment workflow already supports:

- main comparison:
  - `Template`
  - `Direct-LLM`
  - `CST-LLM`
- traceability analysis
- ablation analysis
- multi-source contribution analysis
- lightweight CST continuity analysis

The remaining higher-end work is mostly:

- a stronger `normal` case
- `w/o indicators`
- heavier recursive-CST evaluation
- stronger human review loops

## Notes

- Experiment scripts now reuse the formal backend `cst_state` instead of building a separate parallel twin object.
- Generated outputs are intentionally ignored by Git except for retained directory skeletons and hand-selected reference materials.
