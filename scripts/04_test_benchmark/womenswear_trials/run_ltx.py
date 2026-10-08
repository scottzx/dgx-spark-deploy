"""LTX-2.5 continuous receive, display, return; six latent keyframe conditions."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import time
from config import ROOT, CASES, prompt

runtime=Path('/home/admin/sol-spark-runtime')
out=ROOT/'ltx';out.mkdir(parents=True,exist_ok=True)
sys.path.insert(0,'/home/admin/sol-h3-spark/models/minimax_h3/Sol-H3-Spark')
sys.path.insert(0,str(runtime/'dependencies/offline-context'))
paths=json.loads((runtime/'paths.json').read_text())
sys.path[:0]=[str(Path(paths['ltx_root'])/'packages'/p/'src') for p in ('ltx-core','ltx-pipelines','ltx-kernels')]
parser=argparse.ArgumentParser();parser.add_argument('mode',choices=['cache','generate']);args=parser.parse_args()
prompts={key:prompt(appearance) for key,label,appearance,text in CASES}
(out/'prompts.json').write_text(json.dumps(prompts,ensure_ascii=False,indent=2)+'\n')
(out/'model_paths.json').write_text(json.dumps(paths,indent=2)+'\n')
if args.mode=='cache':
    from runtime import cache_builder
    for key,label,appearance,text in CASES:
        target=out/f'{key}_prompt.pt'
        if target.exists():continue
        cache_builder.FIXED_PROMPT=prompts[key]
        print(json.dumps({'product':key,**cache_builder.build_cache(paths,target)}),flush=True)
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
for index,(key,label,appearance,text) in enumerate(CASES):
    target=out/key;target.mkdir(exist_ok=True)
    if (target/'metrics.json').exists() and (target/'motion.mp4').exists():continue
    started=time.perf_counter();torch.cuda.reset_peak_memory_stats()
    cache=load_cache(out/f'{key}_prompt.pt',prompt=prompts[key],torch_module=torch)
    video_context,audio_context=cache.contexts(prompts[key],device)
    registry=ModelRegistry(cache_models=False,cache_weights=False)
    encoder=ImageConditioner(paths['output_video_vae'],dtype,device,registry=registry)
    refs=[ImageConditioningInput(str(ROOT/'assets'/file),frame,strength,0)
          for file,frame,strength in [('empty.png',0,1.0),(f'{key}_handover.png',32,.85),
             (f'{key}_held.png',64,.9),(f'{key}_held.png',136,.9),
             (f'{key}_handover.png',168,.85),('empty.png',200,1.0)]]
    generator=torch.Generator(device=device).manual_seed(2026100810+index)
    with torch.inference_mode():
        conditions=encoder(lambda enc:combined_image_conditionings(refs,768,576,enc,dtype,device))
        loras=(LoraPathStrengthAndSDOps(paths['refiner_lora'],1.,LTXV_LORA_COMFY_RENAMING_MAP),)
        stage=DiffusionStage.from_checkpoint(paths['transformer'],dtype,device,loras=loras,
                 registry=registry,alloc_trim_strategy=AllocatorTrimStrategy.TRIM)
        video,audio=stage(denoiser=SimpleDenoiser(video_context,audio_context),
                 sigmas=DISTILLED_SIGMAS.to(device),noiser=GaussianNoiser(generator),
                 width=576,height=768,frames=201,fps=25.,
                 video=ModalitySpec(context=video_context,conditionings=conditions),
                 audio=ModalitySpec(context=audio_context))
        decoder=VideoDecoder(paths['output_video_vae'],dtype,device,registry=registry)
        chunks=decoder(video.latent,None,generator,dtype=dtype)
        encode_video(video=chunks,fps=25.,audio=None,output_path=str(target/'motion.mp4'),
                     video_chunks_number=get_video_chunks_number(201,None),crf=18,preset='fast')
        torch.cuda.synchronize()
    m={'product':key,'label':label,'model':'LTX-2.5 dev + distilled LoRA','frames':201,
       'fps':25,'duration_seconds':8.04,'size':[576,768],'aspect_ratio':'3:4','steps':8,'seed':2026100810+index,
       'generation_including_model_loading_seconds':time.perf_counter()-started,
       'peak_cuda_allocated_gib':torch.cuda.max_memory_allocated()/2**30,'prompt':prompts[key],
       'conditioning':[{'path':ref.path,'frame':ref.frame_idx,'strength':ref.strength,
              'sha256':hashlib.sha256(Path(ref.path).read_bytes()).hexdigest()} for ref in refs],
       'output_sha256':hashlib.sha256((target/'motion.mp4').read_bytes()).hexdigest(),
       'policy':'One continuous generated action. Six images condition latent diffusion; no inserted frames, reverse playback or action substitution. Chinese voice is applied separately.'}
    (target/'metrics.json').write_text(json.dumps(m,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(m,ensure_ascii=False),flush=True)
    del video,audio,conditions,cache,video_context,audio_context,stage,decoder,encoder,registry
    torch.cuda.empty_cache()
