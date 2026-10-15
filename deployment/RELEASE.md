# 双镜 D²Guard 发行与部署记录 · 2026-10-15

## 访问与使用入口

- **本地桌面版**：Windows 桌面快捷方式 **`双镜 D2Guard`**（或解压 `release/D2Guard-1.0.0-Windows-x64.zip` 运行 `D2Guard.exe`）。
- **公网体验平台**：[https://agent.li33.art/safe](https://agent.li33.art/safe)（旧入口 `/safe/desk/` 自动 307 跳转至 `/safe/`）。
- **GitHub 团队仓库**：[https://github.com/ZXFqwert/D2Guard](https://github.com/ZXFqwert/D2Guard)

## 本次核心升级摘要

1. **$D^2$ 增量安全状态链压缩为安全分量（`build_security_chain_summary`）**：
   - 将多轮长程任务产生的超长 JSON 压缩为定长 12 维结构化安全分量，同时赋能快镜 System 1（Laya 联合评判“前序安全链 + 当前增量”）与慢镜 System 2（`<audit_evidence_sandbox>` 脱敏证据包深度复核）。
2. **双 A100 80GB 算力机微调与轻量化蒸馏落地**：
   - 基于 `/home/roots/d2guard-v4-lab/models/verified-laya-e4e9ddf` 教师模型与 1,280 条 `(SecurityChain + CurrentDelta)` 样本训练导出 `D2guard_core/weights/laya_d2_distilled.json`（验证集动作对齐准确率 `100%`，联合准确率 `97.4%`）。
   - 普通 PC CPU 1,000 次推理实测：`P50 = 0.115ms`，`P95 = 0.253ms`，`P99 = 0.349ms`。
3. **视觉升级（Codex 极简风 + 双镜光学战术装甲）**：
   - 移除旧版二次元猫骑士与旧 Arena 页面，统一为 Codex 极简工作台、双镜几何光学矢量徽章、战术光学装甲外框（`双镜铠甲护体中 · Hook + Gateway + Core 全链路接管`）与左侧五页独立导航。
4. **全量清理旧版本**：
   - 算力机已停用并清理旧版 `d2guard.service`、`d2guard-bridge.service` 及旧版目录，由 `d2guard-unified.service` 直接接管 `8000` 端口 `/safe` 主路由。
