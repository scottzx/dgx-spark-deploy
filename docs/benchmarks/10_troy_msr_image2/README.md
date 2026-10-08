# 木马计：夺门 · 战斗分镜 V2

按用户要求补充夺门战斗和军队大场面，扩展为 **8 场、20 镜，剪辑目标约 100 秒**。前十二镜保留，后八镜改为集结、发现、近战、掩护解闩、城外军阵、交战推门、冲门大战和广场混战。

- [V2 分镜预览](storyboard_v2/review.html)、[剧本](script_v2.md)、[场景拆解](scene_breakdown_v2.md)。
- [镜头表](storyboard_v2/shotlist.json)、[生成记录](storyboard_v2/results.json)、[静态审阅](storyboard_v2/qa.md)。
- [V1 历史说明](README_v1.md) 与 [16 镜对照](storyboard/review.html)。

2026-10-05 用户明确要求后续由 **Qwen Image 2.1** 生图。云端队列已停止。已有资产与 S01–S14 保留原始 image_gen 来源；S15–S20 由 Spark 自托管的 Qwen-Image-2.1 生成，采用 **BF16 原版 40 步、1536×864、多参考图、无 Turbo LoRA**。本轮共 9 次 Qwen 请求，选用 6 张，另保留 3 张需修订初稿；HTTP 生成累计约 741 秒，不含服务加载、传图、审阅和恢复。服务的 `performance-mode=speed` 是 SGLang 执行优化，不等于 6 步 Turbo。完整请求、原始返回 PNG、参数、哈希和本地脚本保存在 `qwen21/`。

两张双方军团造型参考保存在 `assets/groups/`，仍为切换前的云端结果，见 [来源记录](combat_asset_manifest.json)。它们提供衣甲方向；具体人物数量、旗帜、动作和英雄出场由每镜指定。解闩与推门时必须收剑、腾空双手；战斗镜允许右手拔剑，奥德修斯和阿伽门农无盾。

剧本与静态分镜已完成，首轮 MSR V2 视频测试也已生成并拼接为100秒影片。军队规模、手部接触和动态连续性的限制见 [视频审阅记录](video_msr_v1/qa.md)。

[文件与来源校验](storyboard_v2/verification.json) 已通过：20 张选用图、74 个预览资源路径、PNG 校验与源图复制一致。静态人工审阅 11 镜通过、9 镜部分通过，具体限制见审阅页。

## MSR V2 视频测试 V1

按当前 V2 的 20 镜生成原生动态视频，再顺序拼接为 100 秒测试片。20 镜与 100 秒成片已完成；[视频预览与逐镜进度](video_msr_v1/review.html)、[固定参数](video_msr_v1/manifest.json)。详见 [视频说明](video_msr_v1/README.md)。

视频测试主要发现：S15 近战较好；大军团有规模，但持续交锋偏弱。下梯方向、白天/夜间和武器/门闩连续性存在偏差，详见 [视频审阅](video_msr_v1/qa.md)。

## V2 工程回归

新增四镜头、三种条件、双种子的24片段回归，使用本地Qwen起止图、结构化镜头状态、输入指纹与独立质量验收。进度与结果见 [V2说明](video_msr_v2/README.md) 和 [对比审阅页](video_msr_v2/review.html)。

## 夺门打斗专项对照

2026-10-06完成两个本地模型 × 两种前景动作描述 × 三个种子的12段对照，统一Qwen首帧、5秒、672×384、24fps。当前部署的H3配合连续攻防描述，在三个种子中均增加了动作阶段；LTX仍存在兵器变化问题。H3候选仍有盾挡停顿和受力不足，尚未通过完整成片验收。查看[专项说明](combat_prompt_ab/README.md)、[审阅页](combat_prompt_ab/review.html)与[实测结论](combat_prompt_ab/qa.md)。
