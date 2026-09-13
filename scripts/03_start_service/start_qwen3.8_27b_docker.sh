#!/usr/bin/env bash
set -Eeuo pipefail

IMAGE="${LLAMA_CPP_IMAGE:-ghcr.io/ggml-org/llama.cpp:server-cuda13}"
MODEL_DIR="${MODEL_DIR:-${HOME}/models_cache/Qwen3.8-27B-GGUF}"
MODEL="${MODEL_DIR}/Qwen3.8-27B-Q8_0.gguf"
MMPROJ="${MODEL_DIR}/mmproj-BF16.gguf"
CONTEXT_SIZE="${CONTEXT_SIZE:-32768}"
PARALLEL="${PARALLEL:-16}"
PORT="${PORT:-8000}"
CONTAINER_NAME="${CONTAINER_NAME:-qwen3-8-27b}"
DETACH="${DETACH:-false}"

for path in "${MODEL}" "${MMPROJ}"; do
    if [[ ! -s "${path}" ]]; then
        echo "ERROR: missing or empty model file: ${path}" >&2
        exit 1
    fi
done

docker image inspect "${IMAGE}" >/dev/null

# Clean up existing container if running
docker rm -f "${CONTAINER_NAME}" 2>/dev/null || true

RUN_MODE="-i"
if [[ "${DETACH}" == "true" ]]; then
    RUN_MODE="-d"
fi

echo "Starting ${CONTAINER_NAME} with parallel=${PARALLEL}, ctx=${CONTEXT_SIZE}..."

exec docker run --rm ${RUN_MODE} \
    --name "${CONTAINER_NAME}" \
    --gpus all \
    --network host \
    --ipc host \
    -v "${MODEL_DIR}:/models:ro" \
    "${IMAGE}" \
    --model "/models/$(basename "${MODEL}")" \
    --mmproj "/models/$(basename "${MMPROJ}")" \
    --alias "Qwen3.8-27B-Q8_0" \
    --host 0.0.0.0 \
    --port "${PORT}" \
    --ctx-size "${CONTEXT_SIZE}" \
    --n-gpu-layers 999 \
    --flash-attn on \
    --cache-type-k q8_0 \
    --cache-type-v q8_0 \
    --parallel "${PARALLEL}"
