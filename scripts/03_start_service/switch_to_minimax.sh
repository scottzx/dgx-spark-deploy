#!/usr/bin/env bash
# Sol-H3-Spark runs an official CLI batch in the foreground.
set -Eeuo pipefail
runtime=/home/admin/sol-spark-runtime
if [[ $# -eq 0 ]]; then
    echo '用法：bash switch_to_minimax.sh --prompt "视频描述" --output-dir /home/admin/sol-spark-runtime/outputs/新目录'
    exit 2
fi
if [[ ! -f "$runtime/paths.json" || ! -f "$runtime/fixed-prompt.pt" ]]; then
    echo 'Sol-H3-Spark 尚未完成准备：缺少 paths.json 或 fixed-prompt.pt。' >&2
    exit 1
fi
exec 8>"$runtime/inference.lock"
flock -n 8 || { echo '已有 Sol-H3-Spark 任务运行。' >&2; exit 1; }
if docker ps --format '{{.Names}}' | grep -qx 'qwen3-8-flash-next'; then
    docker stop qwen3-8-flash-next
fi
flock -u 8
exec 8>&-
exec bash "$runtime/run_sol_h3_spark.sh" "$@"
