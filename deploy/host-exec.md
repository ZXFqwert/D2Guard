# 宿主实验执行（阶段 G′）

设置 D2_HOST_EXEC=1 才注册 exec/git；产品默认模型、工具与墙钟额度仍不限，评测显式设置20/40/180，多层场景单独登记540秒。

执行工作目录与 HOME 都属于本轮 workspace，环境只保留系统 PATH、HOME、LANG；POSIX 下使用独立进程组，超时杀整个进程组。shell AST 中的路径不得越出工作区，HTTP 下载只允许虚拟 http://lab.test 的本地服务，git push 只允许本轮 .lab-remote.git。防护开关两侧使用相同限制。

这是应用层限制，不是操作系统沙箱，也不提供任意程序的完整行为隔离。动态 shell 需 ASK，执行器不运行无法解析的动态语法。测试使用合成凭据、无害脚本和本轮裸库。无需 Docker 或 bubblewrap。宿主实现目前实测目标为 Linux/POSIX；Windows 不自动退回无进程组控制的执行方式。
