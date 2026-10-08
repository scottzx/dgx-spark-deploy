#!/usr/bin/env python3
"""Normalize native Wan videos to the existing, unchanged 25 FPS voice timing."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

ROOT=Path('/home/admin/wan-animate2-runtime');FF='/home/admin/.local/bin/ffmpeg';PROBE='/home/admin/.local/bin/ffprobe'
parser=argparse.ArgumentParser()
parser.add_argument('--products',nargs='+',choices=['original','diet','zero'],default=['original','diet','zero'])
args=parser.parse_args();receipt_path=ROOT/'outputs/products_25/normalization.json'
records=json.loads(receipt_path.read_text()) if receipt_path.exists() else []
for name in args.products:
    source=ROOT/'outputs/products_576'/name/'motion.mp4'
    target=ROOT/'outputs/products_25'/name;target.mkdir(parents=True,exist_ok=True)
    before=json.loads(subprocess.run([PROBE,'-v','error','-count_frames','-show_streams','-of','json',str(source)],check=True,capture_output=True,text=True).stdout)
    native=next(s for s in before['streams'] if s['codec_type']=='video')
    assert int(native['nb_read_frames'])==192 and native['avg_frame_rate']=='24/1'
    output=target/'motion.mp4'
    subprocess.run([FF,'-v','error','-y','-i',str(source),'-vf','fps=25,tpad=stop_mode=clone:stop_duration=0.04','-frames:v','201','-an',
                    '-c:v','libx264','-crf','18','-pix_fmt','yuv420p','-movflags','+faststart',str(output)],check=True)
    after=json.loads(subprocess.run([PROBE,'-v','error','-count_frames','-show_streams','-of','json',str(output)],check=True,capture_output=True,text=True).stdout)
    video=next(s for s in after['streams'] if s['codec_type']=='video')
    assert int(video['nb_read_frames'])==201 and video['avg_frame_rate']=='25/1' and abs(float(video['duration'])-8.04)<.001
    records=[r for r in records if r['product']!=name]
    records.append({'product':name,'native_frames':192,'native_fps':24,'native_duration_seconds':8.0,'output_frames':201,'output_fps':25,
                    'output_duration_seconds':8.04,'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),
                    'output_sha256':hashlib.sha256(output.read_bytes()).hexdigest(),
                    'last_frame_hold_seconds':.04,
                    'policy':'Official FPS preprocessing floors 201/25*24 to 192 frames (8.0 seconds). Timestamp-based conversion plus one 40 ms hold of the final generated frame aligns the existing 8.04-second voice. No speed change, reversed action, interpolation, or fabricated return action.'})
receipt_path.write_text(json.dumps(records,indent=2)+'\n')
print(json.dumps(records),flush=True)
