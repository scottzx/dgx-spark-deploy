#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Native LTX 2.5 single-stage identity trials, including the MSR image-slot adapter.

MSR math follows liconstudio/ComfyUI-LTX2.5-MSR, revision
03061c18f8a79d26f3c63931dd8e28f5e5d872a6. See its upstream license.
Conditioning rows are prepended for sampling and restored before native cropping.
"""
import argparse
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import sys
import time

RUNTIME=Path('/home/admin/sol-spark-runtime')
ROOT=RUNTIME/'identity_tests_20261003'
sys.path.insert(0,'/home/admin/sol-h3-spark/models/minimax_h3/Sol-H3-Spark')
paths=json.loads((RUNTIME/'paths.json').read_text())
sys.path[:0]=[str(Path(paths['ltx_root'])/'packages'/p/'src') for p in ('ltx-core','ltx-pipelines','ltx-kernels')]
import torch
from ltx_core.conditioning.types.reference_video_cond import VideoConditionByReferenceLatent


def slot_embedding(slot_id,state,device,dtype):
 frequencies=state['frequencies'].to(device=device,dtype=torch.float32)
 value=torch.tensor(float(slot_id)/16,device=device,dtype=torch.float32)
 phases=value*frequencies
 features=torch.cat((value.reshape(1),torch.sin(phases),torch.cos(phases)))
 def linear(x,i):
  return torch.nn.functional.linear(x,state[f'net.{i}.weight'].to(device=device,dtype=torch.float32),
   state[f'net.{i}.bias'].to(device=device,dtype=torch.float32))
 return linear(torch.nn.functional.silu(linear(features,0)),2).to(dtype=dtype)


class MSRCondition(VideoConditionByReferenceLatent):
 def __init__(self,latent,offset,downscale):
  super().__init__(latent,downscale_factor=downscale,strength=1.)
  self.offset=offset
 def apply_to(self,latent_state,latent_tools):
  state,tools=latent_state,latent_tools
  result=super().apply_to(state,tools)
  count=tools.patchifier.patchify(self.latent).shape[1]
  positions=result.positions.clone()
  positions[:,0,-count:]+=self.offset/tools.fps
  return replace(result,positions=positions)


def reorder(state,indices):
 if state.attention_mask is not None:
  raise ValueError('MSR benchmark uses full conditioning attention')
 return replace(state,latent=state.latent[:,indices],clean_latent=state.clean_latent[:,indices],
  denoise_mask=state.denoise_mask[:,indices],positions=state.positions[:,:,indices],
  keyframes_mask=state.keyframes_mask[:,indices] if state.keyframes_mask is not None else None)


def resize_reference(path,width,height,background=False):
 import numpy as np
 from PIL import Image,ImageOps
 with Image.open(path) as im:
  im=im.convert('RGB')
  if background:im=ImageOps.fit(im,(width,height),method=Image.Resampling.BILINEAR)
  else:im=ImageOps.pad(im,(width,height),method=Image.Resampling.BILINEAR,color='white')
  return torch.from_numpy(np.array(im).copy()).permute(2,0,1).float()/127.5-1


def validate_conditioning():
 from ltx_core.components.patchifiers import VideoLatentPatchifier
 from ltx_core.tools import VideoLatentTools
 from ltx_core.types import VideoLatentShape,SpatioTemporalScaleFactors
 shape=VideoLatentShape(batch=1,channels=128,frames=2,height=2,width=3)
 tools=VideoLatentTools(VideoLatentPatchifier(patch_size=1),shape,24.,
  scale_factors=SpatioTemporalScaleFactors(time=8,height=32,width=32))
 state=tools.create_initial_state(device=torch.device('cpu'),dtype=torch.float32)
 latent=torch.ones(1,128,2,2,3)
 result=MSRCondition(latent,-4,1).apply_to(latent_state=state,latent_tools=tools)
 n=shape.token_count();length=result.latent.shape[1]
 perm=torch.cat((torch.arange(n,length),torch.arange(n)))
 restored=reorder(reorder(result,perm),torch.argsort(perm))
 assert torch.equal(restored.positions,result.positions)
 assert torch.equal(tools.clear_conditioning(restored).latent,state.latent)
 assert float(result.positions[0,0,n,0])==-4/24 or abs(float(result.positions[0,0,n,0])+4/24)<1e-6
 assert torch.all(result.clean_latent[:,n:]==1) and torch.all(result.denoise_mask[:,n:]==0)
 print(json.dumps(dict(status='PASS',check='MSR negative positions, clean references, prepend/crop roundtrip')),flush=True)


def main():
 parser=argparse.ArgumentParser(description=__doc__)
 parser.add_argument('--method',choices=['ingredients','msr'])
 parser.add_argument('--check',action='store_true')
 args=parser.parse_args()
 if args.check:
  validate_conditioning();return
 if not args.method:parser.error('--method required')
 from safetensors import safe_open
 from safetensors.torch import load_file,save_file
 from ltx_core.allocator_trim_strategy import AllocatorTrimStrategy
 from ltx_core.components.noisers import GaussianNoiser
 from ltx_core.loader import LoraPathStrengthAndSDOps,LTXV_LORA_COMFY_RENAMING_MAP
 from ltx_core.loader.registry import ModelRegistry
 from ltx_core.model.video_vae import get_video_chunks_number
 from ltx_pipelines.utils.blocks import ImageConditioner,DiffusionStage,VideoDecoder,AudioDecoder
 from ltx_pipelines.utils.constants import DISTILLED_SIGMAS
 from ltx_pipelines.utils.denoisers import SimpleDenoiser
 from ltx_pipelines.utils.media_io import encode_video
 from ltx_pipelines.utils.samplers import euler_denoising_loop
 from ltx_pipelines.utils.types import ModalitySpec
 from runtime.prompt_cache import load_cache
 out=ROOT/args.method;out.mkdir(exist_ok=True)
 started=time.monotonic()
 device=torch.device('cuda:0');dtype=torch.bfloat16
 filenames={'ingredients':'ltx-2.5-22b-ic-lora-ingredients-0.9.safetensors',
  'msr':'LTX-2.5-Licon-MSR-V2.safetensors'}
 lora_path=ROOT/'weights'/filenames[args.method]
 receipt=json.loads(lora_path.with_name(lora_path.name+'.receipt.json').read_text())
 with lora_path.open('rb') as source:
  assert hashlib.file_digest(source,'sha256').hexdigest()==receipt['sha256']
 with safe_open(lora_path,framework='pt',device='cpu') as f:metadata=f.metadata() or {}
 slot_state=None
 if args.method=='msr':
  tensors=load_file(lora_path)
  slot_state={};normal={}
  for key,value in tensors.items():
   stripped=key.removeprefix('diffusion_model.')
   if stripped.startswith('reference_slot_embedding.'):
    slot_state[stripped.removeprefix('reference_slot_embedding.')]=value
   elif stripped.startswith('reference_audio_slot_embedding.'):
    continue
   else:normal[key]=value
  assert {'frequencies','net.0.weight','net.0.bias','net.2.weight','net.2.bias'}<=slot_state.keys()
  lora_path=out/'image_only_lora.safetensors'
  if not lora_path.exists():save_file(normal,str(lora_path),metadata=metadata)
  del normal,tensors
 downscale=int(float(metadata.get('reference_downscale_factor','1')))
 assert downscale>=1 and 768%downscale==0 and 448%downscale==0
 prompt=json.loads((ROOT/'ltx_prompts.json').read_text())[args.method]
 cache=load_cache(ROOT/'prompt_caches'/(args.method+'.pt'),prompt=prompt,torch_module=torch)
 video_context,audio_context=cache.contexts(prompt,device)
 registry=ModelRegistry(cache_models=False,cache_weights=False)
 encoder=ImageConditioner(paths['output_video_vae'],dtype,device,registry=registry)
 condition_audit=[]
 def prepare(enc):
  conditions=[]
  if args.method=='ingredients':
   pixels=resize_reference(ROOT/'assets/ingredients_sheet.png',768,448)
   video=pixels[None,:,None].repeat(1,1,121,1,1).to(device=device,dtype=dtype)
   latent=enc(video)
   conditions.append(VideoConditionByReferenceLatent(latent,downscale_factor=1))
   condition_audit.append(dict(type='static_sheet_video',frames=121,latent_shape=list(latent.shape)))
  else:
   files=['red_identity.png','blue_identity.png','equipment.png','setting.png']
   for i,filename in enumerate(files):
    pixels=resize_reference(ROOT/'assets'/filename,768//downscale,448//downscale,background=i==3)
    video=pixels[None,:,None].repeat(1,1,33,1,1).to(device=device,dtype=dtype)
    latent=enc(video)
    embedding=slot_embedding(i+1,slot_state,device,dtype)
    assert embedding.numel()==latent.shape[1]
    latent=latent+embedding.view(1,-1,1,1,1)
    conditions.append(MSRCondition(latent,i-len(files),downscale))
    condition_audit.append(dict(type='MSR_slot',file=filename,slot_id=i+1,pixel_offset=i-len(files),
     embedding_norm=float(embedding.float().norm()),latent_shape=list(latent.shape)))
  return conditions
 with torch.inference_mode():conditions=encoder(prepare)
 loras=tuple(LoraPathStrengthAndSDOps(str(path),strength,LTXV_LORA_COMFY_RENAMING_MAP) for path,strength in
  [(paths['refiner_lora'],1.),(lora_path,1.)])
 stage=DiffusionStage.from_checkpoint(paths['transformer'],dtype,device,loras=loras,
  registry=registry,alloc_trim_strategy=AllocatorTrimStrategy.TRIM)
 def msr_loop(**kw):
  state=kw['video_state'];n=16*14*24;length=state.latent.shape[1]
  perm=torch.cat((torch.arange(n,length,device=device),torch.arange(n,device=device)))
  kw['video_state']=reorder(state,perm)
  video,audio=euler_denoising_loop(**kw)
  return reorder(video,torch.argsort(perm)),audio
 generator=torch.Generator(device=device).manual_seed(2026100301)
 noiser=GaussianNoiser(generator)
 with torch.inference_mode():
  video,audio=stage(denoiser=SimpleDenoiser(video_context,audio_context),sigmas=DISTILLED_SIGMAS.to(device),
   noiser=noiser,width=768,height=448,frames=121,fps=24.,
   video=ModalitySpec(context=video_context,conditionings=conditions),audio=ModalitySpec(context=audio_context),
   loop=msr_loop if args.method=='msr' else None)
  torch.save(dict(video=video.latent.cpu(),audio=audio.latent.cpu()),out/'generated_latents.pt')
  decoder=VideoDecoder(paths['output_video_vae'],dtype,device,registry=registry)
  chunks=decoder(video.latent,None,generator,dtype=dtype)
  audio_decoder=AudioDecoder(paths['audio_vae'],dtype,device,registry=registry)
  sound=audio_decoder(audio.latent)
  output=out/'trial.mp4'
  encode_video(video=chunks,fps=24.,audio=sound,output_path=str(output),
   video_chunks_number=get_video_chunks_number(121,None),crf=19,preset='fast')
 result=dict(status='PASS',method=args.method,output=str(output),elapsed_s=time.monotonic()-started,
  width=768,height=448,frames=121,fps=24,seed=2026100301,steps=8,distilled_lora_strength=1.,
  identity_lora_strength=1.,base_model=paths['transformer'],conditions=condition_audit,
  prompt=prompt,weight_receipt=receipt,native_port=args.method=='msr',
  msr_source_revision='03061c18f8a79d26f3c63931dd8e28f5e5d872a6' if args.method=='msr' else None,
  stage2_refinement=False)
 (out/'result.json').write_text(json.dumps(result,indent=2))
 print(json.dumps(result),flush=True)

if __name__=='__main__':main()
