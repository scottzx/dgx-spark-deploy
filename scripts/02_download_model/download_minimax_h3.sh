#!/usr/bin/env bash
set -Eeuo pipefail

# ==============================================================================
# NVIDIA DGX Spark / GB10: MiniMax-H3 全量模型下载脚本
# 模型源: ModelScope (MiniMax/MiniMax-H3)
# 存储目录: ~/models_cache/MiniMax-H3
# ==============================================================================

MODEL_DIR="${MODEL_DIR:-${HOME}/models_cache/MiniMax-H3}"
REPO_ID="MiniMax/MiniMax-H3"
MAX_WORKERS="${MAX_WORKERS:-8}"
MODELSCOPE_BIN="${MODELSCOPE_BIN:-${HOME}/.local/bin/modelscope}"

if [[ ! -x "${MODELSCOPE_BIN}" ]]; then
    echo "ERROR: ModelScope CLI not found at ${MODELSCOPE_BIN}" >&2
    exit 1
fi

mkdir -p "${MODEL_DIR}"
mkdir -p "${HOME}/h3-lightning/models"
ln -sfn "${MODEL_DIR}" "${HOME}/h3-lightning/models/MiniMax-H3"

echo "=========================================================="
echo "开始从 ModelScope 下载 ${REPO_ID} (全量快照)..."
echo "保存目标路径: ${MODEL_DIR}"
echo "并发下载线程: ${MAX_WORKERS}"
echo "=========================================================="

"${MODELSCOPE_BIN}" download "${REPO_ID}" \
    --local-dir "${MODEL_DIR}" \
    --max-workers "${MAX_WORKERS}"

echo "=========================================================="
echo "✅ MiniMax-H3 权重下载完成！"
echo "文件位置: ${MODEL_DIR}"
du -sh "${MODEL_DIR}"
echo "=========================================================="
