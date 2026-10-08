#!/usr/bin/env bash
set -Eeuo pipefail

# ==============================================================================
# NVIDIA DGX Spark / GB10: Qwen3-TTS 与 ASR 语音模型全量下载脚本
# 模型源: ModelScope (魔搭社区)
# 存储目录: ~/models_cache/audio_models
# ==============================================================================

CACHE_ROOT="${MODEL_DIR:-${HOME}/models_cache/audio_models}"
MODELSCOPE_BIN="${MODELSCOPE_BIN:-${HOME}/.local/bin/modelscope}"
MAX_WORKERS="${MAX_WORKERS:-8}"

if [[ ! -x "${MODELSCOPE_BIN}" ]]; then
    if command -v modelscope >/dev/null 2>&1; then
        MODELSCOPE_BIN="$(command -v modelscope)"
    else
        echo "ERROR: ModelScope CLI not found. Please install via: pip install -U modelscope" >&2
        exit 1
    fi
fi

mkdir -p "${CACHE_ROOT}"

echo "=========================================================="
echo "🎯 DGX Spark 语音模型套件下载 (TTS + ASR)"
echo "目标存储根目录: ${CACHE_ROOT}"
echo "并发工作线程: ${MAX_WORKERS}"
echo "=========================================================="

# ------------------------------------------------------------------------------
# 1. 下载 Qwen3-TTS 系列 (千问旗舰语音合成)
# ------------------------------------------------------------------------------
echo ""
echo ">>> [1/4] 正在下载 Qwen3-TTS 旗舰版 (1.7B CustomVoice，支持 3秒克隆 + 自然语言情感指令)..."
"${MODELSCOPE_BIN}" download "Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice" \
    --local-dir "${CACHE_ROOT}/Qwen3-TTS-12Hz-1.7B-CustomVoice" \
    --max-workers "${MAX_WORKERS}"

echo ""
echo ">>> [2/4] 正在下载 Qwen3-TTS 轻量版 (0.6B CustomVoice，超低延迟)..."
"${MODELSCOPE_BIN}" download "Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice" \
    --local-dir "${CACHE_ROOT}/Qwen3-TTS-12Hz-0.6B-CustomVoice" \
    --max-workers "${MAX_WORKERS}"

# ------------------------------------------------------------------------------
# 2. 下载 ASR 系列 (阿里 FunASR / SenseVoice 极速情感识别与毫秒级字戳)
# ------------------------------------------------------------------------------
echo ""
echo ">>> [3/4] 正在下载 ASR 套件 (SenseVoiceSmall 极速情感识别)..."
"${MODELSCOPE_BIN}" download "iic/SenseVoiceSmall" \
    --local-dir "${CACHE_ROOT}/SenseVoiceSmall" \
    --max-workers "${MAX_WORKERS}"

echo ""
echo ">>> [4/4] 正在下载 Paraformer 影视字幕级 ASR (含 VAD + 标点恢复 + 毫秒级字戳)..."
"${MODELSCOPE_BIN}" download "iic/speech_paraformer-large-vad-punc_asr_nat-zh-cn-16k-common-vocab8404-pytorch" \
    --local-dir "${CACHE_ROOT}/paraformer-large-vad-punc" \
    --max-workers "${MAX_WORKERS}"

echo "=========================================================="
echo "✅ 全部 TTS & ASR 音频模型下载校验完成！"
echo "各模型目录状态:"
du -sh "${CACHE_ROOT}"/*
echo "=========================================================="
