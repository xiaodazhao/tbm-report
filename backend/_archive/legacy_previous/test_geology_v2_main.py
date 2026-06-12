from utils.io_utils import load_csv_by_date
from services.tbm_analysis_service import analyze_tbm_data

date = "2023-12-30"

path, df = load_csv_by_date(date)

result = analyze_tbm_data(
    df,
    context={
        "date": date,
        "analysis_mode": "daily",
        "source_path": str(path),
        "source_name": path.name,
        "persist_cst": False,
    },
)

print("has geology_v2_context:", "geology_v2_context" in result)
print("has geology_v2_prompt_block:", "geology_v2_prompt_block" in result)
print("has geology_v2_rendered_text:", "geology_v2_rendered_text" in result)
print("has geology_v2_data_summary:", "geology_v2_data_summary" in result)
print("has geology_v2_forward_profile:", "geology_v2_forward_profile" in result)
print("geology_v2_warnings:", result.get("geology_v2_warnings"))

print("\n=== geology_v2_data_summary ===")
print(result.get("geology_v2_data_summary"))

print("\n=== geology_v2_prompt_block preview ===")
print(str(result.get("geology_v2_prompt_block", ""))[:2000])

llm_summary = result.get("llm_summary", {})
prompt_inputs = llm_summary.get("prompt_text_inputs", {}) if isinstance(llm_summary, dict) else {}

print("\n=== prompt_text_inputs keys ===")
print(list(prompt_inputs.keys()))

print("\n=== excavated_segment_text preview ===")
print(str(prompt_inputs.get("excavated_segment_text", ""))[:1200])

print("\n=== forward_risk_text preview ===")
print(str(prompt_inputs.get("forward_risk_text", ""))[:1200])