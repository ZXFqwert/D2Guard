# 阶段D5核验摘要

D5 已停止：原注入队列quoted三方一致率低于70%；即使剩余票全部一致仍无法达到70%，按用户预登记规则停止；S1关闭。

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
| GLM_early_per_class_70 | False |
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

机读结果SHA-256：`fb2d09f95068e36a3d3a9d2a9c4d94c878e85b7e8bf5b0f07a212a175d3f3dcb`

报告SHA-256：`8f36a3c51a994164d4200b6dab3523904a8bbaec54cbb8918fcd1091c324347a`

安全/冻结校验：`{"passed": true, "secret_hits": [], "request_log_fields_valid": true, "snapshot_files_unchanged": true, "D3_training_unchanged": true, "D3_validation_unchanged": true, "heldout_unchanged": true, "gold_unchanged": true, "D4_real_test_unchanged": true, "test_repository_overlap": [], "local_tracked": false, "teacher_env_ignored": true, "production_config_absent": true, "training_clock_absent": true}`

真实运行ID：`[]`；verify_v2：`None`。

最新续跑状态：650 条旧 quoted 整批退出并保留审计；新批次按原门槛复核中。下列旧停止结果作为历史记录，不能视作新批次结果；训练评测与最终验收尚未完成。
