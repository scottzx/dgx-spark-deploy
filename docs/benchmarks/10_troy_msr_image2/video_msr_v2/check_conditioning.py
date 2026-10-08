#!/usr/bin/env python3
"""Exercise installed native conditioning, reorder and crop on CPU sentinel latents."""
import json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent
sys.path[:0]=['/home/admin/sol-spark-runtime']
r=Path('/home/admin/sol-spark-runtime/sources/LTX-2/packages')
sys.path[:0]=[str(r/x/'src') for x in ('ltx-core','ltx-pipelines','ltx-kernels')]
import torch
from ltx_core.tools import VideoLatentTools
from ltx_core.types import VideoLatentShape,VideoPixelShape
from ltx_core.components.patchifiers import VideoLatentPatchifier
from ltx_core.conditioning.types.latent_cond import VideoConditionByLatentIndex
from ltx_core.conditioning.types.keyframe_cond import VideoConditionByKeyframeIndex
from run_ltx_identity_trial import MSRCondition,reorder
shape=VideoLatentShape.from_pixel_shape(VideoPixelShape(batch=1,frames=121,height=448,width=768,fps=24))
tools=VideoLatentTools(VideoLatentPatchifier(patch_size=1),shape,24.)
rows=[];n=16*14*24;frame=14*24
for slots in (3,5):
 for method in ('msr','msr_first','msr_first_last'):
  s=tools.create_initial_state('cpu',torch.float32)
  for i in range(slots):s=MSRCondition(torch.full((1,128,5,14,24),float(i+1)),i-slots,1).apply_to(s,tools)
  if method!='msr':s=VideoConditionByLatentIndex(torch.full((1,128,1,14,24),100.),1.,0).apply_to(s,tools)
  if method=='msr_first_last':s=VideoConditionByKeyframeIndex(torch.full((1,128,1,14,24),120.),120,1.).apply_to(s,tools)
  end=frame if method=='msr_first_last' else 0
  assert s.latent.shape[1]==n+slots*5*frame+end
  for i in range(slots):
   t=n+i*5*frame;assert torch.allclose(s.positions[:,0,t:t+frame,0],torch.full_like(s.positions[:,0,t:t+frame,0],(i-slots)/24.))
  if method!='msr':assert (s.clean_latent[:,:frame]==100).all() and (s.denoise_mask[:,:frame]==0).all()
  if end:assert (s.clean_latent[:,-frame:]==120).all() and (s.positions[:,0,-frame:,0]==5).all()
  perm=torch.cat((torch.arange(n,s.latent.shape[1]),torch.arange(n)))
  restored=reorder(reorder(s,perm),torch.argsort(perm))
  assert torch.equal(s.clean_latent,restored.clean_latent) and torch.equal(s.keyframes_mask,restored.keyframes_mask)
  result=tools.unpatchify(tools.clear_conditioning(restored))
  assert list(result.latent.shape)==[1,128,16,14,24]
  rows.append(dict(slots=slots,method=method,tokens=s.latent.shape[1],roundtrip=True,cropped_shape=list(result.latent.shape)))
report=dict(status='PASS',scope='CPU integration of installed native classes and existing MSR adapter; sentinel content, no model-quality claim',cases=rows)
(ROOT/'conditioning_check.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report))
