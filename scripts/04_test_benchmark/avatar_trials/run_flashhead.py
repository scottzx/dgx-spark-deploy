#!/usr/bin/env python3
"""Use OpenAvatarChat's actual streaming processor with local FlashHead Lite."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import queue
import subprocess
import sys
import time
root=Path('/home/admin/digital-human-runtime')
source=root/'sources/SoulX-FlashHead';os.chdir(source);sys.path.insert(0,str(source))
os.environ['HF_HUB_OFFLINE']='1';os.environ['TRANSFORMERS_OFFLINE']='1'
import cv2
import numpy as np
import soundfile as sf
import torch
from flash_head.inference import get_pipeline,get_base_data,get_infer_params
processor_path=root/'sources/OpenAvatarChat/src/handlers/avatar/flashhead/flashhead_processor.py'
spec=importlib.util.spec_from_file_location('oac_flashhead_processor',processor_path)
module=importlib.util.module_from_spec(spec);sys.modules[spec.name]=module;spec.loader.exec_module(module)
parser=argparse.ArgumentParser();parser.add_argument('--smoke',action='store_true')
parser.add_argument('--image',default=str(root/'inputs/presenter.png'))
parser.add_argument('--audio',default=str(root/'inputs/narration_16k.wav'))
parser.add_argument('--original-audio',default=str(root/'inputs/narration.wav'))
parser.add_argument('--label');args=parser.parse_args()
label=args.label or ('smoke_B' if args.smoke else 'route_B_flashhead');out=root/'outputs'/label;out.mkdir(parents=True,exist_ok=True)
audio,sr=sf.read(args.audio,dtype='float32')
original,orig_sr=sf.read(args.original_audio,dtype='float32')
assert sr==16000 and orig_sr==24000
if args.smoke:audio=audio[:8*sr];original=original[:8*orig_sr]
start=time.perf_counter()
with torch.inference_mode():
    pipeline=get_pipeline(1,'/home/admin/models_cache/digital_human/flashhead','lite','/home/admin/models_cache/digital_human/wav2vec2-base-960h')
    get_base_data(pipeline,args.image,20261007,False)
    params=get_infer_params();torch.cuda.synchronize();ready=time.perf_counter()
    times=[]
    class TimedProcessor(module.FlashHeadProcessor):
        def _process_chunk(self,*a,**kw):
            torch.cuda.synchronize();t0=time.perf_counter()
            result=super()._process_chunk(*a,**kw)
            torch.cuda.synchronize();times.append(time.perf_counter()-t0)
            print(f'chunk {len(times)} {times[-1]:.3f} seconds',flush=True)
            return result
    processor=TimedProcessor(pipeline,params,output_audio_sample_rate=24000)
    processor.add_audio(audio,original,'coca-cola-fixed-narration',True)
    torch.cuda.synchronize();generated=time.perf_counter()
    frames=[];paired_audio=[]
    while not processor._output_queue.empty():
        item=processor._output_queue.get_nowait()
        if item.video_frame is not None:frames.append(item.video_frame)
        if item.audio_segment is not None:paired_audio.append(item.audio_segment)
    expected=int(np.ceil(len(audio)/sr*25));assert len(frames)>=expected
    frames=frames[:expected];h,w=frames[0].shape[:2]
    writer=cv2.VideoWriter(str(out/'silent.mp4'),cv2.VideoWriter_fourcc(*'mp4v'),25,(w,h))
    for frame in frames:writer.write(frame)
    writer.release()
    if paired_audio:sf.write(out/'paired_audio.wav',np.concatenate(paired_audio)[:len(original)],24000)
wav=Path(args.original_audio)
if args.smoke:
    wav=out/'smoke.wav';sf.write(wav,original,orig_sr)
subprocess.run(['ffmpeg','-v','error','-y','-i',str(out/'silent.mp4'),'-i',str(wav),'-c:v','libx264','-crf','18','-pix_fmt','yuv420p','-c:a','aac','-shortest',str(out/'raw.mp4')],check=True)
receipt={'route':'B','engine':'OpenAvatarChat FlashHeadProcessor + SoulX-FlashHead Lite',
         'integration_scope':'Actual OAC streaming audio buffer and paired output queue; browser WebRTC/LLM not included',
         'attention':'native PyTorch SDPA','torch_compile':False,'size':[w,h],
         'input_image':args.image,'input_audio':args.audio,
         'load_and_prepare_seconds':ready-start,'generation_seconds':generated-ready,
         'frames':len(frames),'duration_seconds':len(audio)/sr,
         'generation_fps':len(frames)/(generated-ready),'first_chunk_seconds':times[0],
         'chunk_seconds':times,'peak_cuda_allocated_gib':torch.cuda.max_memory_allocated()/2**30,
         'output_audio_matches_input':bool(paired_audio and np.array_equal(np.concatenate(paired_audio)[:len(original)],original))}
(out/'metrics.json').write_text(json.dumps(receipt,indent=2)+'\n');print(json.dumps(receipt),flush=True)
