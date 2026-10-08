"""Inspect actual consecutive frames at a JoyHallo 16-frame chunk boundary."""
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[3]/'docs/benchmarks/14_company_avatar_comparison'
rows = []
for product in ['original','diet','zero']:
    folder = ROOT/'results/joyhallo'/product
    video = folder/'video.mp4'
    if not video.exists():
        continue
    target = folder/'chunk_boundary_64_faces.jpg'
    if not target.exists() or target.stat().st_mtime < video.stat().st_mtime:
        graph = 'select=between(n\\,61\\,67),crop=256:258:122:160,scale=256:256:flags=bilinear,tile=7x1:padding=4'
        subprocess.run(['ffmpeg','-v','error','-y','-i',str(video),'-vf',graph,'-frames:v','1',str(target)],check=True)
    rows.append({'product':product,'frames':list(range(61,68)),
                 'timestamps':[i/25 for i in range(61,68)],'boundary_frame':64,
                 'image':str(target.relative_to(ROOT)),
                 'operation':'Actual candidate frames, crop x=122,y=160,w=256,h=258, bilinear scale 256x256, tile 7x1. No frame synthesis.'})
(ROOT/'joyhallo_chunk_frames.json').write_text(json.dumps(rows,indent=2)+'\n')
print('JoyHallo chunk boundary sheets:',len(rows))
