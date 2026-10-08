#!/usr/bin/env python3
"""EchoMimicV3 Flash fixed-narration test, loading models once for all shots."""
import argparse
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import time
root=Path('/home/admin/digital-human-runtime');source=root/'sources/echomimic_v3'
os.chdir(source);sys.path.insert(0,str(source))
os.environ['HF_HUB_OFFLINE']='1';os.environ['TRANSFORMERS_OFFLINE']='1'
import cv2
import numpy as np
from omegaconf import OmegaConf
from PIL import Image
import soundfile as sf
import torch
from transformers import AutoTokenizer,Wav2Vec2FeatureExtractor
from src.wan_vae import AutoencoderKLWan
from src.wan_image_encoder import CLIPModel
from src.wan_text_encoder import WanT5EncoderModel
from src.wan_transformer3d_audio_2512 import WanTransformerAudioMask3DModel
from src.pipeline_wan_fun_inpaint_audio_2512 import WanFunInpaintAudioPipeline
from src.fm_solvers_unipc import FlowUniPCMultistepScheduler
from src.wav2vec2 import Wav2Vec2Model
from src.utils import get_image_to_video_latent2,filter_kwargs
from infer_flash import get_audio_embed,loudness_norm

parser=argparse.ArgumentParser();parser.add_argument('--smoke',action='store_true')
parser.add_argument('--image',default=str(root/'inputs/presenter.png'))
parser.add_argument('--audio',default=str(root/'inputs/narration_16k.wav'))
parser.add_argument('--original-audio',default=str(root/'inputs/narration.wav'))
parser.add_argument('--label');parser.add_argument('--frames-per-shot',type=int,default=81)
parser.add_argument('--prompt',default='A woman is speaking naturally to camera, subtle head movements, stable identity, professional product presentation.')
parser.add_argument('--negative-prompt',default='distorted face, unnatural mouth, exaggerated gestures, blurry face')
args=parser.parse_args()
if args.frames_per_shot<5 or args.frames_per_shot%4!=1:parser.error('--frames-per-shot must be 4n+1, at least 5')
label=args.label or ('smoke_C' if args.smoke else 'route_C_echomimic');out=root/'outputs'/label;out.mkdir(parents=True,exist_ok=True)
model_root=Path('/home/admin/models_cache/digital_human/wan-fun')
audio,sr=sf.read(args.audio,dtype='float32');assert sr==16000
if args.smoke:audio=audio[:round(3.24*sr)]
start=time.perf_counter();config=OmegaConf.load(source/'config/config.yaml');dtype=torch.bfloat16
torch.manual_seed(20261007)
with torch.inference_mode():
    encoder=Wav2Vec2Model.from_pretrained('/home/admin/models_cache/digital_human/chinese-wav2vec2-base',local_files_only=True).to('cpu')
    encoder.feature_extractor._freeze_parameters()
    extractor=Wav2Vec2FeatureExtractor.from_pretrained('/home/admin/models_cache/digital_human/chinese-wav2vec2-base',local_files_only=True)
    transformer=WanTransformerAudioMask3DModel.from_pretrained(str(model_root),
        transformer_additional_kwargs=OmegaConf.to_container(config.transformer_additional_kwargs),
        low_cpu_mem_usage=False,torch_dtype=dtype)
    vae=AutoencoderKLWan.from_pretrained(str(model_root/'Wan2.1_VAE.pth'),
        additional_kwargs=OmegaConf.to_container(config.vae_kwargs)).to(dtype)
    tokenizer=AutoTokenizer.from_pretrained(str(model_root/'google/umt5-xxl'),local_files_only=True)
    text_encoder=WanT5EncoderModel.from_pretrained(str(model_root/'models_t5_umt5-xxl-enc-bf16.pth'),
        additional_kwargs=OmegaConf.to_container(config.text_encoder_kwargs),low_cpu_mem_usage=False,torch_dtype=dtype).to(dtype).eval()
    clip_encoder=CLIPModel.from_pretrained(str(model_root/'models_clip_open-clip-xlm-roberta-large-vit-huge-14.pth')).to(dtype).eval()
    scheduler=FlowUniPCMultistepScheduler(**filter_kwargs(FlowUniPCMultistepScheduler,dict(config.scheduler_kwargs,shift=1)))
    pipeline=WanFunInpaintAudioPipeline(transformer=transformer,vae=vae,tokenizer=tokenizer,
        text_encoder=text_encoder,scheduler=scheduler,clip_image_encoder=clip_encoder).to('cuda')
    print(json.dumps({'component_dtypes':{'transformer':str(transformer.dtype),'text_encoder':str(text_encoder.dtype),'vae':str(vae.dtype)}}),flush=True)
    torch.cuda.synchronize();ready=time.perf_counter()
    ref=Image.open(args.image).convert('RGB')
    frames_per_shot=args.frames_per_shot;shot_samples=round(frames_per_shot/25*sr)
    total_frames=math.ceil(len(audio)/sr*25)
    writer=cv2.VideoWriter(str(out/'silent.mp4'),cv2.VideoWriter_fourcc(*'mp4v'),25,(512,512))
    times=[];written=0
    for i,begin in enumerate(range(0,len(audio),shot_samples)):
        raw=audio[begin:begin+shot_samples];original_length=len(raw)
        padded=np.pad(raw,(0,shot_samples-len(raw)))
        torch.cuda.synchronize();t0=time.perf_counter()
        normalized=loudness_norm(padded,sr)
        embeddings=get_audio_embed(normalized,extractor,encoder,frames_per_shot,sr=sr,fps=25,device='cpu').to('cuda',dtype=dtype)
        indices=(torch.arange(5)-2)
        centers=torch.arange(frames_per_shot).unsqueeze(1)+indices.unsqueeze(0)
        centers=torch.clamp(centers,0,embeddings.shape[0]-1)
        embeddings=embeddings[centers].unsqueeze(0).to('cuda')
        video,mask,clip_image=get_image_to_video_latent2(ref,None,video_length=frames_per_shot,sample_size=[512,512])
        result=pipeline(args.prompt,
            num_frames=frames_per_shot,negative_prompt=args.negative_prompt,
            audio_embeds=embeddings,audio_scale=1.0,ip_mask=None,use_un_ip_mask=False,
            height=512,width=512,generator=torch.Generator('cuda').manual_seed(20261007+i),
            neg_scale=1.0,neg_steps=0,use_dynamic_cfg=False,use_dynamic_acfg=False,
            guidance_scale=6.0,audio_guidance_scale=3.0,num_inference_steps=8,
            video=video,mask_video=mask,clip_image=clip_image,cfg_skip_ratio=0.0,shift=5.0).videos
        torch.cuda.synchronize();dt=time.perf_counter()-t0
        # Upstream defaults to a NumPy [B,C,T,H,W] result.
        result=torch.as_tensor(result)
        clip_frames=(result[0].permute(1,2,3,0).clamp(0,1)*255).byte().cpu().numpy()
        count=min(len(clip_frames),total_frames-written)
        for frame in clip_frames[:count]:writer.write(frame[:,:,::-1])
        written+=count
        row={'shot':i,'audio_start_seconds':begin/sr,'audio_duration_seconds':original_length/sr,'generated_frames':frames_per_shot,'retained_frames':count,'seconds':dt}
        times.append(row);print(json.dumps(row),flush=True)
        shot_writer=cv2.VideoWriter(str(out/f'shot_{i:02d}.mp4'),cv2.VideoWriter_fourcc(*'mp4v'),25,(512,512))
        for frame in clip_frames[:count]:shot_writer.write(frame[:,:,::-1])
        shot_writer.release()
        (out/'progress.json').write_text(json.dumps({'completed_shots':times,'retained_frames':written},indent=2)+'\n')
        cv2.imwrite(str(out/f'shot_{i:02d}_last.jpg'),clip_frames[count-1][:,:,::-1])
        del result,clip_frames
    writer.release();generated=time.perf_counter()
wav=Path(args.original_audio)
if args.smoke:wav=out/'smoke.wav';sf.write(wav,audio,sr)
subprocess.run(['ffmpeg','-v','error','-y','-i',str(out/'silent.mp4'),'-i',str(wav),'-c:v','libx264','-crf','18','-pix_fmt','yuv420p','-c:a','aac','-shortest',str(out/'raw.mp4')],check=True)
receipt={'route':'C','engine':'EchoMimicV3 Flash','size':[512,512],'steps':8,
         'attention':'native PyTorch SDPA','precision':'bfloat16 (explicit cast after custom T5 loader)',
         'shot_policy':f'{frames_per_shot}-frame shots, same reference image at each shot; no temporal continuation between shots',
         'input_image':args.image,'input_audio':args.audio,'prompt':args.prompt,'negative_prompt':args.negative_prompt,
         'load_and_prepare_seconds':ready-start,'generation_seconds':generated-ready,
         'duration_seconds':len(audio)/sr,'frames':written,'generation_fps':written/(generated-ready),
         'peak_cuda_allocated_gib':torch.cuda.max_memory_allocated()/2**30,'shots':times}
(out/'metrics.json').write_text(json.dumps(receipt,indent=2)+'\n');print(json.dumps(receipt),flush=True)
