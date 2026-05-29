
    print_geo_state_explanation(
        cell_id="cell_1013220_1013230",
        geo_states_df=geo_states_df,
        cell_evidence_df=cell_evidence_df,
        normalized_df=normalized_df,
        top_n_evidence=12,
    )

    # =========================================================
    # 13. 完成
    # =========================================================
    print_title("测试完成")
    print("输出目录:", out_dir.resolve())

