#!/usr/bin/env bash
set -Eeuo pipefail

# NVIDIA DGX Spark / GB10: download Qwen3.8-Flash-Next UD-IQ4_XS from ModelScope.
MODEL_DIR="${MODEL_DIR:-${HOME}/models_cache/Qwen3.8-Flash-Next-GGUF}"
REPO_ID="unsloth/Qwen3.8-Flash-Next-GGUF"
MAX_WORKERS="${MAX_WORKERS:-4}"
MODELSCOPE_BIN="${MODELSCOPE_BIN:-${HOME}/.local/bin/modelscope}"

if [[ ! -x "${MODELSCOPE_BIN}" ]]; then
    echo "ERROR: ModelScope CLI not found at ${MODELSCOPE_BIN}" >&2
    echo "Install it first: ~/.local/bin/uv tool install modelscope" >&2
    exit 1
fi

mkdir -p "${MODEL_DIR}"

echo "Downloading ${REPO_ID} with ModelScope"
echo "Destination: ${MODEL_DIR}"
echo "Files: UD-IQ4_XS shards + mmproj-BF16.gguf"

"${MODELSCOPE_BIN}" download "${REPO_ID}" \
    --include "UD-IQ4_XS/*" "mmproj-BF16.gguf" \
    --local-dir "${MODEL_DIR}" \
    --max-workers "${MAX_WORKERS}"

FIRST_SHARD="${MODEL_DIR}/UD-IQ4_XS/Qwen3.8-Flash-Next-UD-IQ4_XS-00001-of-00003.gguf"
MMPROJ="${MODEL_DIR}/mmproj-BF16.gguf"

for path in \
    "${FIRST_SHARD}" \
    "${MODEL_DIR}/UD-IQ4_XS/Qwen3.8-Flash-Next-UD-IQ4_XS-00002-of-00003.gguf" \
    "${MODEL_DIR}/UD-IQ4_XS/Qwen3.8-Flash-Next-UD-IQ4_XS-00003-of-00003.gguf" \
    "${MMPROJ}"; do
    if [[ ! -s "${path}" ]]; then
        echo "ERROR: missing or empty file: ${path}" >&2
        exit 1
    fi
done

echo "Download complete. First shard: ${FIRST_SHARD}"
du -sh "${MODEL_DIR}"
