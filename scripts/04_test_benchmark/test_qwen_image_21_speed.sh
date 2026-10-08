#!/usr/bin/env bash
# On Spark: run the resident Turbo/base benchmark, restoring the idle LLM afterward.
set -Eeuo pipefail
runtime=/home/admin/qwen-image-2.1-runtime
test -s "$runtime/weights-verified.json"
output="$runtime/outputs/speed-$(date +%Y%m%d-%H%M%S)"
paused=0
restore() {
  result=$?
  trap - EXIT
  if [[ "$paused" == 1 ]]; then
    docker start qwen3-8-flash-next
    healthy=0
    for ((i=0; i<90; i++)); do
      if curl -fsS --max-time 2 http://127.0.0.1:8001/health >/dev/null; then
        healthy=1
        echo 'Language model restored and healthy.'
        break
      fi
      sleep 2
    done
    [[ "$healthy" == 1 ]] || result=1
  fi
  exit "$result"
}
trap restore EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
trap 'exit 129' HUP
if docker ps --format '{{.Names}}' | grep -qx qwen3-8-flash-next; then
  curl -fsS --max-time 5 http://127.0.0.1:8001/slots | python3 -c \
    'import json,sys; s=json.load(sys.stdin); assert s and all(x.get("is_processing") is False for x in s), "Active LLM requests; retry later"'
  paused=1
  docker stop --timeout 60 qwen3-8-flash-next
fi
export PYTHONUNBUFFERED=1
export CUDA_VISIBLE_DEVICES=0
printf '%s\n' "$output" > "$runtime/latest-speed-dir.txt"
"$runtime/venv/bin/python" "$runtime/benchmark_qwen_image_21.py" \
  --cases-dir "$runtime/outputs/acceptance-20260929-164210" \
  --output "$output" "$@"
