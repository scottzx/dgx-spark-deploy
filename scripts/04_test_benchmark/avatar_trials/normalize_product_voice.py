#!/usr/bin/env python3
"""Match replacement clips by measured loudness using only a constant gain."""
import argparse
import json
from pathlib import Path
import subprocess
import time
import numpy as np
import soundfile as sf

parser=argparse.ArgumentParser()
parser.add_argument('--directory',type=Path,default=Path('/home/admin/digital-human-runtime/inputs/product_actions_serena'))
args=parser.parse_args();out=args.directory
receipt=json.loads((out/'voice.json').read_text())
started=time.perf_counter();previews=[];verification=[]
for record in receipt['clips']:
    name=record['product'];speech,sr=sf.read(out/f'{name}_speech.wav',dtype='float32')
    assert sr==24000
    full=np.zeros(round(8.04*sr),dtype=np.float32);offset=round(2.4*sr)
    full[offset:offset+len(speech)]=speech
    sf.write(out/f'{name}_analysis.wav',full,sr)
    result=subprocess.run(['ffmpeg','-hide_banner','-i',str(out/f'{name}_analysis.wav'),
                           '-af','loudnorm=I=-23:TP=-3:LRA=7:print_format=json','-f','null','-'],
                          check=True,capture_output=True,text=True)
    measured=json.loads(result.stderr[result.stderr.rfind('{'):])
    before=float(measured['input_i']);assert np.isfinite(before)
    gain=min(-23-before,-3-float(measured['input_tp']))
    speech*=10**(gain/20)
    assert np.isfinite(speech).all() and np.max(np.abs(speech))<1
    sf.write(out/f'{name}_speech.wav',speech,sr)
    full[:]=0;full[offset:offset+len(speech)]=speech
    sf.write(out/f'{name}.wav',full,sr)
    subprocess.run(['ffmpeg','-v','error','-y','-i',str(out/f'{name}.wav'),
                    '-ar','16000','-c:a','pcm_s16le',str(out/f'{name}_16k.wav')],check=True)
    record['level_matching']={'target_integrated_lufs':-23,'measured_before_lufs':before,
                              'constant_gain_db':gain,'pitch_or_timing_changed':False}
    import hashlib
    record['sha256']=hashlib.sha256((out/f'{name}.wav').read_bytes()).hexdigest()
    previews.extend([speech,np.zeros(4320,dtype=np.float32)])
    verification.append({'product':name,**record['level_matching']})
    (out/f'{name}_analysis.wav').unlink()
preview=np.concatenate(previews);sf.write(out/'voice_preview.wav',preview,24000)
receipt['voice_preview_duration_seconds']=len(preview)/24000
receipt['normalization_seconds']=time.perf_counter()-started
receipt['loudness_policy']='Match final padded action clips to -23 LUFS with constant gain, capped at -3 dBTP; no additional speed or pitch change.'
(out/'voice.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(verification,ensure_ascii=False),flush=True)
