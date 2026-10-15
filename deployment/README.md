# 双镜 D²Guard 桌面版与服务器版部署说明

桌面版与公网体验版共享同一套前端（Codex 极简风 + 双镜光学战术装甲 + 五页导航）、同一套真实审计内核（`D2guard_core`）与五条标准 API 契约，并默认加载由双 NVIDIA A100 80GB 算力机微调蒸馏的 Laya 快镜权重（`D2guard_core/weights/laya_d2_distilled.json`）。

## 1. Windows 桌面版（普通电脑即开即用）

- **桌面快捷方式**：双击桌面上的 **`双镜 D2Guard`** 快捷方式（指向 `release\win-unpacked\D2Guard.exe`）。
- **独立发行包**：解压 `release\D2Guard-1.0.0-Windows-x64.zip` 后双击 `D2Guard.exe`，无需安装 Python、Node.js 或独立显卡。
- 关闭窗口自动回收随附的本地内核进程；重复启动自动聚焦已有窗口。
- 用户个人模型配置与会话数据库保存在 `%APPDATA%/D2Guard/`。
- 从源码重新打包：在项目根目录执行 `pwsh -File scripts/build-desktop.ps1`。

## 2. 算力机与公网体验站（`https://agent.li33.art/safe`）

```bash
cd /home/roots/d2guard-current
bash deployment/deploy.sh --pull
```

- 服务名称：`systemctl --user status d2guard-unified`
- 监听地址：`0.0.0.0:8000`（由 VPS 直接代理至公网 `https://agent.li33.art/safe/`，同时自动兼容 `/safe/desk/` 307 跳转至 `/safe/`）
- 持久化数据目录：`~/.local/share/d2guard-unified/`
- 快镜模型：默认加载 `D2guard_core/weights/laya_d2_distilled.json`（`laya-distilled` 后端，`status: ready`）
- 慢镜与主模型：公网体验站默认配置 `huihui-qwen3.8-27b`，公共访客不可篡改服务器共享模型配置；个人桌面版支持在“设置与接入”页自由配置任意 OpenAI / DeepSeek / Qwen 兼容接口。
