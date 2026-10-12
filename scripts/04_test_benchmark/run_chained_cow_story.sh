#!/usr/bin/env bash
set -euo pipefail

runtime=/home/admin/sol-spark-runtime
package=/home/admin/sol-h3-spark/models/minimax_h3/Sol-H3-Spark

exec 9>"$runtime/inference.lock"
flock -n 9 || { echo "Another Sol-H3-Spark session is running." >&2; exit 1; }
if docker ps --format "{{.Names}}" | grep -q "^qwen3-8-"; then
  echo "Stop the Qwen language-model container before loading the video pipeline." >&2
  exit 1
fi

export SOL_H3_SPARK_RUNTIME_ROOT="$runtime"
export SOL_H3_SPARK_QWEN_IMAGE=sol-h3-spark-qwen
export CUDA_VISIBLE_DEVICES=0
export CUDA_HOME=/usr/local/cuda
export CPATH="$runtime/sysroot/usr/include/python3.12:$runtime/sysroot/usr/include${CPATH:+:$CPATH}"
export PATH="$HOME/.local/bin:/usr/local/cuda/bin:$PATH"
export HF_HUB_OFFLINE=1
export TRANSFORMERS_OFFLINE=1
export PYTHONUNBUFFERED=1

# Prevent Inductor fork deadlock on ARM64 / GB10
export TORCHINDUCTOR_COMPILE_THREADS=1
export TORCHINDUCTOR_MAX_AUTOTUNE=0

cd "$package"
exec "$runtime/bootstrap-env/bin/python" "$runtime/run_chained_cow_story.py" "$@"
