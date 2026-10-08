"""Read-only transcript audit for each selected audition, with source hashes."""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import re

os.environ['HF_HUB_OFFLINE']='1'
os.environ['TRANSFORMERS_OFFLINE']='1'
os.environ['PATH']='/home/admin/.local/bin:'+os.environ.get('PATH','')
import torch
from funasr import AutoModel

parser=argparse.ArgumentParser()
parser.add_argument('--set',dest='voice_set',choices=['marketing','natural'],default='natural')
args=parser.parse_args()
ROOT=Path('/home/admin/womenswear-avatar-tests')/('natural_voice_v2' if args.voice_set=='natural' else 'marketing_voice_v1')
torch.set_num_threads(6)
model=AutoModel(model='/home/admin/models_cache/audio_models/SenseVoiceSmall',device='cpu',
    disable_update=True,trust_remote_code=True,disable_pbar=True,disable_log=True)
clean=lambda s:re.sub(r'[^\w\u4e00-\u9fff]','',re.sub(r'<\|.*?\|>','',s))
rows=[]
for p in sorted(ROOT.glob('*/receipt.json')):
    d=json.loads(p.read_text())
    for c in d['clips']:
        wav=p.parent/(c['key']+'.wav')
        digest=hashlib.sha256(wav.read_bytes()).hexdigest();assert digest==c['sha256']
        result=model.generate(input=str(wav),language='zh',use_itn=True,disable_pbar=True)
        transcript=''.join(t.get('text','') for t in result)
        row={'profile':d['key'],'clip':c['key'],'sha256':digest,'expected_text':c['text'],'result':result,
             'text_matches_after_punctuation_normalization':clean(transcript)==clean(c['text'])}
        rows.append(row);print(json.dumps(row,ensure_ascii=False),flush=True)
(ROOT/'asr_check.json').write_text(json.dumps({'checked_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
    'model':'SenseVoiceSmall','device':'cpu','clips':rows,
    'scope':'Automatic transcript audit; subjective naturalness and timbre require listening.'},ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'audited_clips':len(rows),'matching_transcripts':sum(r['text_matches_after_punctuation_normalization'] for r in rows)}),flush=True)
