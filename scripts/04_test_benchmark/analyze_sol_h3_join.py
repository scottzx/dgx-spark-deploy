#!/usr/bin/env python3
"""Measure delivered joins and reconstructed overlap; no perceptual pass claim."""
import argparse
import json
from pathlib import Path
import subprocess

import numpy as np

FFMPEG='/home/admin/.local/bin/ffmpeg'


def audio(path):
    data=subprocess.check_output([FFMPEG,'-v','error','-i',str(path),'-vn','-ac','1','-ar','8000',
        '-f','f32le','pipe:1'])
    return np.frombuffer(data,dtype='<f4').astype(np.float64)


def frames(path, indices):
    expression='+'.join(f'eq(n\\,{i})' for i in indices)
    data=subprocess.check_output([FFMPEG,'-v','error','-i',str(path),'-vf',
        f"select='{expression}',scale=320:180",'-vsync','0','-pix_fmt','rgb24','-f','rawvideo','pipe:1'])
    return np.frombuffer(data,dtype=np.uint8).reshape(-1,180,320,3).astype(np.float32)/255


def rms(values):
    return float(np.sqrt(np.mean(values**2))) if len(values) else 0.


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('comparison',type=Path)
    args=parser.parse_args()
    report=json.loads(args.comparison.read_text())
    opening,continued,independent=report['shots']
    rows=[]
    before=frames(opening['video_path'],[119,120])
    wave_before=audio(opening['video_path'])
    for label,row in [('continue',continued),('independent',independent)]:
        after=frames(row['video_path'],[0,1])
        wave=audio(row['video_path'])
        left,right=rms(wave_before[-400:]),rms(wave[:400])
        rows.append(dict(transition=label,
            rgb_mae_at_join=float(np.abs(before[-1]-after[0]).mean()),
            rgb_mae_before_join=float(np.abs(before[1]-before[0]).mean()),
            rgb_mae_after_join=float(np.abs(after[1]-after[0]).mean()),
            audio_rms_50ms_before=left,audio_rms_50ms_after=right,
            audio_level_step=abs(left-right)/max(left+right,1e-12)))
    # Compare the generated overlap before trimming against the preceding
    # original audio. This is the PCM used by Stage2, before AAC encoding.
    import torch
    a=torch.load(Path(opening['capture_dir'])/'stage1_direct_tensors.pt',weights_only=True,map_location='cpu')['audio']
    b=torch.load(Path(continued['capture_dir'])/'stage1_direct_tensors.pt',weights_only=True,map_location='cpu')['audio']
    n=round(continued['trim_frames']/24*32000)
    tail=a[0].mean(0).numpy()[-n:][::4].astype(np.float64)
    head=b[0].mean(0).numpy()[:n][::4].astype(np.float64)
    values=[]
    for lag in range(-320,321):
        x,y=(tail[-lag:],head[:len(head)+lag]) if lag<0 else (tail[:len(tail)-lag],head[lag:])
        x,y=x-x.mean(),y-y.mean()
        values.append(float(np.dot(x,y)/max(np.linalg.norm(x)*np.linalg.norm(y),1e-12)))
    best=int(np.argmax(values))
    result=dict(joins=rows,overlap_audio=dict(correlation=values[best],lag_ms=(best-320)/8,
        span_s=continued['trim_frames']/24),
        note='Descriptive measurements only. Lighting/motion affect image MAE; periodic audio can alias correlation lag.')
    output=args.comparison.parent/'seam_metrics.json'
    output.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))


if __name__=='__main__':
    main()
