#!/usr/bin/env bash
# Run on DGX Spark from a checkout of this repository. Does not stop model services.
set -euo pipefail
runtime=/home/admin/qwen-image-2.1-runtime
source_commit=5ff8e59ff9fe81c6e2df4fb4c6ea0d97a5df5ab2
repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
uv=/home/admin/.local/bin/uv
[[ $(uname -m) == aarch64 ]] || { echo 'This recipe targets ARM64 DGX Spark.' >&2; exit 1; }
[[ -x "$uv" ]] || { echo "uv is required at $uv" >&2; exit 1; }
mkdir -p "$runtime/logs" "$runtime/outputs" "$runtime/sources/diffusers"
if [[ ! -x "$runtime/venv/bin/python" ]]; then
  "$uv" venv --python /usr/bin/python3 "$runtime/venv"
fi
python="$runtime/venv/bin/python"
"$uv" pip install --python "$python" torch==2.12.0 torchvision==0.27.0 \
  --index-url https://download.pytorch.org/whl/cu130
"$uv" pip install --python "$python" transformers==5.17.0 accelerate pillow \
  safetensors sentencepiece protobuf psutil
archive="$runtime/diffusers-source.tar.gz"
if ! tar -tzf "$archive" >/dev/null 2>&1; then
  curl -fL --retry 3 --connect-timeout 20 --max-time 1800 \
    "https://codeload.github.com/huggingface/diffusers/legacy.tar.gz/$source_commit" \
    -o "$archive.partial"
  tar -tzf "$archive.partial" >/dev/null
  mv "$archive.partial" "$archive"
fi
tar -xzf "$archive" --strip-components=1 -C "$runtime/sources/diffusers"
"$uv" pip install --python "$python" "$runtime/sources/diffusers"
"$python" -c 'from diffusers import QwenImage21Pipeline; import torch; print(QwenImage21Pipeline.__name__, torch.cuda.get_device_name())'
"$uv" pip freeze --python "$python" > "$runtime/requirements.lock.txt"
cp "$repo_root/scripts/03_start_service/generate_qwen_image_21.py" "$runtime/"
cp "$repo_root/scripts/03_start_service/run_qwen_image_21.sh" "$runtime/"
cp "$repo_root/scripts/02_download_model/download_qwen_image_21.py" "$runtime/"
cp "$repo_root/scripts/02_download_model/verify_qwen_image_21.py" "$runtime/"
if [[ ! -f "$runtime/modelscope-files.json" ]]; then
  curl -fsSL --retry 3 --max-time 120 \
    'https://modelscope.cn/api/v1/models/Qwen/Qwen-Image-2.1/repo/files?Revision=master&Recursive=true' \
    -o "$runtime/modelscope-files.json.partial"
  "$python" -c 'import json,sys; d=json.load(open(sys.argv[1])); assert d["Code"] == 200 and d["Data"]["Files"]' \
    "$runtime/modelscope-files.json.partial"
  mv "$runtime/modelscope-files.json.partial" "$runtime/modelscope-files.json"
fi
"$python" "$runtime/download_qwen_image_21.py" \
  --manifest "$runtime/modelscope-files.json" --model /home/admin/models_cache/Qwen-Image-2.1
"$python" "$runtime/verify_qwen_image_21.py" \
  --manifest "$runtime/modelscope-files.json" --model /home/admin/models_cache/Qwen-Image-2.1 \
  --receipt "$runtime/weights-verified.json"
echo 'Installation complete. Release other model services, then run run_qwen_image_21.sh for GPU acceptance.'
