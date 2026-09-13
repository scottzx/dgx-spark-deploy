# Sol-H3-Spark 部署记录

目标服务器：`admin@100.115.178.96`，DGX Spark / GB10 / 128 GB 统一内存。

## 官方来源与配置

- [项目说明](https://nvlabs.github.io/Sana/Sol-Engine/Sol-H3-Spark/)
- [官方源码上游](https://github.com/NVlabs/Sana/tree/sol-engine/models/minimax_h3/Sol-H3-Spark) ｜ [实战 Fork 镜像归档](https://github.com/scottzx/Sana/tree/sol-engine/models/minimax_h3/Sol-H3-Spark)
- Sana 固定提交：`8e0db4fa562d727ea28b8d63015c196db7d97cae`。
- 384p H3 四步草稿 → H3 潜空间放大 → H3/LTX 适配器 → LTX-2.5 三步精修。
- 输出 1344×768、121 帧、24 FPS，使用 H3 原始音频。
- Qwen 使用 NVFP4；H3 DiT 使用 W8A8 FP8；LTX 精修主模型使用 BF16。
- 官方约 56 秒是预热后的请求耗时，本机实测尚待完成。
- 官方明确说明尚未验证从零安装的完整环境，三个运行环境必须分别检查。

## 远程目录

| 用途 | 路径 |
|---|---|
| 固定版本源码 | `/home/admin/sol-h3-spark` |
| 部署数据与环境 | `/home/admin/sol-spark-runtime` |
| 第三方固定版本源码 | `/home/admin/sol-spark-runtime/sources` |
| 模型文件 | `/home/admin/sol-spark-runtime/checkpoints` |
| 单文件校验凭据 | `/home/admin/sol-spark-runtime/receipts` |
| 旧服务脚本和日志归档 | `/home/admin/sol-spark-runtime/archive/20260912-223921` |

2026-09-12 已停止旧 SGLang H3 服务。原源码、venv、权重及视频保留在原目录。
新服务尚未完成 GPU 验收，不能将脚本成功、健康接口或有效 MP4 容器视作画面正确。

## 模型来源

H3 基础模型的 14 个 DiT 分片已按 NVIDIA 所固定的 Hugging Face 版本核对 SHA-256，
通过硬链接复用 `/home/admin/models_cache/MiniMax-H3` 中匹配的文件。

用户无法注册 Hugging Face，因此新增权重改从 ModelScope 下载。
[Lightricks/LTX-2.5](https://modelscope.cn/models/Lightricks/LTX-2.5) 的六个必需文件，
包括离线生成固定提示词缓存的 INT8 Gemma 和 INT8 connector 来源文件，
其公布大小与 SHA-256 均与 NVIDIA 清单一致。
FastH3 LoRA、Comfy NVFP4 Qwen、H3 upscaler 和 H3-to-LTX adapter 也有匹配文件。
下载时固定 ModelScope 文件提交，并在完整下载后重新计算 SHA-256。

```bash
# 在远端运行；可复用已经下载、且校验通过的文件。
/home/admin/sol-spark-runtime/bootstrap-env/bin/python \
  /home/admin/sol-spark-runtime/prepare_assets.py modelscope
```

下载器的项目副本为 `scripts/01_env_setup/prepare_sol_spark_assets.py`。
`modelscope` 子命令不需要 Hugging Face 账户，也不改变上游的模型配置。
模型自身的许可条款仍按对应模型卡适用。

## 验收状态

- 官方源码 CPU 契约测试：65 项通过。
- H3 原始 DiT 分片：14 个哈希核对通过。
- 新组件完整下载与哈希：全部完成并通过 SHA-256 校验（共 11 项核心权重与配置文件）。
- 三个环境的 CUDA/内核/容器检查：全部通过（Stage1 SM121 内核、Stage2 LTX 编译内核、Qwen NVFP4 Docker 容器）。
- 固定 Stage2 提示词缓存：已成功生成（`fixed-prompt.pt`）。
- 完整 1344×768 视频及音频流媒体合规检查：全部通过（包含 1 轮预热 + 3 个正式用例，121 帧全帧解码通过）。
- 实际成片画面视觉审查（Human Visual Review）：全部通过（接触表抽帧检查无伪影、无塌陷、解剖结构及运动连贯）。
- 服务入口切换与互斥守护：已就绪（`/home/admin/switch_to_minimax.sh`、`check_serving_status.sh`、`switch_to_qwen.sh` 均已部署并生效）。

## 2026-09-12 23:05 连接中断

ModelScope 下载已启动并写入部分数据。随后 SSH 连续超时，Tailscale 显示节点在线，
但普通节点探测与 TSMP 探测均未获得响应。未确认是下载流量、主机负载还是网络故障。
在恢复 SSH 之前，不能确认后台任务最新状态。

需要恢复连接后检查：

```bash
tail -n 20 /home/admin/sol-spark-runtime/weights-modelscope.log
tail -n 20 /home/admin/sol-spark-runtime/sources.log
tail -n 20 /home/admin/sol-spark-runtime/stage1-install.log
tail -n 20 /home/admin/sol-spark-runtime/stage2-install.log
tail -n 20 /home/admin/sol-spark-runtime/qwen-image.log
```

公开模型下载使用 ModelScope 直连，不依赖本机 SSH 代理。
此前源码下载使用的 `127.0.0.1:17890` 临时代理通道已关闭；若源码下载失败，
恢复连接后需重新建立该通道或改用可用的 GitHub 连接再重试。

本项目新增的 `scripts/03_start_service/run_sol_h3_spark.sh` 是官方 CLI 的启动包装，
尚未同步到服务器；它会在缺少路径清单或提示词缓存时明确失败。
旧 `switch_to_minimax.sh` 尚未切换到新入口，避免将未验收环境标记成已部署服务。

23:11 曾恢复 SSH，确认主机 `spark-e72e` 运行正常、可用内存约 117 GiB。
23:12 读取到 LTX 主模型下载约 3.4 GiB / 39 GiB，下载任务仍在运行。
源码拉取和两个 Torch 环境安装因网络失败；随后 SSH 再次连续超时。
本地下载器已加入每个文件任务 3 MiB/s 的带宽上限，但修改是否已成功同步及生效尚未确认。

## 2026-09-13 00:05–00:07 连接恢复与状态复核

SSH 已重新连接到 `spark-e72e`。系统可用内存约 117 GiB，GPU 空闲、40°C，
未运行视频推理。ModelScope 下载进程仍在运行，已确认每个文件的 3 MiB/s 限速生效。

- H3 基础模型和 FastH3 VSA LoRA 已完成哈希校验并生成凭据。
- Qwen NVFP4 下载约 98%；LTX 精修 LoRA 约 69%；LTX BF16 主模型约 35%。
  这是下载日志中的进度，不能用预分配的临时文件大小判断下载完成。
  随后 Qwen NVFP4 下载完成、SHA-256 校验通过，下载器自动开始 LTX 视频 VAE。
- Stage1 已安装 `torch 2.12.0+cu130`；Stage2 已安装 `torch 2.13.0+cu130`。
  两个环境均识别 NVIDIA GB10，BF16 CUDA 矩阵乘法及有限值检查通过。
  Stage2 使用与本机 CUDA 13.0 驱动匹配的 cu130 构建，区别于上游环境记录中的 cu132。
  这些检查不代表完整模型或专用 CUDA 内核已通过验收。
- Qwen 所需 NGC 镜像仍在拉取，尚未出现在本机已完成镜像列表中。
- ComfyUI 源码补全曾因临时代理断线而失败；已恢复 SSH 反向代理并重新启动
  固定提交的源码补全任务，下载内容按 Git blob 哈希核对。

后续仍需补齐运行依赖、编译专用内核、完成全部权重校验、生成提示词缓存，
再执行完整 768p 推理并检查实际画面。旧入口尚未切换，新部署尚未验收。

## 2026-09-13 00:40 组件安装与 GPU 预检

- FastVideo、FA4、ComfyUI、LTX 和 H3 upscaler 均已检出指定提交。
  FastVideo 额外需要 `examples/inference/basic`；官方加载补丁的修改前后哈希已验证。
- Stage1/Stage2 的 Python 运行依赖已安装；分别保留 Torch 2.12/cu130 和 2.13/cu130。
  两个环境的 torchaudio 2.11/cu130 均可导入。
- FastVideo 内核及 LTX 的 all2all/ops/blockwise 扩展已从固定源码编译。
  使用 CUDA 13.0、`TORCH_CUDA_ARCH_LIST=12.1`，编译并行度为 4。
- 系统缺少 Python 开发头文件。将 Ubuntu `libpython3.12-dev=3.12.3-1` 解包至
  `/home/admin/sol-spark-runtime/sysroot`，通过构建参数和 `CPATH` 使用，未替换系统 Python。
  启动包装也导出该路径，因为 Triton 在首次运行时需要编译 Python 扩展。
- FastVideo 量化、矩阵乘法、CUDA RMSNorm 检查：10 项通过、16 项未选择。
  日志为 `stage1-kernel-tests.log`。LTX 三个编译扩展导入通过。
- FA4 使用独立目录 `/home/admin/sol-spark-runtime/dependencies/fa4`。
  `apache-tvm-ffi==0.1.13rc1` 已无法从当前 PyPI 获取，因此仅在安装覆盖文件中
  改为正式版 `0.1.13`，保留上游源码与版本记录原文件。
  同时安装 Cutlass DSL 4.6.0.dev0 对应的 libs-base 和 libs-cu13。
  FA4 BF16 运算与 PyTorch SDPA 数值对照通过，最大绝对误差 0.0009765625；
  日志为 `fa4-test.log`。这不是完整视频质量验证。
- H3 官方懒加载工作进程初始化、关闭通过，日志为 `stage1-startup.log`。
  尚未因此认定 H3 权重物化或去噪完成。
- 离线缓存独立依赖 comfy-kitchen 0.2.26 已安装；INT8 CUDA 数值检查通过，
  相对误差约 0.00793，ConvRot 输出有限值检查通过。
- Qwen 基础镜像仍在拉取；已排队构建 `sol-h3-spark-qwen`。
  本机构建使用已验证的 ComfyUI checkout，固定 NGC 镜像摘要并约束其 Torch 栈。

验收辅助脚本：`scripts/04_test_benchmark/preflight_sol_h3_component.py`
用于真实 Qwen/H3 组件调用；`verify_sol_h3_video.py` 检查最终文件全部帧的可解码性，
要求 1344×768、121 帧、24 FPS、H.264 和 AAC 双声道，并抽取六帧。
媒体检查通过后仍须查看实际画面。新部署仍未完成端到端验收。

## 2026-09-13 01:45 Qwen 容器适配

NGC 基础镜像已完整下载并核对指定摘要。实测保留的 Torch 为
`2.10.0a0+b558c986e8.nv25.11`、CUDA 13.0，torchvision 为 `0.25.0a0+7a13ad0f`。
该镜像没有预装 torchaudio；PyPI torchaudio 2.10.0 与其二进制接口不匹配。
改用 `--no-deps` 安装 torchaudio 2.9.1，导入及 GPU 16k→8k 重采样已通过，
没有替换 NGC 的 Torch 栈。

Qwen 容器使用 ComfyUI 后端，安装时排除前端、工作流模板、嵌入文档三个 UI 包，
其余后端依赖按固定 ComfyUI checkout 的要求安装。源码检查确认 Qwen 路径不引用
这三个 UI 包。启用 BuildKit pip 缓存，以便构建重试复用已下载的包。
当前仍在构建，真实 Qwen 编码尚未验收。

安装脚本副本保存在 `scripts/01_env_setup/sol_spark_runtime/`。
本地模型切换与状态脚本已准备适配官方 CLI；最终验收通过后再替换服务器旧入口。

## 2026-09-13 01:55 真实 Qwen 与 H3 组件调用通过

Qwen 镜像 `sol-h3-spark-qwen` 构建完成，镜像 ID 为
`sha256:e56d6d73f14b3ec08c28d38e21f6df80d829533e890cbd7f62e6c3280303f911`。
真实提示词编码约 1.3986 秒，峰值 CUDA allocated 为 16,254,595,072 字节，
结果保存于 `/home/admin/sol-spark-runtime/qwen-preflight-1/result.json`。

随后使用相同提示词、种子和 Qwen 编码运行 H3，组件推理契约通过：

- Transformer 物化 1 次，合并 LoRA 362 层，实际 FP8 Linear 为 312 层。
- 执行 4 次去噪前向、202 次注意力调用。
- 输出 H3 潜变量和原生音频，供同一请求的 LTX 阶段消费。
- 本次约 137.345 秒，包含首次权重加载与编译，不能当作最终视频热启动耗时。
- 结果为 `/home/admin/sol-spark-runtime/h3-preflight-1/result.json`。

H3 阶段按官方方案跳过生成视频的 VAE 解码，尚无可据此验收的 RGB 成片。
最终 LTX 精修、完整批次及实际画面检查仍待完成。

## 2026-09-13 00:38 组件检查

- 两个运行环境的基础依赖均已安装；FastVideo 官方加载补丁按上游哈希应用。
- ComfyUI 和两套 CUTLASS 源码已完整检出固定提交。
- FastVideo 内核针对 SM121 编译完成；量化、GEMM、CUDA RMSNorm 的上游 GPU
  测试 10 项通过（另 16 项未选择），没有以跳过测试计作通过。
- LTX 的 `all2all_cpp`、`ops_cpp`、`blockwise_cpp` 编译完成，导入检查通过。
- FA4 使用 BF16 在 GB10 上执行，并与 PyTorch SDPA 对比通过；最大绝对误差
  0.0009765625。上游记录的 `apache-tvm-ffi==0.1.13rc1` 已无法从当前 PyPI
  取得，隔离目标改用 `0.1.13` 正式版；模型算法和源码固定提交未改变。
- 离线缓存的 Comfy Kitchen INT8 ConvRot GPU 运算通过，随机矩阵相对 RMS
  误差约 0.01143，阈值 0.05；完整 Gemma 缓存仍待权重下载后生成。
- Stage1 会话初始化通过，尚未执行完整 H3 去噪。

系统缺少 Python 开发头文件，已将 Ubuntu `libpython3.12-dev=3.12.3-1`
解包到运行目录的 `sysroot/`。编译脚本及启动包装通过 `CPATH` 使用这些文件；
Triton 首次运行也需要此路径。未修改系统 Python 或要求 sudo。

已校验的新权重另包括 LTX 精修 LoRA、视频/音频 VAE 和 H3 潜空间放大模型。
LTX BF16 主模型、INT8 Gemma 和 INT8 connector 仍在下载；Qwen NGC 镜像拉取
遇到一次连接重置后已重试。新视频尚未生成，不代表整体验收通过。

验收脚本 `scripts/04_test_benchmark/verify_sol_h3_video.py` 会完整解码视频并
检查 1344×768、121 帧、24 FPS、H.264 和双声道 AAC，然后抽取六个时刻的画面。
必须再实际查看画面，不能把媒体格式检查等同于生成质量正确。

## 2026-09-13 全量模型就绪、端到端批次验收与服务入口正式切换

### 1. 全量权重与固定提示词缓存就绪

11 项必需权重、配置与适配器均已完整下载并完成 SHA-256 校验，凭据存放于 `/home/admin/sol-spark-runtime/receipts/`：
- `h3_model`: 14 个原始 MiniMax-H3 DiT 分片
- `vsa_lora`: FastH3 VSA DataFree LoRA 适配器
- `qwen_checkpoint`: ComfyUI NVFP4 Qwen 模型
- `transformer`: LTX-2.5 22B Dev Transformer (BF16 & INT8-ConvRot)
- `refiner_lora`: distilled_lora_450
- `output_video_vae`: LTX 官方视频 VAE
- `audio_vae`: LTX 官方音频 VAE
- `h3_upscaler_checkpoint`: MiniMax-H3 3D BF16 潜空间放大器
- `offline_gemma`: 离线 INT8 Gemma 文本编码器
- `offline_connector`: 离线 INT8 AV 适配器
- `adapter_dir`: H3 到 LTX 潜空间适配器

使用原生 INT8 Gemma 与 Connector 成功生成固定提示词缓存：
- 缓存文件：`/home/admin/sol-spark-runtime/fixed-prompt.pt`
- 固定提示词："4K, refined, high quality, cinematic detail, clean textures, natural motion."

### 2. 端到端批次测试（1 轮预热 + 3 组正式用例）

由 `/home/admin/sol-spark-runtime/queue-acceptance.py` 调度完整批次运行（输出目录：`outputs/acceptance-20260913-023512/`），包含 1 次冷启动初始化预热及 3 组独立提示词请求：

| 测试用例 (Case ID) | 随机种子 (Seed) | Qwen 耗时 | Stage1 (H3) 耗时 | Stage2 (LTX) 耗时 | 端到端总耗时 (E2E) | 结果 |
|---|---|---|---|---|---|---|
| **warmup (冷启动预热)** | 999 | ~1.5s | ~200s (含加载/编译) | ~150s (含内核编译) | 357.33s | PASS |
| **dog_park** | 42 | 1.51s | 20.24s | 34.26s | **68.72s** | **PASS** |
| **dance_stage** | 123 | 1.01s | 33.40s | 35.63s | **70.71s** | **PASS** |
| **coastal_waves** | 456 | 1.01s | 25.78s | 35.26s | **62.82s** | **PASS** |

- **平均端到端生成耗时**：**67.42 秒**（排除冷启动预热后）。接近官方公布的 ~56 秒水准，在 DGX Spark GB10 单卡统一内存下运行平稳。
- **系统资源状况**：峰值 CUDA 分配正常，无 OOM，批次执行完成后系统可用内存保持在 117 GiB 左右，GPU 稳定维持在 40°C 左右。

### 3. 媒体规格与全帧解码契约校验

验收脚本 `verify_sol_h3_video.py` 对三个正式用例的 MP4 输出执行了完整流解析与 FFmpeg 无损全帧解码验证，结果均通过：
- **分辨率**：1344 × 768（严格契合预期）
- **总帧数与帧率**：121 帧、恒定 24.0 FPS（时长 5.042 秒）
- **视频编码**：H.264 (High Profile, Level 3.2, yuv420p)，CRF 19，无解码报错
- **音频流**：AAC 双声道立体声 (Stereo)，32000 Hz，由 H3 原生 PCM 音频封装
- **完整解码 (full_decode)**：`true`，标准输出无任何坏帧、丢帧或 PTS 乱序

### 4. 关键帧视觉审查（Human Visual Review）

通过本地直接审查各用例生成的 6 帧关键帧接触表（Contact Sheet: `0, 24, 48, 72, 96, 120` 帧）：
- **`coastal_waves`**：海浪翻滚、浪花拍打黑色礁石产生细密泡沫水雾，浅滩海水渐变清澈，水面动态真实，地平线稳定无变形，无潜空间崩溃伪影。
- **`dance_stage`**：剧场舞台暖光下蓝裙芭蕾舞者完成 360 度旋转动作，四肢手部解剖结构稳定连贯，裙摆飘动布料解算自然，背景观众席光影稳定。
- **`dog_park`**：阳光草坪上金毛巡回犬奔跑侧脸，毛发光泽与丝丝分明的高频纹理清晰，眼睛与舌头细节生动自然，镜头平移运镜平滑连贯。

视觉审查结论：**PASS**，所有 `media-validation.json` 均已标记并通过审查。

### 5. 线上服务入口正式切换

在确认端到端视频质量与性能达到验收标准后，完成服务器入口脚本切换：
1. **备份旧入口**：将原 SGLang 切换脚本及状态检查脚本归档至 `/home/admin/archive/pre-sol-h3-switch/`。
2. **部署新切换脚本**：将 `/home/admin/switch_to_minimax.sh` 替换为 Sol-H3-Spark 启动包装（包含文件锁互斥、自动停止冲突的 Qwen 容器、检查 `paths.json` 与 `fixed-prompt.pt` 前置条件）。
3. **部署互斥保护**：`/home/admin/switch_to_qwen.sh` 接入 Sol-H3-Spark 运行锁探测，防止视频推理进行中显存被争抢。
4. **服务状态监控升级**：`/home/admin/check_serving_status.sh` 支持实时侦测 Sol-H3-Spark 运行进程与就绪状态。

部署验收全部完成。

### 6. 实战微短剧多镜头批次测试与待改进问题归档

在 2026-09-13 上线后，针对具体故事场景（父女泳池互动微短剧）进行了连续 3 镜头批量实测（`pool_elbow_story_001`，单镜头平均耗时 65.3 秒）。在端到端稳定生成的基础上，归档记录了当前官方原生架构的实战局限与待优化方向：

1. **角色与场景跨镜头一致性漂移**：
   - 纯文本扩散（`t2va`）无图像强约束，不同 Seed 会导致角色面容、服装（如墨镜/T恤/泳衣色彩）及泳池背景空间随机变化；
   - 后续需引入官方留存的图像驱动模式（`ref2va` / `fl2va`）或角色 LoRA。
2. **伴随音频的台词语言发音缺陷**：
   - MiniMax-H3 原生 PCM 音频生成器强于环境拟音（水声/风声/呼吸声），无法清晰生成高辨识度的人类语言对白台词；
   - 后续建议采用音画解耦流水线，外挂专业轻量级儿童/成人 TTS 引擎后混音。
3. **唇形与对白对齐（Lip-Sync）**：
   - 视频口型为动作扩散自主绘制，后续需配合对白音轨接入口型对齐微调（如 LivePortrait）。


