#!/usr/bin/env bash
# ==============================================================================
# NVIDIA DGX Spark - DeepSeek-V4-Flash Q3_K_S 服务启动脚本
# 推荐后端: llama-server (基于 Blackwell sm_121a 编译)
# ==============================================================================

MODEL_PATH=$(find "${HOME}/models_cache/DeepSeek-V4-Flash-GGUF" -name "*Q3_K_S*.gguf" | head -n 1)

if [ -z "${MODEL_PATH}" ]; then
    echo "❌ 未找到 Q3_K_S 模型文件，请先运行 scripts/02_download_model/download_deepseek_v4_flash.sh"
    exit 1
fi

echo "=========================================================="
echo "🚀 启动 DeepSeek-V4-Flash Q3_K_S (OpenAI 兼容 API 服务)"
echo "模型路径: ${MODEL_PATH}"
echo "绑定端口: 8000 (0.0.0.0)"
echo "上下文长度: 32768 (可根据需求提升至 64k/128k)"
echo "CPU 线程数: 20 (全速调动 Cortex-X925 / A725 核心)"
echo "=========================================================="

llama-server \
    -m "${MODEL_PATH}" \
    --host 0.0.0.0 \
    --port 8000 \
    -ngl 99 \
    -c 32768 \
    --mmap \
    --threads 20 \
    --flash-attn \
    --mlock-none
