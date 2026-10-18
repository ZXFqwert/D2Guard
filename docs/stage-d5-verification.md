# 阶段D5核验摘要

D5 模型验收未通过，S1关闭，等待评审。

| 项 | 状态 |
|---|---|
| real_negative_4000 | True |
| doc_repositories_60 | True |
| mcp_servers_100 | True |
| host_positive_1500 | True |
| mcp_poisoning_400 | True |
| host_quoted_300 | True |
| real_fraction_35 | True |
| validation_negative_600 | True |
| validation_host_positive_200 | True |
| host_test_300 | True |
| real_benign_none_fpr | True |
| real_benign_request_precision | True |
| host_injection_recall | True |
| semantic_heldout | False |
| gold | False |
| checkpoint_D4 | True |
| checkpoint_GLM | True |
| GLM_three_class_72_passed | True |
| GLM_early_per_class_70 | None |
| dean_finalization_complete | True |
| pilot_agreement_ge_85 | True |
| pilot | True |
| request_prior | True |
| quoted_prior | True |
| repository_test_isolation | True |
| repository_train_validation_isolation | True |
| isolation | True |
| pretrain_probe | True |
| two_laya_fits | True |
| posttrain_probe | True |
| offline_recall_not_lower | None |
| real_attack_success_zero | None |
| normal_added_ASK_le_2 | None |
| verify_v2_all_passed | None |
| S1_enabled | False |
| stage_E_started | False |

机读结果SHA-256：`f28304ca8f40081b78bab8e19dbd5982f6e5e0a6b7d7374ed90ab4f03f35fa98`

报告SHA-256：`39c56303c1e0e440cc63f7fb6dbabfe8c48a81cb44cea3e327afd736987af368`

安全/冻结校验：`{"passed": true, "secret_hits": [], "request_log_fields_valid": true, "snapshot_files_unchanged": true, "D3_training_unchanged": true, "D3_validation_unchanged": true, "heldout_unchanged": true, "gold_unchanged": true, "D4_real_test_unchanged": true, "test_repository_overlap": [], "local_tracked": false, "teacher_env_ignored": true, "production_config_absent": true, "training_clock_absent": false}`

真实运行ID：`[]`；verify_v2：`None`。
