# NVIDIA DGX Spark Private Deployment Toolkit

**English** | [简体中文](README.md)

An end-to-end private deployment toolkit for Large Language Models and Multimodal Video Generation on the **NVIDIA DGX Spark (GB10 / 128GB Unified Memory / Ubuntu 24.04 aarch64)**.

- **LLM Inference**: Powered by **llama.cpp** with native Blackwell architecture (`sm_121a`) acceleration, serving GGUF quantized models via an OpenAI-compatible API (`0.0.0.0:8000`).
- **Video Generation**: Upgraded to the official NVIDIA **Sol-H3-Spark** pipeline (H3 diffusion draft denoising + LTX-2.5 latent refinement), delivering 1344×768 @ 24fps (121 frames, ~5 seconds) HD videos with synchronized audio in ~65 seconds end-to-end.
- **Session Cache Optimization**: NVMe-backed multi-slot FIFO KV cache persistence, root-anchor prefix hashing, and LCP rollback mitigation.
- **Batch Acceptance**: Validated through continuous multi-shot batch workloads with full-frame lossless decoding and contact sheet verification. See [Deployment Playbook](docs/deployments/Sol-H3-Spark部署.md).

Unified Model Cache Directory: `~/models_cache/`

---

## Directory Layout

Organized into sequential pipeline stages: `01_env_setup` → `02_download_model` → `03_start_service` → `04_test_benchmark`:

```text
dgx-spark-deploy/
├── README.md                  # Chinese documentation
├── README_EN.md               # English documentation (this file)
├── LICENSE                    # MIT License
├── scripts/
│   ├── 01_env_setup/          # Environment & dependency bootstrapping
│   ├── 02_download_model/     # Model weights acquisition & integrity checks
│   ├── 03_start_service/      # Service launchers (Docker/Native) & model switchers
│   └── 04_test_benchmark/     # Healthchecks, load tests & validation suites
├── docs/
│   ├── README.md              # Documentation index
│   ├── deployments/           # Technical manuals & architecture summaries
│   └── presentations/         # Technical reports & visual presentations (01 ~ 06)
└── .agents/skills/            # Agentic engineering skills (KV cache optimization)
```

---

## Script Catalog

### 01 Environment Setup
| Script | Description |
|---|---|
| `install_llama_cpp_gb10.sh` | Build llama.cpp from source with Blackwell (`sm_121a`) support into `~/.local/bin` |
| `pull_llama_cpp_docker.sh` | Pull official `ghcr.io/ggml-org/llama.cpp:server-cuda13` image with auto-retry |
| `prepare_sol_spark_assets.py` | Verify and download Sol-H3-Spark source assets and ModelScope weights with hash check |
| `manage_filebrowser.sh` | Manage the `filebrowser` web file manager daemon (`start`/`stop`/`restart`/`status`/`logs`) |

### 02 Model Acquisition
| Script | Model / Quantization |
|---|---|
| `download_deepseek_v4_flash.sh` | DeepSeek-V4-Flash `Q3_K_S` |
| `download_qwen3.8_27b.sh` | Qwen3.8-27B `Q8_0` (~29GB, quality-first) |
| `download_qwen3.8_flash_next.sh` | Qwen3.8-Flash-Next `UD-IQ4_XS` (177B MoE shards) |
| `download_minimax_h3.sh` | MiniMax-H3 Multimodal Video Model (ModelScope) |

### 03 Service Launchers & Model Switching
| Script | Model / Target | Mode |
|---|---|---|
| `start_server.sh` | DeepSeek-V4-Flash | Native llama-server |
| `start_qwen_server.sh` | Qwen3.8-27B | Native llama-server |
| `start_qwen3.8_flash_next.sh` | Qwen3.8-Flash-Next | Native (debugging) |
| `start_qwen3.8_27b_docker.sh` | Qwen3.8-27B | Docker container |
| `start_qwen3.8_flash_next_docker.sh` | Qwen3.8-Flash-Next | Production Docker (auto-restart, log rotation, healthcheck) |
| `session_fifo_proxy.py` | NVMe Multi-Slot KV Cache Proxy | Reverse proxy on `:8000` with FIFO slot persistence |
| `switch_to_minimax.sh` | Stop Qwen, execute Sol-H3-Spark video generation batch | Official CLI |
| `run_sol_h3_spark.sh` | Execute Sol-H3-Spark batch with concurrency protection | Official CLI |
| `switch_to_qwen.sh` | Stop MiniMax-H3, restore Qwen 3.8 Flash serving container | Docker (`:8000`) |
| `check_serving_status.sh` | Real-time query of active model, VRAM utilization & health | CLI Status |

### 04 Testing & Benchmarking
| Script | Description |
|---|---|
| `test_api.sh` | Verify `/health`, `/v1/models`, chat completions, and SSE stream |
| `benchmark_serving.py` | Load testing with concurrency gradient scanning (`1 2 4 8 16`) |
| `preflight_sol_h3_component.py` | Dry-run validation of Qwen prompt encoder and H3 denoiser workers |
| `verify_sol_h3_video.py` | Full-frame lossless MP4 decoding and automated 6-keyframe contact sheet generator |
| `run_pool_elbow_batch.py` | Multi-shot consecutive batch story generator (3 continuous shots) |

---

## Quick Start

```bash
# 1. Environment Setup (choose one)
bash scripts/01_env_setup/install_llama_cpp_gb10.sh   # Build from source
bash scripts/01_env_setup/pull_llama_cpp_docker.sh    # Or pull Docker image

# 2. Download Model Weights
bash scripts/02_download_model/download_qwen3.8_27b.sh

# 3. Start LLM Service
bash scripts/03_start_service/start_qwen3.8_27b_docker.sh

# 4. Validate and Run Benchmark
bash scripts/04_test_benchmark/test_api.sh
uv run --with aiohttp --with requests \
  scripts/04_test_benchmark/benchmark_serving.py \
  --concurrency 1 2 4 8 16 --max-tokens 512
```

---

## Mutual Exclusion: Switching Between Qwen and Sol-H3-Spark

NVIDIA GB10 features a unified memory pool of 128GB shared between CPU and GPU. To maximize throughput and avoid OOM, **Sol-H3-Spark (video generation)** and **Qwen 3.8 (LLM serving)** run under mutual exclusion:

```bash
# Check currently running service and VRAM footprint
bash scripts/03_start_service/check_serving_status.sh

# Switch to MiniMax Sol-H3-Spark for video batch generation
bash scripts/03_start_service/switch_to_minimax.sh \
  --prompt "A cute golden retriever playing in a sunny park with soft ripples on grass." \
  --output-dir /home/admin/sol-spark-runtime/outputs/dog_park_001

# Switch back to Qwen LLM serving once video generation completes
bash scripts/03_start_service/switch_to_qwen.sh
```

Environment variable overrides are supported: `MODEL_DIR`, `PORT`, `CONTEXT_SIZE`, `PARALLEL`, `LLAMA_CPP_IMAGE`.

---

## Local & Remote Synchronization

This repository follows a **Hub-and-Spoke** architecture using GitHub as the Single Source of Truth:

1. **Local Workstation (Mac)**: Develop scripts, author documentation, generate visual decks, and push to GitHub:
   ```bash
   git add .
   git commit -m "feat: updates"
   git push origin main
   ```
2. **DGX Spark Host**: Pull latest scripts via SSH Deploy Key in seconds:
   ```bash
   ssh admin@<spark-ip> "cd ~/dgx-spark-deploy && git pull"
   ```
3. Heavy models (`~/models_cache/`) and video outputs (`~/sol-spark-runtime/outputs/`) remain isolated on NVMe storage and are shielded by `.gitignore`.

---

## License

This project is licensed under the [MIT License](LICENSE).
