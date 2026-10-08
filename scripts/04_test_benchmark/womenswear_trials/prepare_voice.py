#!/usr/bin/env python3
"""Shared soft Serena narration for the three garment exchanges."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

os.environ['HF_HUB_OFFLINE'] = '1'
os.environ['TRANSFORMERS_OFFLINE'] = '1'
import numpy as np
import soundfile as sf
import torch
from qwen_tts import Qwen3TTSModel

from config import ROOT, CASES as PRODUCT_CASES
OUT = ROOT / 'voices'
OUT.mkdir(parents=True, exist_ok=True)
CASES = [(key, text) for key, label, appearance, text in PRODUCT_CASES]
INSTRUCTION = ('温暖柔和、自然亲切的成年女声，音调稍低，用平稳的日常说话方式介绍商品，'
               '声音圆润放松，语速适中略紧凑，轻声清晰，不喊、不尖锐、不夸张，'
               '不用气声耳语，句尾平稳。产品名清楚，停顿简短。')
MAX_SPEECH = 3.44
TOTAL = 8.04
START = 2.4
started = time.perf_counter()
model = Qwen3TTSModel.from_pretrained(
    '/home/admin/models_cache/audio_models/Qwen3-TTS-12Hz-1.7B-CustomVoice',
    device_map='cuda:0', dtype=torch.bfloat16, attn_implementation='sdpa')
torch.cuda.synchronize()
loaded = time.perf_counter()
records = []

def trim_silence(wave, rate):
    # Trim only the outer quiet margins, keeping consonant and release padding.
    hop = round(rate * .01)
    levels = np.array([np.sqrt(np.mean(wave[i:i+hop] ** 2)) for i in range(0, len(wave), hop)])
    active = np.flatnonzero(levels > max(float(levels.max()) * .0126, .00005))
    if not len(active):
        raise ValueError('Generated voice is silent')
    begin = max(0, int(active[0]*hop-rate*.08))
    end = min(len(wave), int((active[-1]+1)*hop+rate*.16))
    return wave[begin:end], begin/rate, (len(wave)-end)/rate

for index, (name, text) in enumerate(CASES):
    t0 = time.perf_counter()
    attempts = []
    for attempt in range(2):
        seed = 2026100700 + index*10 + attempt
        torch.manual_seed(seed)
        instruction = INSTRUCTION + ('整句紧凑自然地说完，语速稍快但保持柔和，不拉长字音。' if attempt else '')
        wavs, rate = model.generate_custom_voice(
            text=text, language='Chinese', speaker='Serena', instruct=instruction,
            max_new_tokens=1024)
        torch.cuda.synchronize()
        wave = np.asarray(wavs[0], dtype=np.float32)
        assert rate == 24000 and np.isfinite(wave).all() and len(wave) > rate*.5
        sf.write(OUT/f'{name}_raw_attempt{attempt}.wav', wave, rate)
        trimmed, lead, tail = trim_silence(wave, rate)
        factor = max(1., len(trimmed)/rate/MAX_SPEECH)
        attempts.append({'seed':seed, 'instruction':instruction, 'raw_duration_seconds':len(wave)/rate,
                         'trimmed_duration_seconds':len(trimmed)/rate,
                         'trimmed_leading_seconds':lead, 'trimmed_trailing_seconds':tail,
                         'required_atempo':factor})
        if factor <= 1.35:
            break
    else:
        raise RuntimeError(f'{name}: voice does not fit the existing presentation window')
    sf.write(OUT/f'{name}_trimmed.wav', trimmed, rate)
    # Pitch-preserving duration adjustment plus mild presence reduction, not pitch shifting.
    filters = (f'atempo={factor:.8f},highpass=f=70,'
               'equalizer=f=3500:t=q:w=0.8:g=-2.5,loudnorm=I=-20:TP=-2:LRA=7')
    subprocess.run(['ffmpeg','-v','error','-y','-i',str(OUT/f'{name}_trimmed.wav'),
                    '-af',filters,'-ar','24000','-c:a','pcm_s16le',str(OUT/f'{name}_speech.wav')],check=True)
    speech, sr = sf.read(OUT/f'{name}_speech.wav', dtype='float32')
    assert sr == 24000 and len(speech)/sr <= MAX_SPEECH+.04
    audio = np.zeros(round(TOTAL*sr), dtype=np.float32)
    offset = round(START*sr)
    audio[offset:offset+len(speech)] = speech
    sf.write(OUT/f'{name}.wav', audio, sr)
    subprocess.run(['ffmpeg','-v','error','-y','-i',str(OUT/f'{name}.wav'),
                    '-ar','16000','-c:a','pcm_s16le',str(OUT/f'{name}_16k.wav')],check=True)
    record = {'product':name,'text':text,'speaker':'Serena','attempts':attempts,
              'selected_attempt':len(attempts)-1,'filters':filters,'speech_duration_seconds':len(speech)/sr,
              'narration_starts_seconds':START,'narration_ends_seconds':START+len(speech)/sr,
              'duration_seconds':TOTAL,'sample_rate':sr,'generation_and_processing_seconds':time.perf_counter()-t0,
              'sha256':hashlib.sha256((OUT/f'{name}.wav').read_bytes()).hexdigest()}
    records.append(record)
    print(json.dumps(record,ensure_ascii=False),flush=True)

preview = np.concatenate([piece for name,_ in CASES for piece in
                          (sf.read(OUT/f'{name}_speech.wav',dtype='float32')[0], np.zeros(round(.18*24000),dtype=np.float32))])
sf.write(OUT/'voice_preview.wav',preview,24000)
receipt = {'profile':'serena_soft','model':'Qwen3-TTS-12Hz-1.7B-CustomVoice','speaker':'Serena',
           'instruction':INSTRUCTION,'content':'Three generic women\'s garments','load_seconds':loaded-started,
           'total_seconds':time.perf_counter()-started,'clips':records,'voice_preview_duration_seconds':len(preview)/24000,
           'policy':'Same soft Serena voice and padded timeline for all three routes; mild EQ and loudness treatment; all raw attempts retained.'}
(OUT/'voice.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n')
subprocess.run([sys.executable,str(Path(__file__).with_name('normalize_product_voice.py')),'--directory',str(OUT)],check=True)
print(json.dumps({'completed':True,'voice_profile':str(OUT/'voice.json'),'total_seconds':receipt['total_seconds']},ensure_ascii=False),flush=True)
