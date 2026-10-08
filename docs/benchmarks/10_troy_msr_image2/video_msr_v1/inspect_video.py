#!/usr/bin/env python3
"""Inspect downloaded videos and sample temporal frames for visual review."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parent

def sha(path):
    with path.open('rb') as f:
        return hashlib.file_digest(f,'sha256').hexdigest()

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--final',action='store_true')
    args=parser.parse_args()
    from PIL import Image,ImageDraw,ImageFont
    import numpy as np
    manifest=json.loads((ROOT/'manifest.json').read_text())
    out=ROOT/'inspection'; out.mkdir(exist_ok=True)
    font=ImageFont.truetype('/System/Library/Fonts/STHeiti Medium.ttc',19)
    small=ImageFont.truetype('/System/Library/Fonts/STHeiti Medium.ttc',15)
    rows=[]
    for shot in manifest['shots']:
        source=ROOT/'clips'/shot['id']/'delivered.mp4'
        result=source.parent/'result.json'
        if not source.exists() or not result.exists():
            if args.final: raise FileNotFoundError(source)
            continue
        receipt=json.loads(result.read_text())
        assert receipt['manifest_fingerprint']==manifest['fingerprint']
        assert sha(source)==receipt['media']['sha256']
        raw=source.parent/'raw.mp4'
        if raw.exists(): assert sha(raw)==receipt['raw_sha256']
        images=[]
        for timestamp in (0.3,2.5,4.7):
            target=out/(shot['id']+'_'+str(timestamp)+'.png')
            if not target.exists():
                subprocess.run(['ffmpeg','-v','error','-ss',str(timestamp),'-i',str(source),
                    '-frames:v','1',str(target)],check=True,capture_output=True)
            with Image.open(target) as im: images.append(im.convert('RGB'))
        diff=float(np.abs(np.asarray(images[0],dtype=np.float32)-np.asarray(images[-1],dtype=np.float32)).mean())
        row=Image.new('RGB',(1188,264),'#171614'); draw=ImageDraw.Draw(row)
        draw.text((10,5),f"{shot['id']}  {shot['title']}  ·  {shot['start_s']}–{shot['end_s']} s",font=font,fill='#eee5d8')
        for j,im in enumerate(images):
            row.paste(im.resize((384,216)),(j*396,42))
            draw.text((j*396+8,46),('0.3s','2.5s','4.7s')[j],font=small,fill='white',stroke_width=1,stroke_fill='black')
        row.save(out/(shot['id']+'_strip.jpg'),quality=90)
        rows.append(dict(id=shot['id'],title=shot['title'],sha256=sha(source),copy_matches=True,
            sampled_times_s=[0.3,2.5,4.7],first_last_pixel_mae_255=diff,
            motion_metric_scope='pixel variation includes camera and lighting; does not prove action compliance'))
    for start in range(0,len(rows),5):
        batch=rows[start:start+5]
        sheet=Image.new('RGB',(1188,264*len(batch)),'#171614')
        for j,row in enumerate(batch):
            with Image.open(out/(row['id']+'_strip.jpg')) as im: sheet.paste(im,(0,j*264))
        sheet.save(out/(f"contact_{batch[0]['id']}_{batch[-1]['id']}.jpg"),quality=90)
    report=dict(status='complete' if args.final else 'incremental',inspected=len(rows),expected=20,clips=rows)
    if args.final:
        film=ROOT/'film.mp4'; receipt=json.loads((ROOT/'result.json').read_text())
        assert sha(film)==receipt['media']['sha256']
        data=json.loads(subprocess.check_output(['ffprobe','-v','error','-count_frames','-show_streams','-of','json',str(film)]))
        v=next(x for x in data['streams'] if x['codec_type']=='video')
        a=next(x for x in data['streams'] if x['codec_type']=='audio')
        assert int(v['nb_read_frames'])==2400 and v['r_frame_rate']=='24/1'
        assert (v['width'],v['height'])==(768,432) and a['channels']==2
        subprocess.run(['ffmpeg','-v','error','-xerror','-i',str(film),'-f','null','-'],check=True,capture_output=True)
        report['film']=dict(sha256=sha(film),copy_matches=True,frames=2400,duration_s=100,fps=24,
            size=[768,432],channels=2,full_decode=True)
    (out/'verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(dict(inspected=len(rows),final=args.final,film=report.get('film'))))

if __name__=='__main__':
    main()
