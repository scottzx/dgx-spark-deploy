#!/usr/bin/env bash
# ==============================================================================
# NVIDIA DGX Spark - Qwen 3.8 27B 服务启动脚本
# 后端: llama-server (已开启 Blackwell 硬件加速)
# ==============================================================================

MODEL_PATH=$(find "${HOME}/models_cache/Qwen3.8-27B-GGUF" -name "*q8_0*.gguf" -o -name "*q4_k_m*.gguf" | head -n 1)

if [ -z "${MODEL_PATH}" ]; then
    echo "❌ 未找到 Qwen 3.8 27B 模型文件，请先执行 scripts/02_download_model/download_qwen3.8_27b.sh"
    exit 1
fi

echo "=========================================================="
echo "🚀 启动 Qwen 3.8 27B (OpenAI 兼容 API 服务)"
echo "模型路径: ${MODEL_PATH}"
echo "绑定地址: 0.0.0.0:8000"
echo "上下文窗口: 32768 (原生支持 262k，可按需调大)"
echo "CPU 线程数: 20 (Cortex-X925 / A725 核心)"
echo "=========================================================="

llama-server \
    -m "${MODEL_PATH}" \
    --host 0.0.0.0 \
    --port 8000 \
    -ngl 99 \
    -c 32768 \
    --threads 20 \
    --flash-attn
