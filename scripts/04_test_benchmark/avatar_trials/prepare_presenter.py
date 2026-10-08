#!/usr/bin/env python3
"""Create the common presenter locally with the already installed Qwen image model."""
import hashlib
import json
import os
from pathlib import Path
import time

os.environ['HF_HUB_OFFLINE'] = '1'
os.environ['TRANSFORMERS_OFFLINE'] = '1'
import torch
from diffusers import QwenImage21Pipeline, FlowMatchEulerDiscreteScheduler

root = Path('/home/admin/digital-human-runtime')
output = root / 'inputs/presenter.png'
if output.exists():
    raise SystemExit('Presenter already exists; keep the same reference for all routes.')
prompt = ('Photorealistic professional studio portrait for an ecommerce presenter. '
          'An original fictional Chinese adult woman aged 30, natural friendly appearance, '
          'shoulder length straight dark hair tucked behind the ears, clear unobstructed face, '
          'looking directly into the camera, lips gently closed, no visible teeth, '
          'natural subtle smile, red crew neck blouse, head and shoulders medium closeup, '
          'head centered, face occupies forty percent of frame height, '
          'soft even frontal lighting, plain warm light gray studio background, '
          'crisp eyes and face, realistic skin texture. No props, no drinks, no cans, '
          'no writing, no logo, no jewelry, no hands in frame. Square composition.')
start = time.perf_counter()
pipe = QwenImage21Pipeline.from_pretrained('/home/admin/models_cache/Qwen-Image-2.1',
                                         dtype=torch.bfloat16, local_files_only=True)
pipe.load_lora_weights('/home/admin/qwen-image-2.1-runtime/turbo',
                      weight_name='Qwen-Image-2.1-viggle-turbo-v0.2.1-6step-lora-r256.safetensors',
                      local_files_only=True)
pipe.scheduler = FlowMatchEulerDiscreteScheduler.from_config(pipe.scheduler.config, shift_terminal=None)
pipe.to('cuda')
torch.cuda.synchronize()
loaded = time.perf_counter()
result = pipe(prompt=prompt, width=768, height=768, num_inference_steps=6,
              true_cfg_scale=1.0, sigmas=[1.0, .9375, .875, .75, .5, .25],
              generator=torch.Generator('cuda').manual_seed(20261007)).images[0]
torch.cuda.synchronize()
result.save(output)
receipt = {'model': 'Qwen-Image-2.1 + Viggle Turbo 6-step', 'prompt': prompt,
           'seed': 20261007, 'load_seconds': loaded-start,
           'total_seconds': time.perf_counter()-start,
           'sha256': hashlib.sha256(output.read_bytes()).hexdigest()}
output.with_suffix('.json').write_text(json.dumps(receipt, indent=2) + '\n')
print(json.dumps(receipt), flush=True)
