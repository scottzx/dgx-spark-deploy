#!/usr/bin/env bash
set -euo pipefail
runtime=/home/admin/qwen-image-2.1-runtime
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 PYTHONUNBUFFERED=1
export CUDA_VISIBLE_DEVICES=0
exec "$runtime/venv/bin/python" "$runtime/generate_qwen_image_21.py" "$@"
