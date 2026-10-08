"""Export unaltered consecutive face crops around known speech boundaries."""
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[3]/'docs/benchmarks/14_company_avatar_comparison'
ENDS = {'original':4.689583333333333, 'diet':5.511083333333333, 'zero':5.839041666666667}
records = []
old = {}
if (ROOT/'speech_boundary_frames.json').exists():
    old = {(r['engine'],r['product'],r['phase']):r for r in json.loads((ROOT/'speech_boundary_frames.json').read_text())}
for engine in ['liveportrait','latentsync','longcat','infinitetalk','avatarforever','joyhallo','joyvasa','avatarforever_nocache','avatarforever_speaking']:
    for product,end in ENDS.items():
        directory = ROOT/'results'/engine/product
        candidate = directory/'video.mp4'
        if not candidate.exists(): continue
        media=json.loads(subprocess.check_output(['ffprobe','-v','error','-select_streams','v:0','-show_streams','-of','json',str(candidate)]))['streams'][0]
        candidate_crop = (320,80,128,128)
        format_version = 2
        operation = 'Fixed 128x128 face crop at x=320,y=80, bilinear 2x enlargement. No frame synthesis or quality score.'
        if (media['width'],media['height'])!=(768,512):
            if engine!='joyhallo' or (media['width'],media['height'])!=(512,512): continue
            # Map the baseline face rectangle through the actual input portrait
            # crop. This compares continuity within each row, not pixel errors.
            receipt=json.loads((directory/'metrics.json').read_text())
            left,top,right,bottom=receipt['portrait_crop_xyxy']
            sx,sy=512/(right-left),512/(bottom-top)
            candidate_crop=tuple(2*round(v/2) for v in ((320-left)*sx,(80-top)*sy,128*sx,128*sy))
            x,y,w,h=candidate_crop
            if min(x,y)<0 or x+w>512 or y+h>512: raise RuntimeError('Portrait face crop is outside actual media')
            format_version=3
            operation=f'Baseline crop x=320,y=80,w=128,h=128; candidate crop x={x},y={y},w={w},h={h}, mapped through recorded portrait input crop. Both scaled bilinearly to 256x256. No frame synthesis or pixel-error score.'
        for phase,timing in [('opening',2.48),('ending',end)]:
            center = round(timing*25)
            target = directory/f'{phase}_consecutive_faces.jpg'
            select = f'select=between(n\\,{center-2}\\,{center+2})'
            suffix = 'scale=256:256:flags=bilinear,tile=5x1:padding=4'
            x,y,w,h=candidate_crop
            graph = f'[0:v]{select},crop=128:128:320:80,{suffix}[a];[1:v]{select},crop={w}:{h}:{x}:{y},{suffix}[b];[a][b]vstack'
            if not target.exists() or target.stat().st_mtime < candidate.stat().st_mtime or old.get((engine,product,phase),{}).get('inspection_format_version')!=format_version:
                subprocess.run(['ffmpeg','-v','error','-y','-i',str(ROOT/'baseline'/f'{product}.mp4'),
                                '-i',str(candidate),'-filter_complex',graph,'-frames:v','1',str(target)],check=True)
            records.append({'engine':engine,'product':product,'phase':phase,'speech_boundary_seconds':timing,'inspection_format_version':format_version,
                            'candidate_face_crop_xywh':list(candidate_crop),
                            'nominal_audio_padding_start_seconds':2.4,'opening_center_note':'First clear speech energy is near 2.48s in all three shared tracks; 40ms bins, not forced phoneme alignment.',
                            'frames':list(range(center-2,center+3)),
                            'timestamps':[i/25 for i in range(center-2,center+3)],
                            'image':str(target.relative_to(ROOT)),
                            'layout':'Top row: LTX+Serena baseline. Bottom row: candidate. Left to right: five consecutive frames.',
                            'operation':operation})
(ROOT/'speech_boundary_frames.json').write_text(json.dumps(records,indent=2)+'\n')
print('Consecutive-frame face sheets:',len(records))
