#!/usr/bin/env bash
set -Eeuo pipefail

# ==============================================================================
# NVIDIA DGX Spark - Qwen 3.8 27B 自动化下载脚本
# 适配环境: Ubuntu 24.04 LTS (aarch64) / 128GB Unified Memory
# ==============================================================================

TARGET_DIR="${MODEL_DIR:-${HOME}/models_cache/Qwen3.8-27B-GGUF}"
REPO_ID="unsloth/Qwen3.8-27B-GGUF"
MODELSCOPE_BIN="${MODELSCOPE_BIN:-${HOME}/.local/bin/modelscope}"
MAX_WORKERS="${MAX_WORKERS:-4}"

# Q8_0 is approximately 29 GB and is the quality-first 27B test target.
MODEL_FILE="Qwen3.8-27B-Q8_0.gguf"

echo "=========================================================="
echo "1. 创建高速 NVMe 存储路径"
echo "=========================================================="
mkdir -p "${TARGET_DIR}"
echo "=========================================================="
echo "2. 开始从 ModelScope 下载 Qwen 3.8 27B Q8_0 + mmproj"
echo "=========================================================="
"${MODELSCOPE_BIN}" download "${REPO_ID}" \
    --include "${MODEL_FILE}" "mmproj-BF16.gguf" \
    --local-dir "${TARGET_DIR}" \
    --max-workers "${MAX_WORKERS}"

for path in "${TARGET_DIR}/${MODEL_FILE}" "${TARGET_DIR}/mmproj-BF16.gguf"; do
    if [[ ! -s "${path}" ]]; then
        echo "ERROR: missing or empty file: ${path}" >&2
        exit 1
    fi
done

echo "=========================================================="
echo "✅ Qwen 3.8 27B 下载完成！"
echo "文件位置: ${TARGET_DIR}"
echo "=========================================================="
ls -lh "${TARGET_DIR}"
