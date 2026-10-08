#!/usr/bin/env python3
"""Local reference-conditioned Qwen image benchmark for handheld product presenters."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time
import wave

os.environ['HF_HUB_OFFLINE']='1'
os.environ['TRANSFORMERS_OFFLINE']='1'
from PIL import Image
import torch
from diffusers import QwenImage21Pipeline, FlowMatchEulerDiscreteScheduler

root=Path('/home/admin/digital-human-runtime')
out=root/'inputs/handheld';out.mkdir(parents=True,exist_ok=True)
cases=[('original','original_gb.jpg',1,'原味，熟悉的经典可乐风味。'),
       ('diet','diet.jpg',2,'健怡，无糖，口感更轻盈。'),
       ('zero','zero.jpg',3,'零度，同样无糖，更接近原味可口可乐的风味。')]
duration=97/25
for name,product,voice,text in cases:
    source_audio=root/f'inputs/voice_{voice:02d}.wav'
    with wave.open(str(source_audio)) as wav:
        if wav.getframerate()!=24000 or wav.getnframes()/wav.getframerate()>duration:raise ValueError('Voice does not fit the common shot')
    for rate,suffix in [(24000,''),(16000,'_16k')]:
        subprocess.run(['ffmpeg','-v','error','-y','-i',str(source_audio),'-af','apad','-t',str(duration),'-ar',str(rate),'-c:a','pcm_s16le',str(out/f'{name}{suffix}.wav')],check=True)
    (out/f'{name}_audio.json').write_text(json.dumps({'text':text,'duration_seconds':duration,'original_voice':f'voice_{voice:02d}.wav','source_product':product},ensure_ascii=False,indent=2)+'\n')

pending=[case for case in cases if not (out/f'{case[0]}.png').exists()]
if not pending:raise SystemExit('All handheld inputs already exist; preserving them.')
started=time.perf_counter()
pipe=QwenImage21Pipeline.from_pretrained('/home/admin/models_cache/Qwen-Image-2.1',dtype=torch.bfloat16,local_files_only=True)
pipe.load_lora_weights('/home/admin/qwen-image-2.1-runtime/turbo',weight_name='Qwen-Image-2.1-viggle-turbo-v0.2.1-6step-lora-r256.safetensors',local_files_only=True)
pipe.scheduler=FlowMatchEulerDiscreteScheduler.from_config(pipe.scheduler.config,shift_terminal=None)
pipe.to('cuda');torch.cuda.synchronize();loaded=time.perf_counter()
for name,product,voice,text in pending:
    refs=[root/'inputs/presenter.png',root/'inputs'/product]
    prompt=('Create a single coherent photorealistic ecommerce presenter photograph. '
            'Reference image 1 is the presenter: preserve this exact adult Chinese woman, her facial identity, straight shoulder-length black hair, red crew-neck blouse and warm gray studio background. '
            'Reference image 2 is the exact beverage can she is presenting: preserve its can shape, colors, design and visible brand lettering. '
            'Reframe as a waist-up medium shot, square composition. Her unobstructed face occupies approximately one third of the image height in the upper half. '
            'She looks at the camera with gently closed lips. Both forearms and anatomically correct hands are completely visible. '
            'She physically holds exactly one can upright at upper chest height below and to the right of her face as seen by the viewer. '
            'Her right hand grips the lower side of the can with fingers naturally wrapping around its curved surface, and her left palm supports the can bottom. '
            'The main can label faces the camera and is unobstructed. Realistic hand-can contact, contact shadows and natural proportions; the can is about the length of her palm. '
            'Face, both hands and whole can clearly visible with margin around them, consistent soft studio lighting. '
            'No separate product panel, no collage, no floating can, no additional cans, no extra fingers, no subtitles. Opaque square photograph.')
    images=[Image.open(p).convert('RGB') for p in refs]
    torch.cuda.reset_peak_memory_stats();torch.cuda.synchronize();t0=time.perf_counter()
    result=pipe(prompt=prompt,image=images,width=768,height=768,num_inference_steps=6,true_cfg_scale=1.0,
                sigmas=[1.,.9375,.875,.75,.5,.25],generator=torch.Generator('cuda').manual_seed(20261008)).images[0]
    torch.cuda.synchronize();elapsed=time.perf_counter()-t0
    path=out/f'{name}.png';result.save(path)
    receipt={'model':'Qwen-Image-2.1 + Viggle Turbo 6-step','seed':20261008,'prompt':prompt,'size':list(result.size),
             'references':[str(p) for p in refs],'reference_sha256':[hashlib.sha256(p.read_bytes()).hexdigest() for p in refs],
             'load_seconds':loaded-started,'generation_seconds':elapsed,'peak_cuda_allocated_gib':torch.cuda.max_memory_allocated()/2**30,
             'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'policy':'Single generated input per SKU; shared unchanged across A/B/C; no packaging repair or post-composited product'}
    path.with_suffix('.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'product':name,'generation_seconds':elapsed,'output':str(path)}),flush=True)
