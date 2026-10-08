# DGX Spark 模型私有化部署

[English](README_EN.md) | **简体中文**

在 **NVIDIA DGX Spark (GB10 / 128GB 统一内存 / Ubuntu 24.04 aarch64)** 上，
基于 **llama.cpp** 部署 GGUF 量化模型，对外提供 OpenAI 兼容 API（默认 `0.0.0.0:8000`）。

视频生成已成功升级至 NVIDIA 官方 **Sol-H3-Spark**（源码基于 [scottzx/Sana:sol-engine](https://github.com/scottzx/Sana/tree/sol-engine/models/minimax_h3/Sol-H3-Spark)，官方上游 [NVlabs/Sana](https://github.com/NVlabs/Sana)）：H3 草稿经 LTX-2.5 精修，
输出 1344×768、121 帧（约 5 秒）的高清带声视频，端到端单视频生成仅约 67 秒。
已通过全流程批次测试与关键帧画质验收，详见 [部署记录](docs/deployments/Sol-H3-Spark部署.md)。

模型统一缓存目录：`~/models_cache/`

## 目录结构

按「装环境 → 下模型 → 起服务 → 测性能」流水线编号：

```
scripts/
├── 01_env_setup/          环境准备
├── 02_download_model/     模型下载
├── 03_start_service/      服务启动（native / docker）
└── 04_test_benchmark/     连通性测试与压测
docs/                      部署文档与实战总结
```

## 脚本清单

### 01 环境准备
| 脚本 | 说明 |
|---|---|
| `install_llama_cpp_gb10.sh` | 从源码编译 llama.cpp，启用 Blackwell (sm_121a) 加速，装到 `~/.local/bin` |
| `pull_llama_cpp_docker.sh` | 拉取官方镜像 `ghcr.io/ggml-org/llama.cpp:server-cuda13`（带重试） |
| `prepare_sol_spark_assets.py` | Sol-H3-Spark 固定源码与 ModelScope 权重下载、哈希校验 |
| `install_qwen_image_21.sh` | Qwen-Image-2.1 独立环境、固定源码与官方权重安装 |
| `manage_filebrowser.sh` | FileBrowser 远端文件管理器守护进程管理（启动 / 停止 / 重启 / 状态 / 日志） |

### 02 模型下载
| 脚本 | 模型 / 量化 |
|---|---|
| `download_deepseek_v4_flash.sh` | DeepSeek-V4-Flash `Q3_K_S` |
| `download_qwen3.8_27b.sh` | Qwen3.8-27B `Q8_0`（约 29GB，质量优先） |
| `download_qwen3.8_flash_next.sh` | Qwen3.8-Flash-Next `UD-IQ4_XS`（177B MoE，分片） |
| `download_minimax_h3.sh` | MiniMax-H3 全量多模态视频模型（ModelScope） |
| `download_qwen_image_21.py` | Qwen-Image-2.1 官方 BF16 权重分段续传与 SHA-256 校验 |
| `verify_qwen_image_21.py` | 按官方文件清单校验图像模型并生成凭据 |

### 03 服务启动与模型切换
| 脚本 | 模型 / 功能 | 方式 |
|---|---|---|
| `start_server.sh` | DeepSeek-V4-Flash | native llama-server |
| `start_qwen_server.sh` | Qwen3.8-27B | native llama-server |
| `start_qwen3.8_flash_next.sh` | Qwen3.8-Flash-Next | native（调试用） |
| `start_qwen3.8_27b_docker.sh` | Qwen3.8-27B | Docker |
| `start_qwen3.8_flash_next_docker.sh` | Qwen3.8-Flash-Next | Docker 生产级（开机自启 / 崩溃重启 / 日志轮转 / 健康检查） |
| `session_fifo_proxy.py` | NVMe 多槽位 KV Cache 持久化代理 | `:8000` 端口反向代理与 FIFO 淘汰持久化 |
| `switch_to_minimax.sh` | 停止 Qwen，执行 Sol-H3-Spark 视频批次 | 官方 CLI（已验收上线） |
| `run_sol_h3_spark.sh` | 执行 Sol-H3-Spark，检查输入清单并限制同时运行一个批次 | 官方 CLI |
| `run_qwen_image_21.sh` / `generate_qwen_image_21.py` | 生成角色、场景、透明 PNG 与参考图编辑；[部署说明](docs/deployments/Qwen-Image-2.1部署.md) | 独立 Diffusers CLI |
| `switch_to_qwen.sh` | 切换至 Qwen 3.8 Flash（停止 MiniMax，启动 Qwen 容器） | Docker (`:8000`) |
| `check_serving_status.sh` | 实时查看当前活跃模型、显存与健康状态 | 状态检测 |

### 04 测试与压测
| 脚本 | 说明 |
|---|---|
| `test_api.sh` | 校验 `/health`、`/v1/models`、对话与流式输出 |
| `benchmark_serving.py` | 吞吐压测，支持并发梯度扫描 |
| `preflight_sol_h3_component.py` | 单独检查官方 Qwen 编码和 H3 去噪工作进程 |
| `verify_sol_h3_video.py` | 最终视频格式、全部帧解码检查及抽帧；画面需另行查看 |
| `test_qwen_image_21.sh` | 实测场景、透明道具与参考图编辑；可临时暂停空闲语言模型并在结束后恢复 |
| `test_qwen_image_21_speed.sh` / `benchmark_qwen_image_21.py` | 六步 Turbo 与原版的连续出图对照；[加速实测](docs/deployments/Qwen-Image-2.1加速实测.md) |
| `test_qwen_image_21_sglang.py` / `benchmark_qwen_image_21_http.py` | 独立 SGLang 原生服务的同素材 HTTP 性能与透明通道测试 |
| `benchmark_qwen_image_21_composition.py` | 五角色与三背景的六参考图合成对照；[实测](docs/deployments/Qwen-Image-2.1多角色合成实测.md) |
| `run_pool_elbow_batch.py` | 三镜头连续微短剧多任务批次生成 |
| `run_chained_cow_story.py` | 四镜头 20 秒链式连贯微短剧生成（首尾帧衔接 + TTS 对齐混流 + 母带拼接） |

## 快速开始

```bash
# 1. 准备环境（二选一）
bash scripts/01_env_setup/install_llama_cpp_gb10.sh   # 源码编译
bash scripts/01_env_setup/pull_llama_cpp_docker.sh    # 或拉取 Docker 镜像

# 2. 下载模型
bash scripts/02_download_model/download_qwen3.8_27b.sh

# 3. 启动服务
bash scripts/03_start_service/start_qwen3.8_27b_docker.sh

# 4. 验证与压测
bash scripts/04_test_benchmark/test_api.sh
uv run --with aiohttp --with requests \
  scripts/04_test_benchmark/benchmark_serving.py \
  --concurrency 1 2 4 8 16 --max-tokens 512
```

## MiniMax-H3 与 Qwen 3.8 Flash 互斥切换

NVIDIA GB10 的 CPU 与 GPU 共享 128GB 内存。Sol-H3-Spark 和 Qwen 3.8 Flash
应互斥运行。视频批次会在前台执行，同一批次复用模型，结束后释放资源。
原 SGLang `:30010` 服务已停止，官方 Sol-H3-Spark 使用命令行入口。

```bash
# 查看当前正在运行哪个模型
bash check_serving_status.sh

# 切换并执行 Sol-H3-Spark 视频生成；输出目录必须尚不存在
bash switch_to_minimax.sh --prompt "A dog walks through a sunny park." \
  --output-dir /home/admin/sol-spark-runtime/outputs/dog-001

# 视频批次结束后切换回 Qwen；批次运行中会拒绝切换
bash switch_to_qwen.sh
```

多数参数支持环境变量覆盖：`MODEL_DIR`、`PORT`、`CONTEXT_SIZE`、`PARALLEL`、`LLAMA_CPP_IMAGE` 等。

## 开源协议

本项目采用 [MIT License](LICENSE) 开源协议。
