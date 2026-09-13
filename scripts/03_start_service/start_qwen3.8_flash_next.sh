#!/usr/bin/env bash
set -Eeuo pipefail

# NVIDIA DGX Spark / GB10: OpenAI-compatible Qwen3.8-Flash-Next server.
MODEL_DIR="${MODEL_DIR:-${HOME}/models_cache/Qwen3.8-Flash-Next-GGUF}"
LLAMA_SERVER="${LLAMA_SERVER:-${HOME}/.local/bin/llama-server}"
MODEL="${MODEL_DIR}/UD-IQ4_XS/Qwen3.8-Flash-Next-UD-IQ4_XS-00001-of-00003.gguf"
MMPROJ="${MODEL_DIR}/mmproj-BF16.gguf"
HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-8000}"
CONTEXT_SIZE="${CONTEXT_SIZE:-16384}"
THREADS="${THREADS:-20}"

if [[ ! -x "${LLAMA_SERVER}" ]]; then
    echo "ERROR: llama-server not found at ${LLAMA_SERVER}" >&2
    exit 1
fi

for path in \
    "${MODEL}" \
    "${MODEL_DIR}/UD-IQ4_XS/Qwen3.8-Flash-Next-UD-IQ4_XS-00002-of-00003.gguf" \
    "${MODEL_DIR}/UD-IQ4_XS/Qwen3.8-Flash-Next-UD-IQ4_XS-00003-of-00003.gguf" \
    "${MMPROJ}"; do
    if [[ ! -s "${path}" ]]; then
        echo "ERROR: missing or empty model file: ${path}" >&2
        exit 1
    fi
done

echo "Starting Qwen3.8-Flash-Next UD-IQ4_XS"
echo "API: http://${HOST}:${PORT}/v1"
echo "Context: ${CONTEXT_SIZE}; vision enabled"

exec "${LLAMA_SERVER}" \
    --model "${MODEL}" \
    --mmproj "${MMPROJ}" \
    --alias "Qwen3.8-Flash-Next-UD-IQ4_XS" \
    --host "${HOST}" \
    --port "${PORT}" \
    --ctx-size "${CONTEXT_SIZE}" \
    --threads "${THREADS}" \
    --n-gpu-layers 999 \
    --flash-attn on \
    --cache-type-k q8_0 \
    --cache-type-v q8_0 \
    --parallel 1
