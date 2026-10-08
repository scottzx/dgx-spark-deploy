# 手持商品口播：开源方案筛选

核查日期：2026-10-07。这里只记录官方源码、文档和模型卡支持的能力；候选项目尚未在本轮 Spark 上部署，不能把官方视频或其他 GPU 的性能当作本机实测。

## 当前技术架构的边界

现有链路为 Qwen-Image 人物图 → Qwen3-TTS → A/B/C 数字人引擎 → 视频编码。上一轮在最终排版阶段加入独立商品图层，人物生成模型没有接触商品参考图。

[MuseTalk](https://github.com/TMElyralab/MuseTalk) 修改约 256×256 的脸部区域，并支持输入视频。A 可以保留输入里已经存在的手和商品；静态照片本身不会产生拿起、转动、指向等身体动作。如果先准备真实手持动作视频，再逐帧对齐口型，可以继续沿用 LiveTalking 框架，补充其素材准备环节。

[SoulX-FlashHead](https://github.com/Soul-AILab/SoulX-FlashHead) 定位为流式 talking head。可以测试含手和商品的输入，但官方没有提供罐身约束、手物接触约束或具体带货动作控制接口。更换 OpenAvatarChat 外层框架并不能直接补足这些能力，需要评估或更换它所接的生成引擎。

[EchoMimicV3](https://github.com/antgroup/echomimic_v3) 支持音频驱动人物动画，Flash 版提供 8 步推理和文本提示。它是现有安装中最适合先验证身体动作的一路，但商品形状、文字和手指接触需要单独验收。

## 候选比较

| 候选 | 官方支持的输入和能力 | 与本次需求的关系 | 本机验证前不能承诺的部分 |
| --- | --- | --- | --- |
| [LongCat-Video-Avatar 1.5](https://github.com/meituan-longcat/LongCat-Video) | 2026-05-21 发布；音频＋图像／文本、视频续接；Whisper-large-v3 音频编码；8 步蒸馏；480P/720P | 优先评估新一代自然口播、身体运动和长镜头，模型卡见 [这里](https://huggingface.co/meituan-longcat/LongCat-Video-Avatar-1.5) | 商品文字保真、手物接触、GB10 速度；官方示例使用多 GPU，不能直接认定 Spark 实时 |
| [InfiniteTalk](https://github.com/MeiGen-AI/InfiniteTalk) | 音频＋图像／视频；同时处理口型、头部、身体、表情；基于 Wan2.1-I2V-14B；支持单卡、低显存和加速 LoRA | 适合已有“人物拿着商品”的动作视频，或用图像生成较长的身体口播 | 14B 推理成本、ARM64/Blackwell 的注意力与量化兼容；商品标签不由专门约束保证 |
| [Wan-Animate-2](https://github.com/Wan-Video/Wan-Animate-2) | 2026-08-07 发布代码与 Base／Distillation 权重；参考人物图＋动作视频；可直接使用驱动视频；蒸馏示例 10 步 | 有明确拿起、指向、转动商品动作时，作为动作迁移候选 | 本身不是中文音频口型对齐管线，需再接 MuseTalk 或其他口型工具；官方硬件示例为多卡 A800，单 Spark 兼容与性能未测；Lite 的描述不能替代已发布权重核验 |
| [SoulX-FlashTalk](https://github.com/Soul-AILab/SoulX-FlashTalk) | 14B 音频驱动流式人物；官方单卡配置要求超过 64GB 显存，CPU offload 可降到约 40GB | 自然身体口播的备选，而不是直接把 FlashHead 的速度套用过来 | 官方 32 FPS／0.87s 基于 8×H800；不构成单 Spark 的实时承诺 |

## 选择原则

要求是“拿着罐子说话，动作固定”时，先验收手持输入，再用 A 驱动嘴部即可，不必先替换框架。

本轮实际要求是三罐商品分别完成“拿起 → 介绍 → 放回并松手”。应增加动作生成或驱动视频这一环。先用已经部署的 [LTX-2.5](https://github.com/Lightricks/LTX-2) 做首尾与中间关键帧条件的连续动作测试，再用 A 的 MuseTalk 处理实际移动画面的口型。此路径的结果见 [动作报告](README.md)，不能用固定手持基线代替。

需要寻找新项目时，精确拿取流程优先评估 Wan-Animate-2＋口型工具，前提是有真实、完整的商品动作驱动视频；自然音频驱动身体口播可以比较 LongCat-Video-Avatar 1.5；已有动作视频的配音与身体适配可以对比 InfiniteTalk。三者都需要验收目标商品身份、未操作商品原位保留、抓取到松手的连续性以及包装文字。

商品包装必须严格一致时，真实商品／准确 3D 商品与真实动作素材是更可控的输入。生成模型提供的“手持效果”与真实包装准确性需要分别验收，不能用一张看起来正确的首帧代替全片检查。
