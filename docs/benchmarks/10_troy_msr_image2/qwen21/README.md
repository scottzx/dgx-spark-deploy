# Qwen Image 2.1 · 夺门战分镜

此目录保存用户指定的自托管生图路径。没有调用云端文生图入口。

- 主机：`admin@100.115.178.96` / `spark-e72e`。
- 权重：`/home/admin/models_cache/Qwen-Image-2.1`，已有本地官方 BF16 权重；离线加载。
- 服务：已有 SGLang 环境，原生 backend + torch SDPA + performance-mode speed。
- 生成：40 步、CFG 1.0、1536×864、CUDA seed、多参考图。没有加载 Turbo LoRA，没有把少步采样冒充精细生图。
- `requests/` 是实际完整请求；`inputs/` 是未经改动的参考 PNG 副本；`outputs/` 保留原始 PNG 返回与逐图参数/参考 SHA-256。
- `generate_frame.py` 仅请求 Spark 回环地址 `http://127.0.0.1:30010/v1/images/edits`。
- `import_frame.py` 在复制到分镜目录前检查原图、提示词和每个实际参考图的哈希一致性。

`serve_session.py` 先确认已启动的 fl2va 视频服务 READY、无客户端连接、GPU 利用率为零，再以 SIGTERM 请求正常关闭；不强杀视频任务。获取两个推理锁后加载图片服务。本轮结束、失败、信号中断或会话时限到达，均释放图片服务和锁，重新启动原 fl2va 服务并等待健康。会话记录和运行日志随结果归档。

已有 cloud image_gen 资产和 S01–S14 是历史输入。保留它们的实际来源，不将其标为 Qwen 输出。本轮 Qwen 图片不代表已经完成 MSR 视频或多 seed 稳定性测试。

本轮已完成：9 次 Qwen 请求、6 张选用图、3 张修订前图；20 张全套分镜文件检查通过。图片服务已退出，原 fl2va 视频服务恢复为 READY，见 `session.json`。服务实际参数见 `server-config.json`，运行日志为 `sglang-server.log` 与 `restored-video-server.log`。
