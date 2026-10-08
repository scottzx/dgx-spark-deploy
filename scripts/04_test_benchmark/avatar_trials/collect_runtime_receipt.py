#!/usr/bin/env python3
"""Collect only hardware and package metadata; do not include credentials or environment."""
from datetime import datetime, timezone
import importlib.metadata
import json
from pathlib import Path
import platform
import subprocess

root = Path('/home/admin/digital-human-runtime')
packages = ['torch', 'transformers', 'diffusers', 'numpy', 'opencv-python', 'soundfile', 'qwen-tts']
receipt = {
    'recorded_at_utc': datetime.now(timezone.utc).isoformat(),
    'hostname': platform.node(), 'machine': platform.machine(), 'python': platform.python_version(),
    'packages': {name: importlib.metadata.version(name) for name in packages},
    'gpu': subprocess.check_output(['nvidia-smi', '--query-gpu=name,driver_version', '--format=csv,noheader'], text=True).strip(),
    'memory': subprocess.check_output(['free', '-b'], text=True),
    'active_gpu_compute': subprocess.check_output(['nvidia-smi', '--query-compute-apps=pid,process_name,used_memory', '--format=csv'], text=True),
    'active_containers': subprocess.check_output(['docker', 'ps', '--format', '{{.Names}}'], text=True).splitlines(),
    'runtime': str(root), 'model_cache': '/home/admin/models_cache/digital_human',
}
(root / 'runtime_receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
print(json.dumps(receipt, indent=2))
