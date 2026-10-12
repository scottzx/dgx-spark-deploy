#!/usr/bin/env bash
# Run on the Spark host after preparation and GPU validation.
set -euo pipefail
runtime=/home/admin/sol-spark-runtime
package=/home/admin/sol-h3-spark/models/minimax_h3/Sol-H3-Spark
if [[ $# -eq 0 ]]; then
  echo 'Usage: run_sol_h3_spark.sh --prompt "..." --output-dir /home/admin/sol-spark-runtime/outputs/new-run'
  echo 'Or use --prompts prompts.jsonl to reuse the loaded models across a batch.'
  exit 2
fi
if [[ ! -f "$runtime/paths.json" || ! -f "$runtime/fixed-prompt.pt" ]]; then
  echo 'Sol-H3-Spark preparation is incomplete: paths.json and fixed-prompt.pt are required.' >&2
  exit 1
fi
exec 9>"$runtime/inference.lock"
flock -n 9 || { echo 'Another Sol-H3-Spark session is running.' >&2; exit 1; }
if docker ps --format '{{.Names}}' | grep -q '^qwen3-8-'; then
  echo 'Stop the Qwen language-model container before loading the video pipeline.' >&2
  exit 1
fi
export SOL_H3_SPARK_RUNTIME_ROOT="$runtime"
export SOL_H3_SPARK_QWEN_IMAGE=sol-h3-spark-qwen
export CUDA_VISIBLE_DEVICES=0
export CUDA_HOME=/usr/local/cuda
# Rootless Python development headers are also required by Triton at runtime.
export CPATH="$runtime/sysroot/usr/include/python3.12:$runtime/sysroot/usr/include${CPATH:+:$CPATH}"
export PATH="$HOME/.local/bin:/usr/local/cuda/bin:$PATH"
export HF_HUB_OFFLINE=1
export TRANSFORMERS_OFFLINE=1
export PYTHONUNBUFFERED=1
cd "$package"
exec "$runtime/bootstrap-env/bin/python" infer.py --paths "$runtime/paths.json" "$@"
