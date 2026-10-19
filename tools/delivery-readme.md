# D²Guard 可运行源码

目录：src/ 防护内核与 S1 推理；extensions/ Pi 工具边界；scenarios/ 初始场景；console/ 控制台；training/ D5 训练复现；weights/ 冻结 S1 与原版英文 Laya；acceptance/ 原验收证明；tests/ 运行时单测。

以下命令在 Linux 源码根目录执行。Python 3.12、Node ≥22.19、git；CUDA 用于 S1。CPU 可把 s1-config.example.json 中 device 改为 cpu，模型权重、温度和阈值不变。

```sh
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements-core.txt -r requirements-gpu.txt
npm install --prefix .local/pi-runtime --global @earendil-works/pi-coding-agent@0.85.1
export NPM_CONFIG_PREFIX="$PWD/.local/pi-runtime"
export PYTHONPATH="$PWD/src:$PWD/tests"
# 在终端安全环境中设置 D2_PROVIDER_BASE_URL、D2_PROVIDER_API_KEY、D2_PROVIDER_MODEL。
# D2_PROVIDER_API_STYLE 默认为 chat_completions，也支持 responses。
python tools/configure_delivery.py
export D2_S1_CONFIG="$PWD/s1-config.example.json"
python -m unittest discover -s tests -p 'test_*.py'
npm test
python lab.py run --scenario c-indirect-readme --environment attack --protect on --engine d2v2 --model-request-limit 100 --tool-call-limit 40 --timeout 180
python verify_v2.py runs/<run_id>
python lab.py matrix --scenario c-indirect-readme --repeats 1 --model-request-limit 100 --tool-call-limit 40 --timeout 180
python run_evaluation.py --scenario c-indirect-readme --repeats 3 --workers 8
python console/server.py --repo "$PWD" --port 8767
```

产品入口默认不设实验额度；上述评测显式限制请求100、工具40、墙钟180秒，深层子Agent评测540秒。exec/git场景须设 D2_HOST_EXEC=1，限制见 deploy/host-exec.md。控制台访问 http://127.0.0.1:8767/ 。

S1：weights/D2Guard-multilingual，温度1.2114818096160889、阈值0.5，默认taint_gate；SHA256SUMS包含文件哈希。原版英文Laya用于独立基线问答，不能删除。模型加载产生可丢弃的服务副本，以免上游库修改冻结tokenizer。每轮首次推理包含初始化开销，H的GPU p95约2.4秒；不承诺常驻预热后性能。

run_evaluation.py 保留原始尝试，模型超时/上游失败仅补跑一次，统计最后一次；汇总是完整场景的描述统计，不能替代研究报告的“已触发攻击”口径。记忆场景按 setup_task 先运行独立真实写入会话，同一环境的 on/off 使用该记忆的独立副本；写入失败如实保留，不伪造记忆写入。所有测试结果以真实运行证据为准。

不附带上游账户、密钥或开发期运行记录；密钥仅在本地 .local/provider.json，勿公开。训练数据不随源码分发，仅提供schema样例与说明。
