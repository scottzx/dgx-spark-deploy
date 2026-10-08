#!/usr/bin/env python3
"""MuseTalk lip dubbing on the actual moving frames of local product action videos."""
import json
import argparse
import math
import os
from pathlib import Path
import subprocess
import sys
import time
import hashlib

root=Path('/home/admin/digital-human-runtime');source=root/'sources/LiveTalking'
os.chdir(source);sys.path.insert(0,str(source))
os.environ['HF_HUB_OFFLINE']='1';os.environ['TRANSFORMERS_OFFLINE']='1'
import cv2
import numpy as np
import soundfile as sf
import torch
from avatars.musetalk.utils.utils import load_all_model
from avatars.musetalk.whisper.audio2feature import Audio2Feature
from avatars.musetalk.utils.face_parsing import FaceParsing
from avatars.musetalk.utils.blending import get_image_prepare_material
from avatars.musetalk.myutil import get_image_blending

arguments=argparse.ArgumentParser()
arguments.add_argument('--inputs',type=Path,default=root/'inputs/product_actions')
arguments.add_argument('--output',type=Path,default=root/'outputs/product_actions_dubbed')
arguments.add_argument('--motion',type=Path,default=root/'outputs/product_actions_ltx')
arguments.add_argument('--products',nargs='+',choices=['original','diet','zero'],default=['original','diet','zero'])
arguments.add_argument('--transition-mode',choices=['smooth','hard'],default='smooth')
args=arguments.parse_args()
inputs=args.inputs;motion=args.motion;out=args.output;out.mkdir(parents=True,exist_ok=True)
voice=json.loads((inputs/'voice.json').read_text()) if (inputs/'voice.json').exists() else {'profile':'vivian_original','speaker':'Vivian'}

def smoothstep(x):
    x=np.clip(x,0.,1.)
    return x*x*(3.-2.*x)

def speech_span(name,audio,sr):
    record=next((item for item in voice.get('clips',[]) if item['product']==name),None)
    if record:
        return record['narration_starts_seconds'],record['narration_ends_seconds']
    hop=round(.01*sr)
    level=np.array([np.sqrt(np.mean(audio[i:i+hop]**2)) for i in range(0,len(audio),hop)])
    active=np.flatnonzero(level>max(float(level.max())*.02,.00005))
    if not len(active):raise ValueError(f'{name}: no speech')
    return active[0]*hop/sr,min(len(audio),(active[-1]+1)*hop)/sr

def mouth_material(mask,mask_box,bbox):
    # Preserve nose, cheeks and jaw outline; feather only the mouth neighbourhood.
    x1,y1,x2,y2=bbox;x_s,y_s,x_e,y_e=mask_box
    yy,xx=np.mgrid[y_s:y_e,x_s:x_e]
    nx=(xx-(x1+x2)/2)/(x2-x1);ny=(yy-y1)/(y2-y1)
    horizontal=smoothstep((.42-np.abs(nx))/.16)
    vertical=smoothstep((ny-.48)/.14)*(1.-smoothstep((ny-.87)/.15))
    return np.rint(mask.astype(np.float32)*horizontal*vertical).astype(np.uint8)

started=time.perf_counter()
with torch.inference_mode():
    vae,unet,pe=load_all_model(device='cuda');vae.vae=vae.vae.half();unet.model=unet.model.half();pe=pe.half().to('cuda')
    audio_processor=Audio2Feature(model_path='models/whisper')
    parser_model=FaceParsing(left_cheek_width=90,right_cheek_width=90)
    cascade=cv2.CascadeClassifier(cv2.data.haarcascades+'haarcascade_frontalface_default.xml')
    torch.cuda.synchronize();loaded=time.perf_counter()
    for name in args.products:
        target=out/name;target.mkdir(exist_ok=True)
        motion_sha256=hashlib.sha256((motion/name/'motion.mp4').read_bytes()).hexdigest()
        audio_sha256=hashlib.sha256((inputs/f'{name}.wav').read_bytes()).hexdigest()
        if (target/'metrics.json').exists() and (target/'dubbed.mp4').exists():
            saved=json.loads((target/'metrics.json').read_text())
            if (saved.get('transition_mode','hard')==args.transition_mode
                    and saved.get('input_video_sha256')==motion_sha256
                    and saved.get('input_audio_sha256')==audio_sha256):continue
        t0=time.perf_counter();frames=[];boxes=[]
        capture=cv2.VideoCapture(str(motion/name/'motion.mp4'))
        if abs(capture.get(cv2.CAP_PROP_FPS)-25)>.01:raise ValueError('Expected 25 FPS action input')
        previous=None;fallback=[]
        while True:
            ok,frame=capture.read()
            if not ok:break
            faces=cascade.detectMultiScale(cv2.cvtColor(frame,cv2.COLOR_BGR2GRAY),1.1,4,minSize=(64,64))
            if len(faces):
                x,y,w,h=map(int,max(faces,key=lambda b:b[2]*b[3]));previous=[x,max(0,y+round(.04*h)),x+w,min(frame.shape[0],y+round(1.12*h))]
            elif previous is None:raise RuntimeError(f'No face in first frame of {name}')
            else:fallback.append(len(frames))
            frames.append(frame);boxes.append(previous.copy())
        capture.release()
        raw_boxes=[box.copy() for box in boxes]
        if args.transition_mode=='smooth':
            tracked=np.array(boxes,dtype=np.float32).reshape(-1,1,4)
            tracked=cv2.GaussianBlur(tracked,(1,7),1.25,borderType=cv2.BORDER_REPLICATE)
            boxes=np.rint(tracked.reshape(-1,4)).astype(int).tolist()
        audio,sr=sf.read(inputs/f'{name}_16k.wav',dtype='float32');assert sr==16000
        n=math.ceil(len(audio)/sr*25)
        if len(frames)!=n:raise RuntimeError(f'{name}: motion has {len(frames)} frames, audio requires {n}')
        features=audio_processor.audio2feat(audio);chunks=audio_processor.feature2chunks(features,25,n)
        speech_start,speech_end=speech_span(name,audio,sr)
        if args.transition_mode=='smooth':
            times=np.arange(n)/25
            # Full strength covers every phoneme; fade in before, fade out after speech.
            fade=.48;full_start=speech_start-.04;full_end=speech_end+.04
            weights=smoothstep((times-(full_start-fade))/fade)*(1.-smoothstep((times-full_end)/fade))
        else:
            fade=0.;weights=np.array([float(2.2<=i/25<=6.0) for i in range(n)])
        latents=[];masks=[];mask_boxes=[]
        for image,bbox in zip(frames,boxes):
            x1,y1,x2,y2=bbox
            crop=cv2.resize(image[y1:y2,x1:x2],(256,256),interpolation=cv2.INTER_LANCZOS4)
            latents.append(vae.get_latents_for_unet(crop))
            mask,mask_box=get_image_prepare_material(image,bbox,fp=parser_model,mode='jaw')
            if args.transition_mode=='smooth':mask=mouth_material(mask,mask_box,bbox)
            masks.append(cv2.cvtColor(mask,cv2.COLOR_GRAY2BGR));mask_boxes.append(mask_box)
        torch.cuda.synchronize();prepared=time.perf_counter()
        h,w=frames[0].shape[:2]
        writer=cv2.VideoWriter(str(target/'silent.mp4'),cv2.VideoWriter_fourcc(*'mp4v'),25,(w,h))
        for offset in range(0,n,8):
            count=min(8,n-offset)
            feats=pe(torch.from_numpy(np.stack(chunks[offset:offset+count])).to('cuda',dtype=unet.model.dtype))
            latent=torch.cat(latents[offset:offset+count],dim=0)
            pred=unet.model(latent,torch.tensor([0],device='cuda'),encoder_hidden_states=feats).sample
            decoded=vae.decode_latents(pred)
            for j,face in enumerate(decoded):
                i=offset+j;image=frames[i].copy()
                if weights[i]>0:
                    x1,y1,x2,y2=boxes[i];face=cv2.resize(face,(x2-x1,y2-y1),interpolation=cv2.INTER_LANCZOS4)
                    original=image.copy()
                    changed=get_image_blending(image,face,boxes[i],masks[i],mask_boxes[i])
                    image=cv2.addWeighted(changed,float(weights[i]),original,float(1.-weights[i]),0)
                writer.write(image)
        writer.release();torch.cuda.synchronize();rendered=time.perf_counter()
        subprocess.run(['ffmpeg','-v','error','-y','-i',str(target/'silent.mp4'),'-i',str(inputs/f'{name}.wav'),
                        '-c:v','libx264','-crf','18','-pix_fmt','yuv420p','-c:a','aac','-movflags','+faststart','-shortest',str(target/'dubbed.mp4')],check=True)
        m={'product':name,'engine':'LiveTalking MuseTalk 1.5 on moving frames','input_video':str(motion/name/'motion.mp4'),
           'input_video_sha256':motion_sha256,
           'input_audio':str(inputs/f'{name}.wav'),'voice_profile':voice['profile'],'speaker':voice['speaker'],
           'input_audio_sha256':audio_sha256,
           'frames':n,'fps':25,'duration_seconds':n/25,'size':[w,h],'load_seconds_shared':loaded-started,
           'video_preparation_and_audio_features_seconds':prepared-t0,'render_and_write_seconds':rendered-prepared,
           'peak_cuda_allocated_gib':torch.cuda.max_memory_allocated()/2**30,'face_boxes':boxes,'raw_face_boxes':raw_boxes,'face_detection_fallback_frames':fallback,
           'dubbed_frames':int(np.count_nonzero(weights)),'dubbing_window_seconds':[float(np.flatnonzero(weights)[0]/25),float(np.flatnonzero(weights)[-1]/25)],
           'narration_starts_seconds':float(speech_start),'narration_ends_seconds':float(speech_end),
           'transition_mode':args.transition_mode,'transition_seconds':fade,'transition_weights':weights.round(8).tolist(),
           'face_box_smoothing_frames':7 if args.transition_mode=='smooth' else 1,
           'mouth_region_policy':'Feathered mouth neighbourhood; nose, cheek edges and jaw outline retained from motion source.' if args.transition_mode=='smooth' else 'Original jaw mask',
           'policy':'Per-frame face input and masks; original moving hands, can, table and other products retained. No reversed playback or post-inserted return action.'}
        (target/'metrics.json').write_text(json.dumps(m,ensure_ascii=False,indent=2)+'\n')
        print(json.dumps({k:v for k,v in m.items() if k not in ['face_boxes','raw_face_boxes','transition_weights']},ensure_ascii=False),flush=True)
        del frames,latents,masks,chunks,features;torch.cuda.empty_cache()
