#!/usr/bin/env python3
"""Fixed-narration benchmark of the actual LiveTalking MuseTalk rendering components."""
import argparse
import json
import math
import os
from pathlib import Path
import pickle
import subprocess
import sys
import time
root = Path('/home/admin/digital-human-runtime')
source = root/'sources/LiveTalking'
os.chdir(source)
sys.path.insert(0,str(source))
os.environ['HF_HUB_OFFLINE']='1'
os.environ['TRANSFORMERS_OFFLINE']='1'
import cv2
import numpy as np
import soundfile as sf
import torch
from avatars.musetalk.utils.utils import load_all_model
from avatars.musetalk.whisper.audio2feature import Audio2Feature
from avatars.musetalk.utils.face_parsing import FaceParsing
from avatars.musetalk.utils.blending import get_image_prepare_material
from avatars.musetalk.myutil import get_image_blending

parser=argparse.ArgumentParser()
parser.add_argument('--audio',default=str(root/'inputs/narration_16k.wav'))
parser.add_argument('--label',default='route_A_musetalk')
parser.add_argument('--image',default=str(root/'inputs/presenter.png'))
parser.add_argument('--original-audio',help='Optional common source audio for final muxing')
args=parser.parse_args()
out=root/'outputs'/args.label;out.mkdir(parents=True,exist_ok=True)
start=time.perf_counter();torch.manual_seed(20261007)
with torch.inference_mode():
    vae,unet,pe=load_all_model(device='cuda')
    vae.vae=vae.vae.half();unet.model=unet.model.half();pe=pe.half().to('cuda')
    audio_processor=Audio2Feature(model_path='models/whisper')
    image=cv2.imread(args.image)
    if image is None:raise RuntimeError(f'Cannot read {args.image}')
    cascade=cv2.CascadeClassifier(cv2.data.haarcascades+'haarcascade_frontalface_default.xml')
    boxes=cascade.detectMultiScale(cv2.cvtColor(image,cv2.COLOR_BGR2GRAY),1.1,5,minSize=(100,100))
    if len(boxes)!=1:raise RuntimeError(f'Expected one face, got {len(boxes)}')
    x,y,w,h=map(int,boxes[0]);bbox=[x,max(0,y+round(.04*h)),x+w,min(image.shape[0],y+round(1.12*h))]
    x1,y1,x2,y2=bbox
    crop=cv2.resize(image[y1:y2,x1:x2],(256,256),interpolation=cv2.INTER_LANCZOS4)
    latent=vae.get_latents_for_unet(crop)
    parser_model=FaceParsing(left_cheek_width=90,right_cheek_width=90)
    mask,mask_box=get_image_prepare_material(image,bbox,fp=parser_model,mode='jaw')
    mask=cv2.cvtColor(mask,cv2.COLOR_GRAY2BGR)
    del parser_model
    avatar=source/'data/avatars'/args.label;(avatar/'full_imgs').mkdir(parents=True,exist_ok=True);(avatar/'mask').mkdir(exist_ok=True)
    cv2.imwrite(str(avatar/'full_imgs/00000000.png'),image)
    cv2.imwrite(str(avatar/'mask/00000000.png'),mask)
    for name,value in [('coords.pkl',[bbox]),('mask_coords.pkl',[mask_box])]:
        with (avatar/name).open('wb') as f:pickle.dump(value,f)
    torch.save([latent.cpu()],avatar/'latents.pt')
    (avatar/'avator_info.json').write_text(json.dumps({'avatar_id':args.label,'roi_method':'OpenCV Haar fixed image ROI','bbox':bbox}))
    torch.cuda.synchronize();ready=time.perf_counter()
    audio,sr=sf.read(args.audio,dtype='float32');assert sr==16000
    features=audio_processor.audio2feat(audio)
    n=math.ceil(len(audio)/sr*25)
    chunks=audio_processor.feature2chunks(features,25,n)
    torch.cuda.synchronize();encoded=time.perf_counter()
    writer=cv2.VideoWriter(str(out/'silent.mp4'),cv2.VideoWriter_fourcc(*'mp4v'),25,(image.shape[1],image.shape[0]))
    times=[];batch=8;first=None
    for offset in range(0,n,batch):
        t0=time.perf_counter();count=min(batch,n-offset)
        audio_features=pe(torch.from_numpy(np.stack(chunks[offset:offset+count])).to('cuda',dtype=unet.model.dtype))
        pred=unet.model(latent.repeat(count,1,1,1),torch.tensor([0],device='cuda'),encoder_hidden_states=audio_features).sample
        frames=vae.decode_latents(pred)
        torch.cuda.synchronize();dt=time.perf_counter()-t0
        times.append({'first_frame':offset,'frames':count,'seconds':dt})
        if first is None:first=time.perf_counter()-encoded
        for f in frames:
            face=cv2.resize(f,(x2-x1,y2-y1),interpolation=cv2.INTER_LANCZOS4)
            writer.write(get_image_blending(image.copy(),face,bbox,mask,mask_box))
        if offset%80==0:print(f'frames {offset+count}/{n} batch_seconds {dt:.3f}',flush=True)
    writer.release();rendered=time.perf_counter()
subprocess.run(['ffmpeg','-v','error','-y','-i',str(out/'silent.mp4'),'-i',args.original_audio or args.audio,'-c:v','libx264','-crf','18','-pix_fmt','yuv420p','-c:a','aac','-shortest',str(out/'raw.mp4')],check=True)
receipt={'route':'A','engine':'LiveTalking MuseTalk 1.5 rendering components',
         'integration_scope':'Fixed narration, model inference and compositing; WebRTC and conversational LLM not included',
         'roi_method':'OpenCV Haar on one static portrait','input_image':args.image,'input_audio':args.audio,'bbox':bbox,'frames':n,'fps':25,
         'duration_seconds':len(audio)/sr,'load_and_avatar_prepare_seconds':ready-start,
         'audio_feature_seconds':encoded-ready,'render_and_write_seconds':rendered-encoded,
         'gpu_inference_seconds':sum(t['seconds'] for t in times),
         'gpu_inference_fps':n/sum(t['seconds'] for t in times),
         'render_and_write_fps':n/(rendered-encoded),'first_batch_seconds':first,
         'peak_cuda_allocated_gib':torch.cuda.max_memory_allocated()/2**30,'batches':times}
(out/'metrics.json').write_text(json.dumps(receipt,indent=2)+'\n');print(json.dumps(receipt),flush=True)
