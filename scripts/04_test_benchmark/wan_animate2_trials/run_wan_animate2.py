#!/usr/bin/env python3
"""Run official distilled Wan-Animate-2 with an explicit reference and driving video."""
import argparse
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import sys
import time

ROOT=Path('/home/admin/wan-animate2-runtime')
sys.path.insert(0,str(ROOT/'deps'))
os.environ['HF_HUB_OFFLINE']='1';os.environ['TRANSFORMERS_OFFLINE']='1'
os.environ['PYTORCH_CUDA_ALLOC_CONF']='expandable_segments:True'
parser=argparse.ArgumentParser()
parser.add_argument('--reference',type=Path)
parser.add_argument('--driving',type=Path)
parser.add_argument('--prompt-file',type=Path)
parser.add_argument('--batch-manifest',type=Path)
parser.add_argument('--output',type=Path,required=True)
parser.add_argument('--width',type=int,default=320)
parser.add_argument('--height',type=int,default=480)
parser.add_argument('--fps',type=int,default=24)
parser.add_argument('--segment-frames',type=int,default=49)
parser.add_argument('--steps',type=int,default=10)
parser.add_argument('--seed',type=int,default=20261007)
parser.add_argument('--input-kind',choices=['official_example','real_product_capture','generated_product_video'],required=True)
args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=True)
if args.batch_manifest:
    jobs=json.loads(args.batch_manifest.read_text())
else:
    if not all([args.reference,args.driving,args.prompt_file]):
        parser.error('Supply --batch-manifest or --reference, --driving and --prompt-file')
    jobs=[{'reference':str(args.reference),'driving':str(args.driving),'prompt_file':str(args.prompt_file)}]
if args.segment_frames < 5 or (args.segment_frames-1)%4:
    parser.error('--segment-frames must be 4n+1, at least 5')
for job in jobs:
    for field in ['reference','driving','prompt_file']:
        if not Path(job[field]).is_file():parser.error(f'Missing {field}: {job[field]}')
import torch
import numpy as np
from PIL import Image
from diffusers import WanAnimate2DistilledModularPipeline
from diffusers.utils import export_to_video,load_image,load_video

def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as stream:
        while chunk:=stream.read(8*1024*1024):h.update(chunk)
    return h.hexdigest()

started=time.perf_counter()
model=Path('/home/admin/models_cache/Wan2.2-Animate-2-14B-Distilled-Diffusers')
pipe=WanAnimate2DistilledModularPipeline.from_pretrained(str(model),local_files_only=True)
pipe.load_components(dtype=torch.bfloat16)
for component in ['transformer','text_encoder','image_encoder','vae']:
    print(json.dumps({'stage':'move_component','component':component}),flush=True)
    getattr(pipe,component).to('cuda')
pipe.transformer.compile_repeated_blocks(fullgraph=False)
pipe.vae.enable_tiling()
torch.cuda.synchronize();loaded=time.perf_counter()
print(json.dumps({'stage':'model_loaded','load_seconds':loaded-started,'pipeline_class':type(pipe).__name__,'steps':args.steps}),flush=True)
for index,job in enumerate(jobs):
    reference=Path(job['reference']);driver=Path(job['driving']);prompt_file=Path(job['prompt_file'])
    output=args.output/job['product'] if 'product' in job else args.output
    output.mkdir(parents=True,exist_ok=True);case_start=time.perf_counter()
    driving,fps=load_video(str(driver),return_fps=True)
    image=load_image(str(reference));prompt=prompt_file.read_text().strip();seed=args.seed+index
    torch.cuda.reset_peak_memory_stats()
    print(json.dumps({'stage':'generate','product':job.get('product','official'),'input_frames':len(driving),'input_fps':fps}),flush=True)
    with torch.inference_mode():
        result=pipe(image=image,driving_video=driving,driving_video_fps=fps,prompt=prompt,
                    height=args.height,width=args.width,fps=args.fps,segment_frame_length=args.segment_frames,
                    num_inference_steps=args.steps,generator=torch.Generator('cuda').manual_seed(seed),output='videos')
    torch.cuda.synchronize();generated=time.perf_counter()
    frames=result[0];video=output/'motion.mp4'
    export_to_video(frames,str(video),fps=args.fps)
    size=list(frames[0].size) if isinstance(frames[0],Image.Image) else [int(np.asarray(frames[0]).shape[1]),int(np.asarray(frames[0]).shape[0])]
    receipt={'engine':'Official diffusers WanAnimate2DistilledModularPipeline','input_kind':args.input_kind,
             'product':job.get('product'),'reference':str(reference),'reference_sha256':sha(reference),'driving':str(driver),'driving_sha256':sha(driver),
             'prompt':prompt,'model_directory':str(model),'steps':args.steps,'seed':seed,'fps':args.fps,
             'input_frames':len(driving),'input_fps':fps,'segment_frame_length':args.segment_frames,'requested_area_size':[args.width,args.height],
             'frames':len(frames),'output_size':size,'load_seconds_shared':loaded-started,
             'generation_including_compile_seconds':generated-case_start,'case_total_seconds':time.perf_counter()-case_start,
             'peak_cuda_allocated_gib':torch.cuda.max_memory_allocated()/2**30,'output_sha256':sha(video),
             'packages':{name:importlib.metadata.version(name) for name in ['torch','diffusers','transformers','huggingface-hub','safetensors','tokenizers']},
             'policy':'Motion follows the declared video. Generated drivers are not real capture; their errors may carry into the result. Official examples verify the environment only.'}
    (output/'metrics.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(receipt,ensure_ascii=False),flush=True)
    del frames,result,driving
    torch.cuda.empty_cache()
