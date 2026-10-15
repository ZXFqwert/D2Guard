# 双镜桌面版与服务器版

两种运行方式使用相同的前端、真实审计内核和五条 API 契约。旧版 Arena 保留在仓库原路径；本版放在 `unified/`，不覆盖旧版实现。

## Windows App

下载 `D2Guard-1.0.0-Windows-x64.zip`，完整解压后双击 `D2Guard.exe`。
不需要安装 Python 或 Node。关闭窗口自动关闭随附的内核；重复启动会聚焦原窗口。
若 8765 已被占用，会明确提示，不会终止其他进程。

用户数据与模型密钥保存在 `%APPDATA%/D2Guard/`，升级时不会被安装目录覆盖。
发行包不含开发者的模型密钥、历史会话或本地数据库。首次使用可在设置页录入个人模型。
该构建尚未进行 Windows 代码签名。

从源码构建：在 Windows 执行 `pwsh -File scripts/build-desktop.ps1`。
原 `start_all.py`、三个底层通信文件及 `electron/main.cjs` 保留，供原开发流程使用。
新发行入口为 `electron/standalone.cjs`，PyInstaller 打包的内核同时提供静态页面和 API。

## Linux / 算力机

```bash
git clone https://github.com/ZXFqwert/D2Guard.git
cd D2Guard/unified
bash deployment/deploy.sh
# 后续更新
bash deployment/deploy.sh --pull
```

需要 Python 3.11+、Node 22+、npm、用户级 systemd；私有仓库需先配置自己的 GitHub 登录。
程序独立运行在 127.0.0.1:8766；数据在 `~/.local/share/d2guard-unified/`。
部署不改动旧版 `.venv`、`.env`、数据库及源码。服务配置可用 `systemctl --user cat d2guard-unified` 检查。

构建 Web 版时 Vite 将 API 地址替换为当前网站的 `/safe/desk`，源码中的原通信函数保持不变。
静态资源使用 `/safe/desk/` 基路径；所有 HTTP 接口走相同域名。
公共体验站禁止访客改写共享模型或通过测试接口使用服务器密钥请求任意地址；个人桌面版可完整配置模型。
服务器管理员可通过仅绑定回环的临时本地管理实例配置独立数据库，或离线写入 `desktop_config`。
运行时环境设置放在数据目录 `runtime.env`，不要放入 Git。

## 与旧版 /safe 共存

优先在反向代理增加更具体的路由：

```nginx
location = /safe/desk { return 307 /safe/desk/; }
location /safe/desk/ {
    proxy_pass http://10.33.0.30:8766;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_read_timeout 90s;
}
```

8766 默认仅监听回环，跨机器代理需配合 SSH 隧道或受防火墙限制的绑定地址。
已有 VPS 固定转发至算力机 8000 时，可用 `legacy_bridge.py` 包装旧版入口：
它仅转发 `/safe/desk` 至新版，其他请求原样交给旧版应用。旧版功能与流式响应不经过代理。
在旧版目录，以旧版 Python 启动：

```bash
export D2GUARD_LEGACY_DIR=/home/roots/D2Guard
export PYTHONPATH=/path/to/D2Guard/unified
/home/roots/D2Guard/.venv/bin/python -m uvicorn deployment.legacy_bridge:app --host 0.0.0.0 --port 8000
```

切换前先在空闲端口测试。回滚时停止包装服务，在旧目录恢复原命令：
`python -m uvicorn web_demo:app --host 0.0.0.0 --port 8000`。
新版服务可独立停止：`systemctl --user stop d2guard-unified`。
