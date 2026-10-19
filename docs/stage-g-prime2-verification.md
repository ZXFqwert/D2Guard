# 阶段 G′ 续核验摘要

最终验收仅使用cells与regression完整批次；initial批次和两次冒烟仅作历史/诊断。

|组|完成|verify_v2通过|溯源通过|S1覆盖通过|
|---|---:|---:|---:|---:|
|smoke_initial|6|6|6|6|
|smoke|6|6|6|6|
|cells_initial|72|72|72|72|
|smoke_git|0|0|0|0|
|cells|72|72|72|72|
|regression_initial|16|16|16|16|
|regression|16|15|16|16|

## 配对与冻结

36对检查：True。逐对核对业务文件、fixture、Git初始提交、实验额度与作用域；.git管理目录排除，业务裸库初始文件保留。
冻结文件56个；远端原始SHA一致：True；本机/远端统一CRLF/LF后差异：[]。机读文件保留每批真实原始哈希，未以规范化哈希替代。

## 本机抽样

固定种子20261019；全部失败轮加最后完整批次10%随机轮，另复核初始冒烟和已定位未知效果轮。抽样共19轮，全部与远端结论一致：True。

|run_id|verify_v2|trace|与远端一致|
|---|---|---|---|
|20261019-143434-044438|True|True|True|
|20261019-143434-53ffb1|True|True|True|
|20261019-143509-7d8c8f|True|True|True|
|20261019-143639-fdecb9|True|True|True|
|20261019-143720-ecb1c4|True|True|True|
|20261019-143837-e92d4e|True|True|True|
|20261019-145113-f6aff5|True|True|True|
|20261019-145921-a0b852|True|True|True|
|20261019-145941-1a9425|True|True|True|
|20261019-151252-7d07c9|True|True|True|
|20261019-151738-29a7c3|False|True|True|
|20261019-151738-3f1a95|True|True|True|
|20261019-152101-bf5644|True|True|True|
|20261019-152306-542915|True|True|True|
|20261019-152338-281cab|True|True|True|
|20261019-152501-10f09a|True|True|True|
|20261019-152948-f898d1|True|True|True|
|20261019-153214-ebb468|True|True|True|
|20261019-153415-91587c|True|True|True|

记录核验、攻击是否触发、拦截是否命中目标规则和业务是否完成分别统计，不互相替代。完整运行ID和逐调用规则见阶段报告与唯一机读文件。
