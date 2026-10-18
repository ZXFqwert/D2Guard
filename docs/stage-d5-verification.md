# 阶段D5核验摘要

D5 已停止：GLM batch and two minimal probes returned HTTP 403; response contains quota/balance error marker. Preserve all valid rows and votes; legacy synthetic early gate incomplete. No training or test evaluation started.；S1关闭。

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
| checkpoint_GLM | True |
| GLM_three_class_72_passed | True |
| GLM_early_per_class_70 | None |
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

机读结果SHA-256：`46c6ca56dd1cd2384f3c172c4bf1be2d1014ae8ec81d9d7d9e549e6a03f6c018`

报告SHA-256：`9b408e9888e56f06aa6ecbf811fce24cf72f62ed572a596d2d57ca33ac092555`

安全/冻结校验：`{"passed": true, "secret_hits": [], "request_log_fields_valid": true, "snapshot_files_unchanged": true, "D3_training_unchanged": true, "D3_validation_unchanged": true, "heldout_unchanged": true, "gold_unchanged": true, "D4_real_test_unchanged": true, "test_repository_overlap": [], "local_tracked": false, "teacher_env_ignored": true, "production_config_absent": true, "training_clock_absent": true}`

真实运行ID：`[]`；verify_v2：`None`。
