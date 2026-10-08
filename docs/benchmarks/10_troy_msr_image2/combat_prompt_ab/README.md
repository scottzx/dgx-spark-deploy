# 双人夺门：模型与动作描述对照

2026-10-06的新12段实测：两个本地模型、两种前景动作描述、三个种子。统一Qwen首帧、5秒、672×384、24fps。H3原生完整VAE解码；LTX独立首帧生成。本轮没有MSR、尾帧或战斗LoRA。

查看[审阅页](review.html)、[实测结论](qa.md)、[15秒四组并排](comparison_15s.mp4)和[H3较好候选](best_duel.mp4)。H3新描述在三个种子均增加攻防阶段；LTX武器一致性仍失败。候选仍需修订动作，音轨尚未听审。

`manifest.json`冻结输入；`acceptance.json`冻结共同评价标准；`quality_review.json`为绑定实际输出哈希的人工观察。`verification.json`、`assembly_verification.json`和`browser_verification.json`分别记录文件、拼接与实际页面播放。服务恢复以最终`session.json`和独立`service_health_after.json`为准。

运行过程：`prepare.py` → `run_h3.py` → `offline_session.py`中的原生解码、LTX缓存与推理 → 本地采样审查 → `record_review.py` → `assemble.py` → `build_review.py` → `check_review.py`。

H3为已有W8A8／FastH3-VSA加速配置，LTX为8步蒸馏路径。本轮结果不能推广为两个完整底模的总体排名，不能直接与上一轮MSR首尾帧批次比较通过率。
