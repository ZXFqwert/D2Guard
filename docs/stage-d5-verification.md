# 阶段D5核验摘要

D5 数据准备中止：DeepSeek 连续读取超时；S1关闭，等待评审。

| 项 | 状态 |
|---|---|
| real_negative_4000 | None |
| doc_repositories_60 | None |
| mcp_servers_100 | None |
| host_positive_1500 | None |
| mcp_poisoning_400 | None |
| host_quoted_300 | None |
| real_fraction_35 | None |
| validation_negative_600 | None |
| validation_host_positive_200 | None |
| host_test_300 | None |
| real_benign_none_fpr | None |
| real_benign_request_precision | None |
| host_injection_recall | None |
| semantic_heldout | None |
| gold | None |
| checkpoint_D4 | True |
| pilot_agreement_ge_85 | True |
| isolation | None |
| pretrain_probe | None |
| two_laya_fits | None |
| offline_recall_not_lower | None |
| real_attack_success_zero | None |
| normal_added_ASK_le_2 | None |
| verify_v2_all_passed | None |
| S1_enabled | False |
| stage_E_started | False |

机读结果SHA-256：`61704e5a2efc3d9d251dc6d81dbac9c6b48b10db669648adc28377673ac59798`

报告SHA-256：`dcf1fc78033771d41d5abb0096849657643b1464f2a26219d92246ffd42c81fc`

安全/冻结校验：`{"passed": true, "secret_hits": [], "request_log_fields_valid": true, "snapshot_files_unchanged": true, "D3_training_unchanged": true, "D3_validation_unchanged": true, "heldout_unchanged": true, "gold_unchanged": true, "D4_real_test_unchanged": true, "test_repository_overlap": [], "local_tracked": false, "teacher_env_ignored": true, "production_config_absent": true, "training_clock_absent": true}`

真实运行ID：`[]`；verify_v2：`None`。
