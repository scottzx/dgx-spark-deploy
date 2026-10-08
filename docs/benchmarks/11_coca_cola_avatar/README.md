# 可口可乐数字人三路线实测

2026-10-07，在 DGX Spark / GB10 上轮流测试固定中文带货口播。三条路线均使用同一张原创虚构成年主播照片、同一段 26.44 秒配音，以及可口可乐官网的原味、健怡、零度易拉罐参考图。

打开 [对比页面](review.html) 可同步播放、切换人物原片、下载竖版成片。完整测量表见 [RESULTS.md](RESULTS.md)，原始数据见 [comparison_metrics.json](comparison_metrics.json)，媒体校验见 [verification.json](verification.json)。

## 测试范围与配置

| 路线 | 实际运行的组件 | 本次配置 |
| --- | --- | --- |
| A | LiveTalking 中的 MuseTalk 1.5 模型、音频特征、人物素材准备和人脸合成 | FP16，256×256 嘴部区域，8 帧批次，768×768 原片；单张照片用 OpenCV Haar 定位 |
| B | OpenAvatarChat 的 FlashHeadProcessor，接 SoulX-FlashHead Lite | BF16，512×512，4 步，24 帧流式输出批次；音频滑窗和配对输出队列实际运行 |
| C | EchoMimicV3 Flash 原生推理管线 | BF16，512×512，8 步，81 帧分镜；Audio CFG 3、Text CFG 6、Flow UniPC；未启用 TeaCache |

A/B 没有运行浏览器 WebRTC、问答 LLM、打断、OBS 推流或长时间直播。C 每个分镜重新使用同一张参考照片，尚未加入跨分镜人物状态延续。首个 3.24 秒接缝可见嘴部与头部回到参考姿态，这一轮保留原片供对比，不将其视为已经解决的连续性。首批或首段分别为 A 的 8 帧、B 的 24 帧、C 的 81 帧，不能直接作为相同定义的直播首帧延迟比较。

有效 FPS 使用人物生成阶段的实际耗时：A 包含合成与写帧，B 包含缓冲、推理、帧转换和输出队列，C 包含逐分镜生成和写帧。最终广告排版、音频编码、TTS、模型下载及加载不计入该 FPS。加载数字取自本次文件缓存条件，并非冷机启动。CUDA 峰值是 PyTorch allocated；Spark 的统一内存还包括 CPU、文件缓存及其他分配。

## 输入与商品展示

主播由本地 Qwen-Image-2.1 加六步 LoRA 生成，768×768，固定种子 20261007；[原始照片](assets/presenter.png) 与 [生成记录](assets/presenter.json) 已保存。配音由本地 Qwen3-TTS-12Hz-1.7B-CustomVoice / Vivian 生成，24 kHz；模型驱动使用同源 16 kHz 重采样版本。完整 [配音](assets/narration.wav)、[句子时间表](assets/narration.json) 和 [ASR 检查](asr_check.json) 已保存。ASR 覆盖完整文案；“健怡”被识别成“剑怡/剑宜”同音字，字幕使用正确产品名。

口播文案：

> 可口可乐，今天你想选哪一罐？原味，熟悉的经典可乐风味。健怡，无糖，口感更轻盈。零度，同样无糖，更接近原味可口可乐的风味。聚餐、追剧，或者想来一口冰爽，三种选择，按你的口味来。原味、健怡、零度，认准罐身标识，挑一罐你喜欢的，冰镇后更过瘾！

健怡与零度的区别取自 [可口可乐官方说明](https://www.coca-cola.com/us/en/offerings/faq/whats-the-difference-between-coca-cola-zero-sugar-and-diet-coke)。商品图片使用官网英美版参考包装，具体链接见 [sources.json](assets/sources.json)，不代表特定国行 SKU。三罐均为独立商品图层，未让人物生成模型重绘包装。当前没有手持罐装商品动作、价格、折扣或购买链接。

## ARM64 与 GB10 适配

在独立的 `/home/admin/digital-human-runtime/avatar-env` 中运行 Python 3.12 / PyTorch 2.14.1+cu130 / Transformers 4.57.3 / Diffusers 0.36.0。三路数字人推理使用 PyTorch 原生 SDPA。环境通过 `spark_base.pth` 复用已有 Qwen-Image 环境的未覆盖依赖；新安装或固定版本的包均写入 avatar-env，未改动原图像环境。最终依赖版本见 [requirements.lock.txt](requirements.lock.txt)，源代码归档摘要见 [source_receipts.json](source_receipts.json)。

实际改动见 [compatibility.patch](compatibility.patch)：单 GPU FlashHead 跳过未安装的 xfuser 分布式依赖；头像已构图，关闭可选的人脸裁剪；首轮关闭 torch.compile；EchoMimic 去掉未使用的 decord 导入。OpenCV 固定为 4.12.0.88，以保留 Haar Cascade 接口。

EchoMimic 的自定义 T5 加载器在 `low_cpu_mem_usage=False` 分支没有应用传入的 `torch_dtype`。测试脚本显式调用 `.to(torch.bfloat16)` 并打印组件精度。修正前 3.24 秒短测耗时 252.53 秒，CUDA 峰值 29.90 GiB；修正后耗时 72.44 秒，峰值 19.29 GiB。两份短测记录保留在 `smoke_C_t5_fp32` 和 `smoke_C`。完整成片使用修正后的 BF16 配置。

权重清单包含具体 revision、大小和 SHA-256。ModelScope 下载了 33 个文件，HF 补齐 15 个文件；下载器逐个校验，合计约 32.95 GB。只使用 EchoMimic Flash 的 Transformer 权重，Wan 基座提供配置、VAE、T5、CLIP 和 tokenizer；没有额外下载被替换的基座 Transformer。加载日志中 EchoMimic 的 Transformer、VAE、T5 权重均为 0 missing / 0 unexpected keys。

## Spark 上的位置与复现

运行目录：`/home/admin/digital-human-runtime`。模型缓存：`/home/admin/models_cache/digital_human`。输入、原片、逐分镜证据、日志和测量记录分别在 `inputs`、`outputs`、`logs`。

复制仓库中的 `scripts/04_test_benchmark/avatar_trials/run_*.py` 到运行目录后，按顺序执行以下命令。三条路线应轮流占用 GPU。

```bash
ssh admin@100.115.178.96
export PATH=/home/admin/.local/bin:$PATH
export CPATH=/home/admin/sol-spark-runtime/sysroot/usr/include/python3.12:/home/admin/sol-spark-runtime/sysroot/usr/include
export PYTHONUNBUFFERED=1
/home/admin/digital-human-runtime/avatar-env/bin/python /home/admin/digital-human-runtime/run_musetalk.py
/home/admin/digital-human-runtime/avatar-env/bin/python /home/admin/digital-human-runtime/run_flashhead.py
/home/admin/digital-human-runtime/avatar-env/bin/python /home/admin/digital-human-runtime/run_echomimic.py
```

Mac 上的成片合成、校验和页面生成：

```bash
python3 scripts/04_test_benchmark/avatar_trials/assemble_samples.py A B C
python3 scripts/04_test_benchmark/avatar_trials/verify_outputs.py
python3 scripts/04_test_benchmark/avatar_trials/build_review.py
```

合成脚本依赖本机 Pillow、NumPy、`/opt/homebrew/bin/ffmpeg` 及 macOS 的 Hiragino Sans GB 字体。输出为 1080×1920、25 FPS、H.264/AAC 的 26.44 秒竖版视频，字幕直接使用 TTS 句子时间表。校验脚本检查完整解码、661 帧、音视频时长与三条成片的解码音轨一致性。

按用户授权已暂停 Sol-H3 API 及其 Stage 1/2、Qwen 容器、异步网关和会话代理，停机前进程/容器快照保存在 [services_before_tests.json](services_before_tests.json)。释放资源后可用内存从约 17 GiB 提升到 117 GiB。本轮结束后旧服务保持暂停。快照保存启动命令、工作目录和容器名；恢复时使用原来的服务启动配置，既有入口位于 `/home/admin/sol-spark-runtime/start_sol_server*.sh` 和 `start_gateway.sh`。

## 开源项目来源

- [LiveTalking](https://github.com/lipku/LiveTalking)：Apache-2.0 框架。
- [MuseTalk](https://github.com/TMElyralab/MuseTalk#disclaimerlicense)：代码 MIT，官方声明其训练权重可用于商业用途。
- [OpenAvatarChat](https://github.com/HumanAIGC-Engineering/OpenAvatarChat)：Apache-2.0 框架。
- [SoulX-FlashHead](https://github.com/Soul-AILab/SoulX-FlashHead) 与 [权重卡](https://huggingface.co/Soul-AILab/SoulX-FlashHead-1_3B)：Apache-2.0。
- [EchoMimicV3](https://github.com/antgroup/echomimic_v3) 与 [权重卡](https://huggingface.co/BadToBest/EchoMimicV3)：Apache-2.0。

上述是各项目自身的声明；依赖模型和商品素材的来源单独列在清单中。
