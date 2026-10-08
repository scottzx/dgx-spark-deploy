#!/usr/bin/env python3
import json
import argparse
import os
from pathlib import Path
import time
os.environ['HF_HUB_OFFLINE'] = '1'
os.environ['TRANSFORMERS_OFFLINE'] = '1'
from funasr import AutoModel
root = Path('/home/admin/digital-human-runtime')
parser = argparse.ArgumentParser()
parser.add_argument('--input',type=Path,default=root/'inputs/narration.wav')
parser.add_argument('--output',type=Path,default=root/'inputs/asr_check.json')
args = parser.parse_args()
start = time.perf_counter()
model = AutoModel(model='/home/admin/models_cache/audio_models/SenseVoiceSmall',
                  device='cuda:0', disable_update=True, trust_remote_code=True)
result = model.generate(input=str(args.input), language='zh', use_itn=True)
receipt = {'input':str(args.input),'elapsed_seconds':time.perf_counter()-start,'result':result}
args.output.write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(receipt,ensure_ascii=False),flush=True)
