#!/usr/bin/env python3
"""Native H3 decode and standalone LTX first-frame trials in an exclusive GPU session."""
import argparse,hashlib,json,subprocess,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parent
RUNTIME=Path('/home/admin/sol-spark-runtime')
PACKAGE=Path('/home/admin/sol-h3-spark/models/minimax_h3/Sol-H3-Spark')
FFMPEG='/home/admin/.local/bin/ffmpeg';FFPROBE='/home/admin/.local/bin/ffprobe'
sys.path[:0]=[str(PACKAGE),str(RUNTIME)]
def save(p,x):
 p.parent.mkdir(parents=True,exist_ok=True);t=p.with_suffix('.partial.json');t.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n');t.replace(p)
def sha(p):
 with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def emit(**x):
 print(json.dumps(x),flush=True);save(ROOT/'progress.json',x)
def media(p,frames):
 x=json.loads(subprocess.check_output([FFPROBE,'-v','error','-count_frames','-show_streams','-show_format','-of','json',str(p)]))
 v=next(s for s in x['streams'] if s['codec_type']=='video');a=next(s for s in x['streams'] if s['codec_type']=='audio')
 assert int(v['nb_read_frames'])==frames and [v['width'],v['height']]==[672,384] and v['r_frame_rate']=='24/1',x
 assert a['channels']==2 and a['sample_rate']=='32000',x
 subprocess.run([FFMPEG,'-v','error','-xerror','-i',str(p),'-f','null','-'],check=True,capture_output=True)
 return dict(frames=frames,size=[672,384],fps=24,duration_s=frames/24,audio_sample_rate=32000,channels=2,full_decode=True,sha256=sha(p),bytes=p.stat().st_size)
def deliver(raw,p):
 subprocess.run([FFMPEG,'-y','-v','error','-i',str(raw),'-vf','trim=end_frame=120,setpts=PTS-STARTPTS','-af','atrim=end=5,asetpts=PTS-STARTPTS','-frames:v','120','-c:v','libx264','-crf','18','-pix_fmt','yuv420p','-c:a','aac','-ar','32000','-ac','2',str(p)],check=True)
 return media(p,120)
def paths():
 x=json.loads((RUNTIME/'paths.json').read_text())
 sys.path[:0]=[str(Path(x['ltx_root'])/'packages'/p/'src') for p in ('ltx-core','ltx-pipelines','ltx-kernels')]
 sys.path.insert(0,str(RUNTIME/'dependencies/offline-context'))
 return x
def caches(m):
 p=paths()
 from runtime import cache_builder
 from runtime.prompt_cache import load_cache
 import torch
 for key in ('ltx_old','ltx_new'):
  out=ROOT/'prompt_caches'/(key+'.pt');out.parent.mkdir(exist_ok=True)
  emit(status='LTX_ENCODING_PROMPT',key=key)
  if out.exists():load_cache(out,prompt=m['prompts'][key],torch_module=torch)
  else:
   cache_builder.FIXED_PROMPT=m['prompts'][key];cache_builder.build_cache(p,out)
def native(m):
 sys.path.insert(0,str(RUNTIME/'sources/FastVideo'))
 import numpy as np
 import torch
 from safetensors.torch import load_file
 from fastvideo.configs.models.vaes.minimax_h3_video import MiniMaxH3VideoVAEConfig
 from fastvideo.models.vaes.minimax_h3_video import AutoencoderKLMiniMaxH3
 from draft_preview import _write_wav
 p=paths();root=Path(p['h3_model'])/'vae';config=MiniMaxH3VideoVAEConfig()
 config.update_model_arch(json.loads((root/'config.json').read_text()))
 vae=AutoencoderKLMiniMaxH3(config).eval().requires_grad_(False);state={}
 for shard in sorted(root.glob('*.safetensors')):state.update(load_file(shard))
 vae.load_state_dict(state,strict=True);del state;vae.to('cuda')
 rows=[]
 for j in [x for x in m['jobs'] if x['model']=='h3']:
  d=ROOT/'clips'/j['id'];done=d/'result.json'
  if done.exists():
   row=json.loads(done.read_text());assert row['input_fingerprint']==j['input_fingerprint'] and sha(d/'delivered.mp4')==row['media']['sha256'];rows.append(row);continue
  response=json.loads((d/'capture_response.json').read_text());cap=Path(response['capture_dir'])
  record=json.loads((cap/'capture.json').read_text());assert record['case_id']==j['id'] and record['prompt']==j['prompt'] and record['seed']==j['seed']
  payload=torch.load(cap/'stage1_direct_tensors.pt',map_location='cpu',weights_only=True)
  latent=payload['h3_normalized'].to('cuda',dtype=torch.float32)
  pixels=torch.empty(vae.decoded_pixel_shape(latent.shape),dtype=torch.float32,device='cpu')
  emit(status='H3_NATIVE_DECODING',job=j['id'],completed=len(rows),total=6);t=time.monotonic()
  with torch.inference_mode(),torch.autocast('cuda',dtype=torch.float16):vae.decode_to_pixels(vae.denormalize_latents(latent),pixels)
  torch.cuda.synchronize();del latent
  decoded=pixels[0].clamp(0,1);frames,h,w=decoded.shape[1:];assert [w,h]==[672,384] and frames>=120
  rgb=d/'native.rgb';rgb.write_bytes((decoded.permute(1,2,3,0).numpy()*255).astype(np.uint8).tobytes())
  wav=d/'native.wav';_write_wav(wav,payload['audio'][:,:,:round(frames/24*32000)])
  raw=d/'raw.mp4'
  subprocess.run([FFMPEG,'-y','-v','error','-f','rawvideo','-pix_fmt','rgb24','-s',f'{w}x{h}','-r','24','-i',str(rgb),'-i',str(wav),'-frames:v',str(frames),'-c:v','libx264','-crf','18','-pix_fmt','yuv420p','-c:a','aac','-ar','32000','-ac','2',str(raw)],check=True)
  rgb.unlink();wav.unlink();v=deliver(raw,d/'delivered.mp4')
  row=dict(status='TECHNICAL_PASS',id=j['id'],input_fingerprint=j['input_fingerprint'],manifest_fingerprint=m['fingerprint'],model='h3',variant=j['variant'],seed=j['seed'],
           decoder='native full H3 VAE',refiner=False,raw_frames=frames,raw_sha256=sha(raw),media=v,native_decode_and_delivery_s=time.monotonic()-t,
           inference_profile='existing local W8A8/FastH3-VSA FL2VA, four transformer updates; native full VAE, no LTX refinement',
           h3_capture_dir=str(cap),capture_tensor_sha256=sha(cap/'stage1_direct_tensors.pt'),generation_s=response['client_wall_s'],quality_status='pending_manual')
  save(done,row);rows.append(row);emit(status='H3_NATIVE_COMPLETE',job=j['id'],completed=len(rows),total=6)
  del pixels,decoded,payload
 save(ROOT/'h3_native_results.json',dict(status='PASS',clips=rows))
def ltx(m):
 p=paths()
 import torch
 from contextlib import nullcontext
 from ltx_core.allocator_trim_strategy import AllocatorTrimStrategy
 from ltx_core.components.noisers import GaussianNoiser
 from ltx_core.loader import LoraPathStrengthAndSDOps,LTXV_LORA_COMFY_RENAMING_MAP
 from ltx_core.loader.registry import ModelRegistry
 from ltx_core.model.video_vae import get_video_chunks_number
 from ltx_pipelines.utils.blocks import ImageConditioner,DiffusionStage,VideoDecoder,AudioDecoder
 from ltx_pipelines.utils.constants import DISTILLED_SIGMAS
 from ltx_pipelines.utils.denoisers import SimpleDenoiser
 from ltx_pipelines.utils.helpers import combined_image_conditionings
 from ltx_pipelines.utils.args import ImageConditioningInput
 from ltx_pipelines.utils.media_io import encode_video
 from ltx_pipelines.utils.samplers import euler_denoising_loop
 from ltx_pipelines.utils.types import ModalitySpec
 from runtime.prompt_cache import load_cache
 device,dtype=torch.device('cuda:0'),torch.bfloat16
 registry=ModelRegistry(cache_models=False,cache_weights=False)
 encoder=ImageConditioner(p['output_video_vae'],dtype,device,registry=registry)
 lora=LoraPathStrengthAndSDOps(p['refiner_lora'],1.,LTXV_LORA_COMFY_RENAMING_MAP)
 stage=DiffusionStage.from_checkpoint(p['transformer'],dtype,device,loras=(lora,),registry=registry,alloc_trim_strategy=AllocatorTrimStrategy.TRIM)
 # Pinned installed API; preceding V2 same-input probe validated this resident path.
 resident=None
 def context(**kw):
  nonlocal resident
  if resident is None:resident=stage._build_transformer(**kw)
  return nullcontext(resident)
 stage._transformer_ctx=context
 vd=VideoDecoder(p['output_video_vae'],dtype,device,registry=registry)
 ad=AudioDecoder(p['audio_vae'],dtype,device,registry=registry)
 save(ROOT/'ltx_weights.json',{k:dict(path=p[k],bytes=Path(p[k]).stat().st_size,sha256=sha(p[k])) for k in ('transformer','refiner_lora','output_video_vae','audio_vae')})
 rows=[]
 for j in [x for x in m['jobs'] if x['model']=='ltx']:
  d=ROOT/'clips'/j['id'];d.mkdir(parents=True,exist_ok=True);done=d/'result.json'
  if done.exists():
   row=json.loads(done.read_text());assert row['input_fingerprint']==j['input_fingerprint'] and sha(d/'delivered.mp4')==row['media']['sha256'];rows.append(row);continue
  emit(status='LTX_GENERATING',job=j['id'],completed=len(rows),total=6);t=time.monotonic()
  cache=load_cache(ROOT/'prompt_caches'/('ltx_'+j['variant']+'.pt'),prompt=j['prompt'],torch_module=torch);vc,ac=cache.contexts(j['prompt'],device)
  image=ImageConditioningInput(path=str(ROOT/j['first_frame']),frame_idx=0,strength=1.,crf=0)
  with torch.inference_mode():
   conditions=encoder(lambda enc:combined_image_conditionings([image],384,672,enc,dtype,device))
   generator=torch.Generator(device=device).manual_seed(j['seed'])
   video,audio=stage(denoiser=SimpleDenoiser(vc,ac),sigmas=DISTILLED_SIGMAS.to(device),noiser=GaussianNoiser(generator),width=672,height=384,frames=121,fps=24.,
                     video=ModalitySpec(context=vc,conditionings=conditions),audio=ModalitySpec(context=ac),loop=euler_denoising_loop)
   torch.save(dict(video=video.latent.cpu(),audio=audio.latent.cpu()),d/'generated_latents.pt')
   raw=d/'raw.mp4';pixels=vd(video.latent,None,generator,dtype=dtype);sound=ad(audio.latent)
   encode_video(video=pixels,fps=24.,audio=sound,output_path=str(raw),video_chunks_number=get_video_chunks_number(121,None),crf=18,preset='fast')
  torch.cuda.synchronize();v=deliver(raw,d/'delivered.mp4')
  row=dict(status='TECHNICAL_PASS',id=j['id'],input_fingerprint=j['input_fingerprint'],manifest_fingerprint=m['fingerprint'],model='ltx',variant=j['variant'],seed=j['seed'],
           decoder='native LTX video VAE',refiner=False,raw_frames=121,raw_sha256=sha(raw),media=v,generation_s=time.monotonic()-t,
           inference_profile='BF16 dev transformer + distilled LoRA strength1,8 steps,first-frame strength1; no MSR',quality_status='pending_manual')
  save(done,row);rows.append(row);emit(status='LTX_COMPLETE',job=j['id'],completed=len(rows),total=6)
 save(ROOT/'ltx_results.json',dict(status='PASS',clips=rows))
def main():
 a=argparse.ArgumentParser();a.add_argument('--phase',choices=['native','caches','ltx'],required=True);args=a.parse_args()
 m=json.loads((ROOT/'manifest.json').read_text());assert str(ROOT)==m['remote_root'] and len(m['jobs'])==12
 assert sha(ROOT/'inputs/first.png')==m['first_frame_sha256']
 {'native':native,'caches':caches,'ltx':ltx}[args.phase](m)
if __name__=='__main__':main()
