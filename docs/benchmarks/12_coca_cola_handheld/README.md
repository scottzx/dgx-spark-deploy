# 三罐商品拿起、介绍、放回：本地动作口播测试

2026-10-07，目标为原味、健怡、零度三个商品分别完成“从桌上拿起 → 口播介绍 → 放回桌上并松手”。基于会话 `01a115b3-cb5c-7311-a3ab-d3edb9a72bf3` 和 [上一轮](../11_coca_cola_avatar/README.md) 的问题，先以 A/B/C 手持口播诊断现有引擎，再补充 LTX-2.5 连续动作生成＋逐帧 MuseTalk 口型对齐。

入口：[完整动作测试](review.html)、[A/B/C 固定手持基线](held_baseline.html)、[开源项目筛选](OPEN_SOURCE_RESEARCH.md)、[基线原始测量](comparison_metrics.json)、[基线媒体校验](verification.json)。

配音更新（2026-10-07）：当前完整动作视频已从 Vivian 换为 Serena 温和女声，使用平稳、亲切的语气，3.5 kHz 频段轻衰减 2.5 dB。三段实测综合响度约 -23 LUFS，比原版分别降低约 5.0、2.2、1.7 LU，避免切换商品时音量忽大忽小。三个介绍文案、2.4 秒开始时刻和动作流程保留，嘴部按新声音重新生成；最后的响度统一只改变增益，不改变口型时序。可 [试听新配音](actions/inputs/voice_preview.wav)、[观看柔和配音版](actions/three_products_serena.mp4)，或 [对比原版](actions/voices/vivian/three_products.mp4)。固定手持 A/B/C 基线仍使用原始 Vivian 配音。

新声音的 [生成与处理记录](actions/inputs/voice.json)、[音频校验](actions/inputs/audio_verification.json) 和 [ASR 检查](actions/inputs/asr_check.json) 已保存。ASR 覆盖三段全文，“健怡”显示为同音字“剑怡”。零度首轮 5.2 秒配音超出介绍窗口，已另行生成 3.68 秒版本，再以保留音高的 1.067 倍微调到约 3.44 秒，未截断文案。原始尝试保存在 `actions/voices/serena/inputs`。

口型过渡修复（2026-10-07）：上一版第 55 帧（2.20 秒）直接切入口型生成画面，第 151 帧（6.04 秒）直接恢复动作底片，造成嘴部和下半张脸瞬间变化，视觉上像跳帧。当前改为 0.48 秒 smoothstep 渐入／渐出；渐入在说话前完成，渐出分别跟随原味 4.69 秒、健怡 5.51 秒、零度 5.84 秒的实际语音结束。脸部框使用 7 帧居中高斯平滑，合成区域收窄为嘴部附近的柔边区域，减少鼻子、脸颊边缘和下巴轮廓变化，没有对整张画面做时间模糊。柔和配音、商品动作和 201 帧时长保留。

三罐共六个旧切换位置的“口型处理残差相邻帧变化”降低 58.3%–73.2%。测量先从口播画面减去同一帧动作底片，再比较下半脸区域的相邻帧差异，用于定位原硬切换；此数值不代表统一的审美、身份或口型准确度分数。连续融合权重、语音期间完整口型强度及音轨哈希检查通过，放大帧已人工检查。可看 [同步修复前后对比](actions/transition_review/review.html)、[测量记录](actions/transition_review/verification.json)、[平滑过渡版视频](actions/three_products_serena_smooth.mp4)。修复前 Serena 版本保存在 `actions/voices/serena_hardcuts`。

## 动作结果与选择建议

三罐分别完成基本的“拿起 → 手持介绍 → 放回原位并松手”，未操作的两罐留在桌上。三组完整口播片合计 24.12 秒、603 帧；每罐内部为一次连续生成，组间为剪辑。详见 [动作验收](actions/qa.json) 和 [逐步帧对照](review.html)。

商品文字、罐身轮廓在运动中仍有变化，输入关键帧的小字也不准确，因此基本流程通过不等于可直接投入正式带货。口型对齐沿用同源中文配音，没有进行自动口型准确度评分。

三条动作原片、三条口播片和最终合成片均通过完整解码、帧数与时长检查，见 [媒体校验](actions/verification.json)。桌面与手机预览页面的视频元数据、实际播放和布局检查通过，见 [浏览器校验](actions/browser_verification.json)。最终口播逐步帧对照已人工检查，记录于动作验收；包装变形仍列为未通过项。

| 商品 | 8.04秒动作生成，含模型加载 | CUDA allocated 峰值 |
| --- | ---: | ---: |
| 原味 | 159.50s | 39.55 GiB |
| 健怡 | 132.67s | 39.55 GiB |
| 零度 | 131.11s | 39.55 GiB |

三段动作合计 423.28 秒，另加逐帧口型准备、渲染和编码；图片与提示词缓存生成另计。这是离线链路，不能由 A 的 29 FPS 推导完整链路实时。

建议保留 A 作为口型模块，增加动作生成或动作素材准备环节，不必先整体替换 LiveTalking/OpenAvatarChat。现有 LTX-2.5 足以继续做离线过程验证；若下一步要求固定抓取轨迹、严格商品身份与更稳定动作，优先评估真实完整动作视频＋Wan-Animate-2／口型工具。自然身体口播的生成候选是 LongCat-Video-Avatar 1.5；两者尚未在本轮 Spark 上实测，见 [来源与边界](OPEN_SOURCE_RESEARCH.md)。

## 当前架构能做到什么

完整动作测试使用共同 768×512 桌面画面，三罐按原味、健怡、零度从画面左到右排列。每罐 8.04 秒／201 帧／25 FPS，介绍音轨在 2.4 秒开始。LTX-2.5 的条件为第 0 帧桌面、第 64／136 帧手持目标商品、第 200 帧回到桌面；每罐内部为一次连续生成，三罐之间正常剪辑。

动作关键帧经过目视验收。首轮零度关键帧错误地保留桌面零度、删除健怡，已拒绝作为动作输入；一次独立重生成的 `actions/inputs/zero_held_v2.png` 正确保留原味与健怡在桌上，仅手持零度。失败图和元数据保留，其他关键帧未重生成。输入文字仍存在误差，不作为准确商品包装资产。

口型阶段逐帧读取生成视频，对每一帧定位脸部、准备 VAE 和脸部合成遮罩，MuseTalk 处理同源音轨；当前合成跟随每罐实际介绍时段，前后分别作 0.48 秒柔和过渡。手、商品、桌面和其他两罐沿用生成视频的实际移动画面；没有插入静态末帧或倒放拿起动作来冒充放回。LTX 源码 revision 为 `d151147788a9284cca791edc6ce898007e727fe6`；具体模型路径见 `actions/ltx_paths.json`。

A/B 的框架可以继续承担音频和人物渲染。缺少的是“人物与商品接触的素材”及“可控制的身体动作”，更换 WebRTC、对话或排版框架不会自动增加这些能力。

如果要求固定姿势拿着商品口播，A 已经可以完成：这轮三罐视频中手与罐子保持稳定，人物嘴部随配音变化。它保留的是输入素材里的手持姿势，没有生成拿起或转动动作。

B 也能保留手持画面，并有头部和表情变化，但细小商品文字受生成影响，短样本平均速度低于 25 FPS。它尚未提供受控的商品展示动作。

C 的口型、头部和表情有变化，但没有执行提示中的明确举罐动作；罐身小字会改变，例如原味输入的 330ml 在部分生成帧中变成 350ml。三罐 11.64 秒生成耗时 268.37 秒，约 1.08 FPS，因此也不能把它当作已经满足完整动作的引擎。

这三路固定手持基线都不满足“拿起、介绍、放回”的完整验收。A 可以继续作为动作视频的口型工具；需要增加真实动作素材、动作视频驱动或身体动作生成引擎。

| 固定手持基线 | 11.64秒生成耗时 | 有效 FPS | CUDA allocated 峰值 |
| --- | ---: | ---: | ---: |
| A | 9.96s | 29.23 | 6.68 GiB |
| B | 22.95s | 12.68 | 4.98 GiB |
| C | 268.37s | 1.08 | 19.32 GiB |

## 固定手持基线的统一输入与测试范围

沿用上一轮的虚构成年主播、Qwen3-TTS / Vivian 中文声音和官网商品参考图；商品图来源见 [原始来源清单](../11_coca_cola_avatar/assets/sources.json)。包装为官网英美版参考，不代表具体国行 SKU。

先用本地 Qwen-Image-2.1＋Viggle Turbo 六步 LoRA，以主播图和每罐商品图作为两个参考，生成三张 768×768 的手持图片：

- [原味](inputs/original.png)：原味，熟悉的经典可乐风味。
- [健怡](inputs/diet.png)：健怡，无糖，口感更轻盈。
- [零度](inputs/zero.png)：零度，同样无糖，更接近原味可口可乐的风味。

每个 SKU 只生成一张输入，不挑选多个种子，不做包装修复或后置商品图层合成。三路共享完全相同的输入图片和音轨。生成元数据含参考哈希、提示词、种子 20261008、耗时和 CUDA allocated 峰值，分别保存于 `inputs/*.json`。

输入目视检查：人物身份、红色上衣、灰色背景基本保持；双手托底和握持商品，接触关系清楚。包装并非逐像素复制，细小英文及布局有变化，尤其零度底部小字已经不准确。这是输入生成环节的误差，不能归咎于数字人动画，也不能因为 A 保持稳定就称其包装完全准确。

复用原始 `voice_01.wav`、`voice_02.wav`、`voice_03.wav`，末尾补静音到 3.88 秒；共同保存 24 kHz 音轨和用于模型驱动的 16 kHz 版本。每罐为 97 帧、25 FPS，三个测试镜头按原味→健怡→零度剪辑成 11.64 秒视频。

固定手持基线的三罐切换是明确剪辑，未测试同一镜头连续换罐，也未测试从桌上拿起。本文新增的 LTX 动作测试补充了拿起、放回并松手；两类测试均未覆盖 360°旋转、包装背面、真人直播、问答打断、WebRTC 或 OBS。

## 推理配置与计时

| 路线 | 实际组件 | 原片配置 | 动作来源 |
| --- | --- | --- | --- |
| A | LiveTalking 中的 MuseTalk 1.5 音频特征、模型与脸部合成 | FP16，256×256 脸部区域，8 帧批次，768×768 原片 | 共同照片保持手与商品，模型修改嘴部 |
| B | OpenAvatarChat FlashHeadProcessor＋SoulX-FlashHead Lite | BF16，512×512，原生 SDPA，未启用 torch.compile；关闭裁剪以保留手和商品 | 模型生成头部、表情和图像变化 |
| C | EchoMimicV3 Flash | BF16，512×512，8 步，97 帧连续镜头，Text CFG 6 / Audio CFG 3 | 文本要求轻微举罐、保持托底接触和正面标签 |

C 每罐一次连续生成，没有上一轮 81 帧后重置参考照片的镜头内部接缝。模型提示轻微抬高商品，不等于已验证受控动作；需要看实际输出。

A 的有效生成时间包括脸部合成与写帧，音频特征单列；B 包含音频缓冲、模型推理、输出队列和帧转换；C 包含模型生成与写帧。有效 FPS 用实际保留帧数除以各自生成时间。B 的短音轨会受流式批次补齐影响，不能把本轮与上一轮长音轨的 FPS 差异直接归因为手持内容。

模型加载与准备另计：每个 SKU 单独启动推理进程，因此表中累计三次加载，不能看作一次常驻服务启动时间。输入图片生成、TTS、最终编码不计入数字人 FPS。原片分辨率不同，短样本不是长期实时性能测试；CUDA 峰值是 PyTorch allocated，不代表整机内存。

手持输入的 Qwen 加载为 211.77 秒；三张输入分别生成 14.06、12.79、12.70 秒，合计 39.54 秒，峰值约 39.38 GiB。

## 复现与保存位置

Spark：`/home/admin/digital-human-runtime`。本轮输入：`inputs/handheld`；每个 SKU 的原片与测量：`outputs/handheld_{A,B,C}_{original,diet,zero}`；各次推理日志：`logs/handheld_*.log`。模型、依赖及 ARM64/GB10 适配沿用 [上一轮运行记录](../11_coca_cola_avatar/runtime_receipt.json)，未安装新的候选项目或改动依赖版本。

将仓库 `scripts/04_test_benchmark/avatar_trials/` 中的 `prepare_handheld.py`、`run_handheld_suite.py`、更新的 `run_musetalk.py`、`run_flashhead.py`、`run_echomimic.py` 复制到该运行目录。商品 JPG 需从上一轮 `assets` 复制到 Spark 的 `inputs`。Qwen 图片和数字人模型使用各自的环境：

```bash
export PATH=/home/admin/.local/bin:$PATH
export PYTHONUNBUFFERED=1
/home/admin/qwen-image-2.1-runtime/venv/bin/python /home/admin/digital-human-runtime/prepare_handheld.py
/home/admin/digital-human-runtime/avatar-env/bin/python /home/admin/digital-human-runtime/run_handheld_suite.py
```

生成完成后同步输入和九个输出目录到本报告目录，在 Mac 执行：

```bash
python3 scripts/04_test_benchmark/avatar_trials/assemble_handheld.py
```

合成脚本输出三条 768×768 H.264/AAC 视频、每条输入与 0/1/2/3.8 秒帧对照图、汇总测量及对比页；检查九条原片与三条合成片的完整解码、帧数、时长、各 SKU 三路解码音轨一致性。手持姿势、口型和包装的验收为人工目视，没有运行 SyncNet、OCR 或身份识别评分。

完整动作的复现脚本为 `prepare_product_actions.py`、`run_product_actions_ltx.py`、`dub_product_actions.py` 和 `assemble_product_actions.py`。准备关键帧使用 Qwen 图片环境；缓存提示词与 LTX 生成使用已有 Stage 2 环境；口型处理使用数字人环境。三路按顺序运行，不能把缓存构建、素材生成或加载时间算入嘴部 FPS：

```bash
/home/admin/qwen-image-2.1-runtime/venv/bin/python /home/admin/digital-human-runtime/prepare_product_actions.py
# 仅复现本轮零度输入修正时执行：
/home/admin/qwen-image-2.1-runtime/venv/bin/python /home/admin/digital-human-runtime/prepare_product_actions.py --retry-zero
/home/admin/sol-spark-runtime/stage2-env/bin/python /home/admin/digital-human-runtime/run_product_actions_ltx.py cache
/home/admin/sol-spark-runtime/stage2-env/bin/python /home/admin/digital-human-runtime/run_product_actions_ltx.py generate
/home/admin/digital-human-runtime/avatar-env/bin/python /home/admin/digital-human-runtime/dub_product_actions.py
```

Spark 动作输入为 `inputs/product_actions`，动作原片为 `outputs/product_actions_ltx/{original,diet,zero}`，口播片为 `outputs/product_actions_dubbed/{original,diet,zero}`。同步到本报告 `actions/inputs`、`actions/motion`、`actions/dubbed` 后在 Mac 执行 `python3 scripts/04_test_benchmark/avatar_trials/assemble_product_actions.py`。

Spark 原有模型服务延续上一轮授权保持暂停；本轮各生成进程在运行结束后退出。

柔和配音更新使用 `prepare_soft_product_voice.py` 和 `normalize_product_voice.py`，在数字人环境生成 `inputs/product_actions_serena`；当前运行 `dub_product_actions.py --inputs /home/admin/digital-human-runtime/inputs/product_actions_serena --output /home/admin/digital-human-runtime/outputs/product_actions_dubbed_serena_smooth`，默认使用平滑过渡；`--transition-mode hard` 可复现旧固定窗口。`check_voice.py` 的 `--input`、`--output` 可指定新配音预览和 ASR 记录。同步新音轨和口播片后运行既有合成脚本，并运行 `check_product_lip_transitions.py` 生成修复对比与逐帧测量；原版声音和视频存档于 `actions/voices/vivian`。
