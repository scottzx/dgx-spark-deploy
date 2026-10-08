#!/usr/bin/env python3
"""Produce one local Chinese narration and retain sentence timing for every route."""
import hashlib
import json
import os
from pathlib import Path
import time

os.environ['HF_HUB_OFFLINE'] = '1'
os.environ['TRANSFORMERS_OFFLINE'] = '1'
import numpy as np
import soundfile as sf
import torch
from scipy.signal import resample_poly
from qwen_tts import Qwen3TTSModel

root = Path('/home/admin/digital-human-runtime')
out = root / 'inputs'
texts = [
    '可口可乐，今天你想选哪一罐？',
    '原味，熟悉的经典可乐风味。',
    '健怡，无糖，口感更轻盈。',
    '零度，同样无糖，更接近原味可口可乐的风味。',
    '聚餐、追剧，或者想来一口冰爽，三种选择，按你的口味来。',
    '原味、健怡、零度，认准罐身标识，挑一罐你喜欢的，冰镇后更过瘾！',
]
start = time.perf_counter()
model = Qwen3TTSModel.from_pretrained(
    '/home/admin/models_cache/audio_models/Qwen3-TTS-12Hz-1.7B-CustomVoice',
    device_map='cuda:0', dtype=torch.bfloat16, attn_implementation='sdpa')
torch.cuda.synchronize()
loaded = time.perf_counter()
pieces, segments, cursor = [], [], 0
sr = None
for i, text in enumerate(texts):
    path = out / f'voice_{i:02d}.wav'
    torch.manual_seed(20261007+i)
    t0 = time.perf_counter()
    wavs, rate = model.generate_custom_voice(
        text=text, language='Chinese', speaker='Vivian',
        instruct='成年女性电商主播，普通话标准，明亮自然，热情但不夸张，语速稍快，吐字清晰，产品名字之间稍作停顿。',
        max_new_tokens=1024)
    torch.cuda.synchronize()
    wave = np.asarray(wavs[0], dtype=np.float32)
    assert len(wave) > rate*.5 and np.isfinite(wave).all()
    if sr is None:
        sr = rate
    assert sr == rate
    sf.write(path, wave, sr)
    segments.append({'id': i, 'text': text, 'start_seconds': cursor/sr,
                     'end_seconds': (cursor+len(wave))/sr,
                     'generation_seconds': time.perf_counter()-t0})
    pieces.extend([wave, np.zeros(round(sr*.18), dtype=np.float32)])
    cursor += len(wave) + round(sr*.18)
    print(json.dumps(segments[-1], ensure_ascii=False), flush=True)
audio = np.concatenate(pieces)
sf.write(out/'narration.wav', audio, sr)
audio16 = resample_poly(audio, 16000, sr)
sf.write(out/'narration_16k.wav', audio16, 16000)
sf.write(out/'smoke_16k.wav', audio16[:16000*8], 16000)
receipt = {'model': 'Qwen3-TTS-12Hz-1.7B-CustomVoice', 'speaker': 'Vivian',
           'sample_rate': sr, 'duration_seconds': len(audio)/sr,
           'load_seconds': loaded-start, 'total_seconds': time.perf_counter()-start,
           'segments': segments, 'torch': torch.__version__,
           'sha256': hashlib.sha256((out/'narration.wav').read_bytes()).hexdigest()}
(out/'narration.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2)+'\n')
print(json.dumps(receipt, ensure_ascii=False), flush=True)
