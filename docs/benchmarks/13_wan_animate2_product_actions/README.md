# Wan-Animate-2：三组商品动作迁移测试

2026-10-07 开始部署，2026-10-08 继续测试。目标沿用上一轮：原味、健怡、零度分别完成“拿起 → 手持介绍 → 放回并松手”，保留 Serena 柔和配音和嘴部平滑过渡。

## 输入来源与范围

用户确认没有实拍素材，并明确授权使用现有生成视频作为参照。本轮使用上一轮 LTX-2.5 的三条动作原片，每条 768×512、25 FPS、201 帧、8.04 秒。它们尚未经过 MuseTalk，避免将旧口型处理痕迹作为动作条件。

参考图使用同一位红色上衣女性、灰色背景和三罐商品的桌面画面。人物、商品以及动作输入均含生成内容，不能将本轮结果称为实拍驱动验收，也不能据此推断真实商品包装的保真能力。原输入的健怡包装、手指和商品文字已有误差。

## 本轮管线

```text
三组 LTX-2.5 动作原片＋共同人物/桌面参考图
    → Wan-Animate-2 14B Distilled / Diffusers ModularPipeline
    → 原生 24 FPS 视频，逐段携带前一段尾帧
    → 按时间戳转换为 25 FPS / 201 帧
    → 既有 Serena 音轨＋MuseTalk 动态嘴部处理
    → 0.48 秒渐入渐出＋7 帧人脸框平滑
    → 三组独立片及完整拼接片
```

Wan 动作迁移不直接生成中文配音。本轮重新生成完整动作视频，再对 Wan 输出逐帧做嘴部处理；保留已有音轨，避免声音变化影响对比。

## 部署与首轮验证

硬件为 DGX Spark / NVIDIA GB10，128 GB 统一内存，ARM64。新运行目录 `/home/admin/wan-animate2-runtime`，权重目录 `/home/admin/models_cache/Wan2.2-Animate-2-14B-Distilled-Diffusers`。

核心依赖放在独立 `deps` 目录，通过进程内 `PYTHONPATH` 使用：PyTorch 2.14.1+cu130、Diffusers 0.41.0、Transformers 5.19.0、Hugging Face Hub 1.33.0、Safetensors 0.8.0、Tokenizers 0.23.2。基础数字人环境的软件包未被升级。采用已经合并的 `WanAnimate2DistilledModularPipeline`，不是 README 曾引用的未合并传统 Pipeline PR。

权重通过 ModelScope 获取，文件路径、提交版本、长度与 SHA-256 固定在 [modelscope_manifest.json](modelscope_manifest.json)。复用缓存中哈希相同的 tokenizer 词表，其余下载后逐文件校验。`modular_model_index.json` 另行补齐，记录在 [modular_manifest.json](modular_manifest.json)。

GB10 编译版 Flex Attention 已与小规模密集计算比较通过：最大绝对误差 0.00390625，平均绝对误差约 0.000099。此项仅验证计算内核，完整模型单独验证。

官方真人舞蹈 → 小猫参考图的 49 帧、24 FPS 短片已成功生成。模型初始化 361.56 秒；包含首次编译的生成阶段 79.68 秒；峰值 CUDA 分配 50.33 GiB。原始输出 288×510，导出器自动调整为 288×512。这个例子仅用于环境验证，不参与商品动作验收。原始素材与提交版本见 [official_inputs/sources.json](official_inputs/sources.json)，运行测量见 [official_output/metrics.json](official_output/metrics.json)。

## 商品测试参数与验收

三条商品片共享一次模型加载，BF16，蒸馏模型每段 10 步；目标面积 576×384，原生 24 FPS，每段 81 帧，段间携带 1 帧。原始 25 FPS 输入由官方预处理按时间戳采样为 24 FPS。输出需要验收取罐顺序、手指接触、放回松手、商品总数、包装文字、人物一致性，以及内部段落交界和开口/收口的连续性。

官方预处理对目标帧数取整：`int(201 / 25 × 24) = 192`，原生输出为 8.00 秒。转换回 25 FPS 后，将最后一个已经生成的画面保持 40 毫秒，得到 201 帧、8.04 秒，与已有音轨对齐。没有变速、倒放或用保持帧补造放回动作；来源与转换记录保存到 `normalization.json`。

三组商品运行、配音、口型与媒体验证已完成。完整片为 **576×384、25 FPS、603 帧、24.12 秒**，三组之间在 8.04 和 16.08 秒剪辑衔接。查看 [播放与同步对比页](review.html)，或直接播放 [完整测试片](three_products_wan_serena.mp4)。

| 商品 | Wan 生成阶段（秒） | 原生输出 | 峰值 CUDA 分配 | 关键帧动作流程 | 包装保真 |
| --- | ---: | --- | ---: | --- | --- |
| 原味 | 536.95 | 192 帧 / 24 FPS / 8.00 秒 | 60.90 GiB | 拿起、手持、放回、松手可见 | 未通过 |
| 健怡 | 529.41 | 192 帧 / 24 FPS / 8.00 秒 | 60.90 GiB | 拿起、手持、放回、松手可见 | 未通过 |
| 零度 | 530.38 | 192 帧 / 24 FPS / 8.00 秒 | 60.90 GiB | 拿起、手持、放回、松手可见 | 未通过 |

模型共享初始化 350.53 秒，三组生成阶段合计 1596.74 秒（26.61 分钟）；上述生成计时包含驱动视频加载、预处理、分段推理、解码和本次编译，不包含模型初始化或 MuseTalk。MuseTalk 共享加载 7.28 秒，三组分别准备/渲染约 17.23、16.27、23.73 秒。不同分辨率、不同模型和不同输入条件下的上一版计时，不构成严格速度对照。本轮是离线生成测试。

人工检查三个商品的 0 / 0.8 / 1.6 / 2.56 / 4 / 5.44 / 6.2 / 7.2 / 末帧，以及段落交界相邻帧与放回松手近邻帧。三组均可见从桌面拿起、持续手持、放回并松手，抽查画面中保持三罐商品。原味、零度主要单手持罐，健怡主要双手持罐。

抽查开口、收口放大帧，平滑口型没有原先的整幅硬切。三组人脸检测均无漏检，连续权重检查通过；Wan 段落交界存在小幅脸部像素变化，不能宣称所有微小闪动都消失。没有运行 SyncNet、OCR 或人物识别评分，精确音画同步未量化验收。

**本轮结论：动作迁移与完整口播管线可运行，包装保真仍未通过。** 银罐上原有错误文字被带入输出，红罐字样也会重绘。使用生成素材作为动作参照，没有消除参照中的包装错误。576×384 是可行性原型分辨率，不能据此判断该模型在实拍、高分辨率输入下的质量上限。

[verification.json](verification.json) 记录 16 个媒体文件的完整解码、帧数、帧率、时长和 SHA-256。三组配音输入与上一版哈希完全相同；原始动作参照、人物参考图、Wan 输出及口型实际输入均通过哈希绑定检查。开口、收口和段落交界的相邻帧诊断见 [transition_diagnostics.json](transition_diagnostics.json)，人工记录见 [qa.json](qa.json)。此相邻帧 MAE 包含编码影响，只作排查诊断，不能代替自然度或口型准确度评分。

## 复现

仓库脚本目录为 `scripts/04_test_benchmark/wan_animate2_trials`。同步脚本到 Spark 对应运行目录后：

```bash
/home/admin/digital-human-runtime/avatar-env/bin/python /home/admin/wan-animate2-runtime/prepare_product_inputs.py
PATH=/home/admin/.local/bin:$PATH \
CPATH=/home/admin/sol-spark-runtime/sysroot/usr/include/python3.12:/home/admin/sol-spark-runtime/sysroot/usr/include \
PYTHONPATH=/home/admin/wan-animate2-runtime/deps \
/home/admin/digital-human-runtime/avatar-env/bin/python /home/admin/wan-animate2-runtime/run_wan_animate2.py \
  --batch-manifest /home/admin/wan-animate2-runtime/inputs/products/batch.json \
  --output /home/admin/wan-animate2-runtime/outputs/products_576 \
  --width 576 --height 384 --segment-frames 81 --input-kind generated_product_video
/home/admin/digital-human-runtime/avatar-env/bin/python /home/admin/wan-animate2-runtime/prepare_dubbing.py
PATH=/home/admin/.local/bin:$PATH \
/home/admin/digital-human-runtime/avatar-env/bin/python /home/admin/digital-human-runtime/dub_product_actions.py \
  --inputs /home/admin/digital-human-runtime/inputs/product_actions_serena \
  --motion /home/admin/wan-animate2-runtime/outputs/products_25 \
  --output /home/admin/wan-animate2-runtime/outputs/products_dubbed --transition-mode smooth
```

复现依赖导出 `CPATH`，提供当前 PyTorch 编译所需的 Python/C 系统头文件。CPU/GPU 同时驻留，不启用额外模型服务；延续之前服务暂停的授权。

同步 Spark 的 `outputs/products_576`、`outputs/products_25`、`outputs/products_dubbed` 到本报告 `motion`、`motion_25`、`dubbed`；同步生成动作参照到 `inputs`、配音到 `voice`。在 Mac 执行 `python3 scripts/04_test_benchmark/wan_animate2_trials/assemble_review.py` 生成完整片、对比页、接触表和解码证据。脚本按媒体实际末帧裁定取帧时间，避免在 8.00 秒原生视频的终点读取空帧。

## 官方依据

- [Wan-Animate-2 仓库](https://github.com/Wan-Video/Wan-Animate-2)
- [蒸馏模型](https://huggingface.co/Wan-AI/Wan2.2-Animate-2-14B-Distilled-Diffusers)
- [Diffusers 官方合并实现文档](https://github.com/huggingface/diffusers/blob/3a2f35d4efa4c059c8bfb3bc0d6c906264895c81/docs/source/en/api/pipelines/wan_animate_2.md)

这一模型以参考图和驱动视频生成新画面，动作参照不是原始商品像素的直接保留。包装文字是否可用必须查看输出。
