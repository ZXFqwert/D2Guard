# 双模式发行与部署记录 · 2026-10-15

## 使用入口

- [Windows x64 发行包](https://github.com/ZXFqwert/D2Guard/releases/tag/unified-v1.0.0)：下载 ZIP，完整解压，双击 `D2Guard.exe`，无需 Python / Node。
- [新版工作台](https://agent.li33.art/safe/desk/)：同源 API，通过算力机运行真实审计与模型调用。
- [旧版 Arena](https://agent.li33.art/safe/)：保留原入口、功能、代码和数据。

仓库为私有仓库，下载发行包需要有访问权限的 GitHub 账号。Windows 包尚未进行代码签名。
模型密钥不在仓库或发行包中；桌面个人配置保存在 `%APPDATA%/D2Guard/`。

## 算力机更新

```bash
cd /home/roots/d2guard-unified/unified
bash deployment/deploy.sh --pull
```

此命令拉取 GitHub，构建 Web 界面，更新独立环境，并重启新版服务。旧版环境不升级。

| 项目 | 实际位置 |
| --- | --- |
| GitHub 新版代码 | `unified/` |
| 算力机新版 checkout | `/home/roots/d2guard-unified` |
| 新版服务 | `systemctl --user status d2guard-unified` |
| 兼容入口 | `systemctl --user status d2guard-bridge` |
| 新版后端 | `127.0.0.1:8766` |
| 既有代理入口 | `0.0.0.0:8000` |
| 新版持久化数据 | `~/.local/share/d2guard-unified/` |
| 旧版目录 | `/home/roots/D2Guard` |

已有 VPS 转发链路保持原端口。兼容入口只代理 `/safe/desk`，其余请求交给旧版应用。
新版的主模型与慢镜已配置 `huihui-qwen3.8-27b`；公共访客不能改写服务器共享模型配置。
个人桌面版支持完整的模型设置。

## 回滚

```bash
bash /home/roots/d2guard-unified/rollback-bridge.sh
```

该脚本停用兼容入口，在旧目录恢复原 `web_demo:app` 启动命令。
如需单独停止新版：`systemctl --user stop d2guard-unified`。
数据目录独立于 checkout，更新与回滚不删除模型配置或审计数据。

## 验收

- Windows、Linux 分别通过 192 项 pytest；保留一条既有 Starlette 弃用提示。
- 桌面与 Web 两种构建成功。
- 实际打包后的 exe：PB-01 至 PB-06 在普通/铠甲模式均验收通过，包含 ASK 批准与拒绝、自由 JSON、真实主模型规划、慢镜复核。
- Windows 重复启动聚焦已有窗口；关闭窗口回收所启动的内核。
- 公网入口完成同样的真实链路验收：页面错误 0，HTTP 失败 0，原五个 API 均实际调用。
- 三个原通信文件、三个原启动文件及旧 Electron 入口共 7 个冻结文件 SHA256 保持一致。
- 旧版首页在兼容入口切换前后内容一致。
- ZIP SHA256：`f769edb32087f327db3d10b4a0edb1a34a53b683739060f5f091a67e7a6869c9`。
