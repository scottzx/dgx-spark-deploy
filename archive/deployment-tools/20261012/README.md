# 已退役的部署工具

这些文件用于追溯历史部署，不作为当前执行入口。原始内容保持不变，文件名增加 `.disabled`，并移除全部执行位；Spark 原运行路径已移除。

12 项文件的原路径、归档路径、SHA-256、原权限、修改时间及逐项原因保存在 [`scripts/deployment_manifest.json`](../../../scripts/deployment_manifest.json) 的 `archived_remote_files` 中。处理依据和当前替代入口见 [脚本一致性记录](../../../docs/deployments/脚本一致性.md)。

远程归档位置：`/home/admin/sol-spark-runtime/archive/legacy-tools-20261012/`。

不要通过解释器直接运行这些历史文件。确需复用时，先审查固定 PID、旧输出目录、字符串补丁和服务调用目标，再以受管新入口恢复。检查器会拒绝原路径重新出现、归档内容漂移或执行位被重新开启。
