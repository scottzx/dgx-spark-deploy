"""Retake the two short auditions flagged by automatic transcript checking."""
import datetime
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import time

os.environ['HF_HUB_OFFLINE']='1'
os.environ['TRANSFORMERS_OFFLINE']='1'
os.environ['PATH']='/home/admin/.local/bin:'+os.environ.get('PATH','')
import numpy as np
import soundfile as sf
import torch
from qwen_tts import Qwen3TTSModel
from funasr import AutoModel

parser=argparse.ArgumentParser()
parser.add_argument('--set',dest='voice_set',choices=['marketing','natural'],default='marketing')
args=parser.parse_args()
natural=args.voice_set=='natural'
ROOT=Path('/home/admin/womenswear-avatar-tests')/('natural_voice_v2' if natural else 'marketing_voice_v1')
lock=Path('/home/admin/avatar-company-tests/gpu.lock').open('w');fcntl.flock(lock,fcntl.LOCK_EX)
torch.set_num_threads(6)
model=Qwen3TTSModel.from_pretrained('/home/admin/models_cache/audio_models/Qwen3-TTS-12Hz-1.7B-CustomVoice',
    device_map='cuda:0',dtype=torch.bfloat16,attn_implementation='sdpa')
asr=AutoModel(model='/home/admin/models_cache/audio_models/SenseVoiceSmall',device='cpu',
    disable_update=True,trust_remote_code=True,disable_pbar=True,disable_log=True)
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
clean=lambda s:re.sub(r'[^\w\u4e00-\u9fff]','',re.sub(r'<\|.*?\|>','',s))
checked=[]
targets=[('serena_default','dress'),('serena_chat','audition_original_text')] if natural else [('serena_full','cardigan'),('vivian_live','dress')]
for key,name in targets:
    folder=ROOT/key;p=folder/'receipt.json';d=json.loads(p.read_text())
    previous=next(c for c in d['clips'] if c['key']==name)
    attempts=[]
    instruction=d['instruction'] if natural else d['instruction']+'商品颜色、产品名称和句尾每个字都完整清楚地说出来，不要吞字或省略字。'
    for attempt in range(1,3):
        seed=previous['seed']+50+attempt;torch.manual_seed(seed);started=time.perf_counter()
        wavs,rate=model.generate_custom_voice(text=previous['text'],language='Chinese',speaker=d['speaker'],
            instruct=instruction,max_new_tokens=1024)
        torch.cuda.synchronize();wave=np.asarray(wavs[0],dtype=np.float32)
        assert rate==24000 and np.isfinite(wave).all()
        raw=folder/f'{name}_raw_attempt{attempt}.wav';out=folder/f'{name}_attempt{attempt}.wav';sf.write(raw,wave,rate)
        measured=subprocess.run(['ffmpeg','-hide_banner','-i',str(raw),'-af',
            'highpass=f=65,equalizer=f=3500:t=q:w=0.8:g=-2,loudnorm=I=-23:TP=-3:LRA=11:print_format=json',
            '-f','null','-'],capture_output=True,text=True,check=True)
        s=measured.stderr;stats=json.loads(s[s.rfind('{'):s.rfind('}')+1]);gain=min(-23-float(stats['input_i']),-3-float(stats['input_tp']))
        subprocess.run(['ffmpeg','-v','error','-y','-i',str(raw),'-af',
            f'highpass=f=65,equalizer=f=3500:t=q:w=0.8:g=-2,volume={gain:.6f}dB',
            '-ar','24000','-c:a','pcm_s16le',str(out)],check=True)
        result=asr.generate(input=str(out),language='zh',use_itn=True,disable_pbar=True)
        transcript=''.join(x.get('text','') for x in result);matched=clean(transcript)==clean(previous['text'])
        item={'attempt':attempt,'seed':seed,'instruction':instruction,'result':result,'text_matches':matched,
              'duration_seconds':len(wave)/rate,'sha256':sha(out)};attempts.append(item)
        print(json.dumps({'profile':key,'clip':name,**item},ensure_ascii=False),flush=True)
        if not matched:continue
        for src in [folder/f'{name}_raw.wav',folder/f'{name}.wav']:
            backup=src.with_name(src.stem+'_attempt0.wav')
            if not backup.exists():shutil.copy2(src,backup)
        shutil.copy2(raw,folder/f'{name}_raw.wav');shutil.copy2(out,folder/f'{name}.wav')
        chosen=dict(previous,seed=seed,duration_seconds=len(wave)/rate,
            sha256=sha(out),raw_sha256=sha(raw),reused_existing_raw=False,
            generation_and_processing_seconds=time.perf_counter()-started,
            fits_existing_3_44_second_window=len(wave)/rate<=3.44,
            processing={'target_lufs':-23,'constant_gain_db':gain,'pre_gain_measurement':stats,
                'pitch_changed':False,'speed_changed':False,'equalizer':'highpass 65Hz; 3500Hz -2dB Q0.8'},
            instruction_override=instruction,previous_take=previous,retake_attempts=attempts)
        d['clips']=[chosen if c['key']==name else c for c in d['clips']]
        p.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n');break
    else:
        raise RuntimeError(f'{key}/{name}: both retakes need further transcript checking')
    checked.append({'profile':key,'clip':name,'selected_attempt':attempt,'attempts':attempts})
(ROOT/'asr_retakes.json').write_text(json.dumps({'checked_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
    'clips':checked,'scope':'Selected short retakes match automatic transcripts; listening remains the timbre acceptance criterion.'},
    ensure_ascii=False,indent=2)+'\n')
