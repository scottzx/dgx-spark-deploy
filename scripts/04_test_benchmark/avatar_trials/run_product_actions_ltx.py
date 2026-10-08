#!/usr/bin/env python3
"""Native LTX-2.5 keyframe-conditioned pickup, presentation, and put-back trials."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import time

runtime=Path('/home/admin/sol-spark-runtime');root=Path('/home/admin/digital-human-runtime')
inputs=root/'inputs/product_actions';out=root/'outputs/product_actions_ltx';out.mkdir(parents=True,exist_ok=True)
sys.path.insert(0,'/home/admin/sol-h3-spark/models/minimax_h3/Sol-H3-Spark')
sys.path.insert(0,str(runtime/'dependencies/offline-context'))
paths=json.loads((runtime/'paths.json').read_text())
sys.path[:0]=[str(Path(paths['ltx_root'])/'packages'/p/'src') for p in ('ltx-core','ltx-pipelines','ltx-kernels')]
cases=[('original','left','red Coca-Cola Original Taste can with white lettering'),
       ('diet','middle','silver Diet Coke can with red lettering'),
       ('zero','right','red Coca-Cola Zero Sugar can with black lettering')]
prompts={name:(
    'A single continuous eight-second photorealistic ecommerce demonstration, locked medium camera, no cuts, no zoom. '
    'The same Chinese woman with shoulder-length black hair and red blouse sits behind a light gray table against a gray studio backdrop. '
    'Three upright cans stand in a separated row: original red and white can at viewer left, silver diet can in the middle, red and black zero sugar can at viewer right. '
    f'At the beginning both hands are empty. During the first two seconds she reaches for ONLY the {position} can, the {appearance}, '
    'wraps her fingers around it, and lifts it smoothly off the table to upper chest height. '
    'For the middle four seconds she holds this one can upright with both hands, front label facing the camera, and naturally speaks to the viewer while presenting it. '
    'During the final two seconds she lowers the SAME can back onto its ORIGINAL tabletop position, lets the base touch the table, releases her grip, and rests both empty hands on the table. '
    'The other two cans stay untouched at their original positions throughout. Exactly three cans exist at every time: during presentation one is in her hands and two are on the table. '
    'Continuous physically plausible reach, grasp, lift, hold, lower, contact, release. Preserve the can identity, colors, cylinder shape, label and her facial identity. '
    'Soft steady studio light, natural fingers and contact shadows, no floating products, no duplicates, no spontaneous transformation.'
) for name,position,appearance in cases}
parser=argparse.ArgumentParser();parser.add_argument('mode',choices=['cache','generate']);args=parser.parse_args()
(out/'prompts.json').write_text(json.dumps(prompts,ensure_ascii=False,indent=2)+'\n')

if args.mode=='cache':
    from runtime import cache_builder
    for name,prompt in prompts.items():
        target=out/f'{name}_prompt.pt'
        if target.exists():continue
        cache_builder.FIXED_PROMPT=prompt
        print(json.dumps({'product':name,**cache_builder.build_cache(paths,target)}),flush=True)
    raise SystemExit(0)

import torch
from ltx_core.allocator_trim_strategy import AllocatorTrimStrategy
from ltx_core.components.noisers import GaussianNoiser
from ltx_core.loader import LoraPathStrengthAndSDOps,LTXV_LORA_COMFY_RENAMING_MAP
from ltx_core.loader.registry import ModelRegistry
from ltx_core.model.video_vae import get_video_chunks_number
from ltx_pipelines.utils.args import ImageConditioningInput
from ltx_pipelines.utils.blocks import ImageConditioner,DiffusionStage,VideoDecoder
from ltx_pipelines.utils.constants import DISTILLED_SIGMAS
from ltx_pipelines.utils.denoisers import SimpleDenoiser
from ltx_pipelines.utils.helpers import combined_image_conditionings
from ltx_pipelines.utils.media_io import encode_video
from ltx_pipelines.utils.types import ModalitySpec
from runtime.prompt_cache import load_cache

device=torch.device('cuda:0');dtype=torch.bfloat16
for index,(name,position,appearance) in enumerate(cases):
    target=out/name;target.mkdir(exist_ok=True)
    if (target/'metrics.json').exists() and (target/'motion.mp4').exists():continue
    started=time.perf_counter();torch.cuda.reset_peak_memory_stats()
    cache=load_cache(out/f'{name}_prompt.pt',prompt=prompts[name],torch_module=torch)
    video_context,audio_context=cache.contexts(prompts[name],device)
    registry=ModelRegistry(cache_models=False,cache_weights=False)
    encoder=ImageConditioner(paths['output_video_vae'],dtype,device,registry=registry)
    held=inputs/('zero_held_v2.png' if name=='zero' else f'{name}_held.png')
    refs=[ImageConditioningInput(str(inputs/'table.png'),0,1.,0),
          ImageConditioningInput(str(held),64,.9,0),
          ImageConditioningInput(str(held),136,.9,0),
          ImageConditioningInput(str(inputs/'table.png'),200,1.,0)]
    generator=torch.Generator(device=device).manual_seed(2026100720+index)
    with torch.inference_mode():
        conditions=encoder(lambda enc:combined_image_conditionings(refs,512,768,enc,dtype,device))
        loras=(LoraPathStrengthAndSDOps(paths['refiner_lora'],1.,LTXV_LORA_COMFY_RENAMING_MAP),)
        stage=DiffusionStage.from_checkpoint(paths['transformer'],dtype,device,loras=loras,registry=registry,alloc_trim_strategy=AllocatorTrimStrategy.TRIM)
        video,audio=stage(denoiser=SimpleDenoiser(video_context,audio_context),sigmas=DISTILLED_SIGMAS.to(device),
                          noiser=GaussianNoiser(generator),width=768,height=512,frames=201,fps=25.,
                          video=ModalitySpec(context=video_context,conditionings=conditions),audio=ModalitySpec(context=audio_context))
        decoder=VideoDecoder(paths['output_video_vae'],dtype,device,registry=registry)
        chunks=decoder(video.latent,None,generator,dtype=dtype)
        encode_video(video=chunks,fps=25.,audio=None,output_path=str(target/'motion.mp4'),video_chunks_number=get_video_chunks_number(201,None),crf=18,preset='fast')
        torch.cuda.synchronize()
    m={'product':name,'model':'LTX-2.5 dev + distilled LoRA','frames':201,'fps':25,'duration_seconds':8.04,'size':[768,512],
       'steps':8,'seed':2026100720+index,'generation_including_model_loading_seconds':time.perf_counter()-started,
       'peak_cuda_allocated_gib':torch.cuda.max_memory_allocated()/2**30,'prompt':prompts[name],
       'conditioning':[{'path':ref.path,'frame':ref.frame_idx,'strength':ref.strength,'sha256':hashlib.sha256(Path(ref.path).read_bytes()).hexdigest()} for ref in refs],
       'policy':'One continuous generated clip; keyframes are diffusion conditions, no inserted endpoint frames or reverse playback; Chinese dubbing is applied separately.'}
    (target/'metrics.json').write_text(json.dumps(m,ensure_ascii=False,indent=2)+'\n');print(json.dumps(m,ensure_ascii=False),flush=True)
    del video,audio,conditions,cache,video_context,audio_context,stage,decoder,encoder,registry
    torch.cuda.empty_cache()
