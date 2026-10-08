#!/usr/bin/env python3
"""Local action storyboard benchmark: table → selected can in hand → same table."""
import hashlib
import argparse
import json
import os
from pathlib import Path
import subprocess
import time

os.environ['HF_HUB_OFFLINE']='1';os.environ['TRANSFORMERS_OFFLINE']='1'
from PIL import Image
import torch
from diffusers import QwenImage21Pipeline,FlowMatchEulerDiscreteScheduler

root=Path('/home/admin/digital-human-runtime');out=root/'inputs/product_actions';out.mkdir(parents=True,exist_ok=True)
parser=argparse.ArgumentParser();parser.add_argument('--retry-zero',action='store_true');args=parser.parse_args()
cases=[('original','original_gb.jpg',1,'left','red can with white Coca-Cola lettering'),
       ('diet','diet.jpg',2,'middle','silver Diet Coke can with red lettering'),
       ('zero','zero.jpg',3,'right','red Zero Sugar can with black Coca-Cola lettering')]
for name,product,voice,position,appearance in cases:
    for rate,suffix in [(24000,''),(16000,'_16k')]:
        subprocess.run(['ffmpeg','-v','error','-y','-i',str(root/f'inputs/voice_{voice:02d}.wav'),
                        '-af','adelay=2400,apad','-t','8.04','-ar',str(rate),'-c:a','pcm_s16le',str(out/f'{name}{suffix}.wav')],check=True)

pending=args.retry_zero or not (out/'table.png').exists() or any(not (out/f'{name}_held.png').exists() for name,*_ in cases)
if not pending:raise SystemExit('Action storyboard already exists; preserving it.')
started=time.perf_counter()
pipe=QwenImage21Pipeline.from_pretrained('/home/admin/models_cache/Qwen-Image-2.1',dtype=torch.bfloat16,local_files_only=True)
pipe.load_lora_weights('/home/admin/qwen-image-2.1-runtime/turbo',weight_name='Qwen-Image-2.1-viggle-turbo-v0.2.1-6step-lora-r256.safetensors',local_files_only=True)
pipe.scheduler=FlowMatchEulerDiscreteScheduler.from_config(pipe.scheduler.config,shift_terminal=None)
pipe.to('cuda');torch.cuda.synchronize();loaded=time.perf_counter()

def generate(path,refs,prompt,seed):
    if path.exists():return
    torch.cuda.reset_peak_memory_stats();torch.cuda.synchronize();t0=time.perf_counter()
    result=pipe(prompt=prompt,image=[Image.open(p).convert('RGB') for p in refs],width=768,height=512,
                num_inference_steps=6,true_cfg_scale=1.,sigmas=[1.,.9375,.875,.75,.5,.25],
                generator=torch.Generator('cuda').manual_seed(seed)).images[0]
    torch.cuda.synchronize();elapsed=time.perf_counter()-t0;result.save(path)
    receipt={'prompt':prompt,'seed':seed,'model':'Qwen-Image-2.1 + Viggle Turbo 6-step','size':list(result.size),
             'references':[str(p) for p in refs],'reference_sha256':[hashlib.sha256(p.read_bytes()).hexdigest() for p in refs],
             'load_seconds':loaded-started,'generation_seconds':elapsed,'peak_cuda_allocated_gib':torch.cuda.max_memory_allocated()/2**30,
             'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
    path.with_suffix('.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'image':str(path),'generation_seconds':elapsed}),flush=True)

if args.retry_zero:
    generate(out/'zero_held_v2.png',[out/'table.png',root/'inputs/zero.jpg'],
             'Edit reference image 1, preserving the exact camera, woman, gray background and table. There are exactly THREE beverage cans in the whole scene. '
             'Keep the LEFT red ORIGINAL can with WHITE lettering standing at the exact same left tabletop position. '
             'Keep the MIDDLE SILVER Diet Coke can with RED lettering standing at the exact same middle tabletop position. Both of these tabletop cans must remain visible. '
             'REMOVE the RIGHT red ZERO SUGAR can with BLACK lettering from the tabletop, leaving that right tabletop position EMPTY. '
             'The woman now physically holds that SAME removed ZERO SUGAR can at her upper chest on the VIEWER RIGHT side of her face, using one hand to grip it and the other palm to support its base. '
             'Use reference image 2 as the exact design of the ONLY ZERO SUGAR can in the scene. It exists ONLY in her hands, and never on the table in this edited frame. '
             'Exactly TWO cans on the table: original left and SILVER diet middle. Exactly ONE can in her hands: zero sugar at viewer right upper chest. '
             'Do not delete or replace the silver middle can. Do not leave a second zero sugar can on the table. '
             'Preserve her face, red blouse, camera framing, product scale and natural anatomically correct fingers. Mouth closed, coherent realistic photograph.',2026100791)
    raise SystemExit(0)

generate(out/'table.png',[root/'inputs/presenter.png']+[root/'inputs'/case[1] for case in cases],
         'Create one coherent photorealistic ecommerce studio photograph, landscape 3:2 composition. '
         'Preserve the exact adult Chinese woman from reference image 1, her facial identity, straight black hair, red crew-neck blouse and warm gray background. '
         'Medium waist-up shot with her centered behind a clean light gray tabletop, face clearly visible in the upper half. '
         'Both hands rest empty and relaxed on the tabletop near her body, not touching the products. '
         'Exactly three separate upright realistic 330ml beverage cans sit on the tabletop in a widely spaced row in front of her. '
         'From viewer left to right: reference image 2 red original Coca-Cola can with white letters; reference image 3 silver Diet Coke can with red letters; '
         'reference image 4 red Zero Sugar can with black letters. Preserve all three products and labels, the cans are palm-sized, realistic scale. '
         'All three cans, both hands and the space above the table are fully visible. Keep some empty table area around every can. '
         'Soft even frontal studio light and grounded can contact shadows. Her lips gently closed. No collage, no extra products, no writing outside can labels.',2026100701)
for i,(name,product,voice,position,appearance) in enumerate(cases):
    generate(out/f'{name}_held.png',[out/'table.png',root/'inputs'/product],
             'Edit reference image 1 into the middle keyframe of a product demonstration. Preserve exactly the same woman, face, red blouse, tabletop, gray background, framing, camera and lighting. '
             f'She has picked up ONLY the {position} can as viewed by the camera, the {appearance}, whose exact product design is given in reference image 2. '
             'She holds this one can upright at upper chest height with one hand gripping its lower side and the other palm supporting the base, label facing camera, below her unobstructed face. '
             f'The selected {position} can is no longer on the table: leave its former tabletop position empty. The other TWO cans remain standing at their exact original tabletop positions. '
             'Exactly three cans in the whole scene: ONE in her hands and TWO on the table. Realistic fingers wrapping around the same can, no hand-can penetration or extra fingers. '
             'Preserve product colors, proportions and lettering. No duplicated can, no extra products, no collage, no camera zoom. Lips gently closed.',2026100710+i)
