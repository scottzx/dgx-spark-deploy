#!/usr/bin/env bash
# Integration acceptance: scene asset, RGBA prop, then a reference-image edit.
set -Eeuo pipefail
runtime=/home/admin/qwen-image-2.1-runtime
test -s "$runtime/weights-verified.json" || { echo 'Verify model weights first.' >&2; exit 1; }
output="$runtime/outputs/acceptance-$(date +%Y%m%d-%H%M%S)"
mkdir -p "$output"
printf '%s\n' "$output" > "$runtime/latest-acceptance-dir.txt"
paused=0
restore_language_model() {
  result=$?
  trap - EXIT
  if [[ "$paused" == 1 ]]; then
    docker start qwen3-8-flash-next
    restored=0
    for ((i=0; i<90; i++)); do
      if curl -fsS --max-time 2 http://127.0.0.1:8001/health >/dev/null; then
        restored=1
        echo 'Language model restored and healthy.'
        break
      fi
      sleep 2
    done
    if [[ "$restored" != 1 ]]; then
      echo 'ERROR: language model did not become healthy after restart.' >&2
      result=1
    fi
  fi
  exit "$result"
}
trap restore_language_model EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
trap 'exit 129' HUP
if docker ps --format '{{.Names}}' | grep -qx qwen3-8-flash-next; then
  [[ ${1:-} == --pause-idle-qwen ]] || { echo 'Language model is running; pass --pause-idle-qwen for temporary idle-service switching.' >&2; exit 1; }
  curl -fsS --max-time 5 http://127.0.0.1:8001/slots | python3 -c \
    'import json,sys; slots=json.load(sys.stdin); assert slots and all(s.get("is_processing") is False for s in slots), "Language model has active requests; retry after they finish"'
  paused=1
  docker stop --timeout 60 qwen3-8-flash-next
fi
bash "$runtime/run_qwen_image_21.sh" \
  --prompt 'An empty sunlit art studio, warm cream walls, large wooden worktable, shelves of ceramic pots, a large window on the left, cinematic realistic environment asset, eye-level wide shot, no people, no text, no watermark.' \
  --width 1344 --height 768 --steps 40 --seed 42 --output "$output/studio.png"
bash "$runtime/run_qwen_image_21.sh" \
  --transparent --prompt 'A single small handcrafted red ceramic teapot, three-quarter view, entire handle and spout visible, realistic studio product lighting, isolated object, no text, no watermark.' \
  --width 1024 --height 1024 --steps 40 --seed 43 --output "$output/teapot-red.png"
bash "$runtime/run_qwen_image_21.sh" \
  --image "$output/teapot-red.png" --transparent \
  --prompt 'Change only the red ceramic glaze of this teapot to cobalt blue. Preserve the exact teapot shape, handle, spout, camera angle, lighting and transparent background. No text or watermark.' \
  --width 1024 --height 1024 --steps 40 --seed 44 --output "$output/teapot-blue.png"
echo "Image generation checks complete: $output"
echo 'Inspect all three images visually before declaring acceptance complete.'
