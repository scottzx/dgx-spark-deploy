#!/usr/bin/env bash
set -Eeuo pipefail

# ==============================================================================
# NVIDIA DGX Spark / GB10: Qwen3.8-Flash-Next (177B MoE) 生产级常驻部署脚本
# 特性: 开机自启、崩溃自动重启 (restart: unless-stopped)、日志轮转、健康检查
# 优化: 启用 N-Gram 上下文投机解码 (Speculative Decoding)，大幅提升代码与长文生成速度
# ==============================================================================

IMAGE="${LLAMA_CPP_IMAGE:-ghcr.io/ggml-org/llama.cpp:server-cuda13}"
MODEL_DIR="${MODEL_DIR:-${HOME}/models_cache/Qwen3.8-Flash-Next-GGUF}"
MODEL_FIRST_SHARD="${MODEL_DIR}/UD-IQ4_XS/Qwen3.8-Flash-Next-UD-IQ4_XS-00001-of-00003.gguf"
MMPROJ="${MODEL_DIR}/mmproj-BF16.gguf"
CONTEXT_SIZE="${CONTEXT_SIZE:-786432}"
PARALLEL="${PARALLEL:-3}"
BATCH_SIZE="${BATCH_SIZE:-4096}"
UBATCH_SIZE="${UBATCH_SIZE:-2048}"
CACHE_REUSE="${CACHE_REUSE:-256}"
PORT="${PORT:-8000}"
CONTAINER_NAME="${CONTAINER_NAME:-qwen3-8-flash-next}"

# 投机解码参数配置 (N-Gram Prompt Lookup)
SPEC_TYPE="${SPEC_TYPE:-ngram-simple}"
SPEC_NGRAM_N="${SPEC_NGRAM_N:-6}"
SPEC_NGRAM_M="${SPEC_NGRAM_M:-24}"

for path in \
    "${MODEL_FIRST_SHARD}" \
    "${MODEL_DIR}/UD-IQ4_XS/Qwen3.8-Flash-Next-UD-IQ4_XS-00002-of-00003.gguf" \
    "${MODEL_DIR}/UD-IQ4_XS/Qwen3.8-Flash-Next-UD-IQ4_XS-00003-of-00003.gguf" \
    "${MMPROJ}"; do
    if [[ ! -s "${path}" ]]; then
        echo "ERROR: missing or empty model file: ${path}" >&2
        exit 1
    fi
done

docker image inspect "${IMAGE}" >/dev/null

# 停止并移除旧容器（无论当前处于何种状态）
docker rm -f "${CONTAINER_NAME}" 2>/dev/null || true

echo "=========================================================="
echo "启动生产级常驻服务: ${CONTAINER_NAME}"
echo "自动重启策略: unless-stopped (支持开机自启、崩溃自愈)"
echo "API 地址: http://0.0.0.0:${PORT}/v1"
echo "并发槽位: ${PARALLEL}, 上下文: ${CONTEXT_SIZE}, 启用 Vision mmproj"
echo "投机解码策略: ${SPEC_TYPE} (Lookup N=${SPEC_NGRAM_N}, Draft M=${SPEC_NGRAM_M})"
echo "=========================================================="

docker run -d \
    --name "${CONTAINER_NAME}" \
    --restart unless-stopped \
    --gpus all \
    --network host \
    --ipc host \
    --log-opt max-size=50m \
    --log-opt max-file=3 \
    --health-cmd "curl -f http://localhost:${PORT}/health || exit 1" \
    --health-interval 30s \
    --health-timeout 5s \
    --health-retries 3 \
    -v "${MODEL_DIR}:/models:ro" \
    -v "${SLOT_CACHE_DIR:-${HOME}/slot_cache}:/slots" \
    "${IMAGE}" \
    --model "/models/UD-IQ4_XS/Qwen3.8-Flash-Next-UD-IQ4_XS-00001-of-00003.gguf" \
    --mmproj "/models/mmproj-BF16.gguf" \
    --alias "Qwen3.8-Flash-Next-UD-IQ4_XS" \
    --host 0.0.0.0 \
    --port "${PORT}" \
    --slot-save-path "/slots" \
    --slots \
    --ctx-size "${CONTEXT_SIZE}" \
    --n-gpu-layers 999 \
    --batch-size "${BATCH_SIZE}" \
    --ubatch-size "${UBATCH_SIZE}" \
    --cache-reuse "${CACHE_REUSE}" \
    --flash-attn on \
    --cache-type-k q4_0 \
    --cache-type-v q4_0 \
    --parallel "${PARALLEL}" \
    --spec-type "${SPEC_TYPE}" \
    --spec-ngram-simple-size-n "${SPEC_NGRAM_N}" \
    --spec-ngram-simple-size-m "${SPEC_NGRAM_M}" \
    --spec-ngram-simple-min-hits 1

echo "等待服务初始化就绪..."
for i in {1..30}; do
    if curl -sf "http://127.0.0.1:${PORT}/health" >/dev/null 2>&1; then
        echo "=========================================================="
        echo "✅ Qwen3.8-Flash-Next 生产常驻服务已就绪并健康运行！"
        echo "=========================================================="
        docker ps --filter "name=${CONTAINER_NAME}"
        exit 0
    fi
    sleep 2
done

echo "⚠️ 服务仍在后台加载权重，可通过 'docker logs -f ${CONTAINER_NAME}' 查看实时进度。"
