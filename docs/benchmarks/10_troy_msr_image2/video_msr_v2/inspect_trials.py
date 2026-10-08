#!/usr/bin/env python3
"""Verify actual clip hashes and make 0.5-second temporal contacts."""
import argparse,hashlib,json,subprocess
from pathlib import Path
from PIL import Image,ImageDraw,ImageFont
ROOT=Path(__file__).resolve().parent
FF='/opt/homebrew/bin/ffmpeg';FP='/opt/homebrew/bin/ffprobe'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 parser=argparse.ArgumentParser();parser.add_argument('--final',action='store_true');args=parser.parse_args()
 m=json.loads((ROOT/'manifest.json').read_text());out=ROOT/'inspection';out.mkdir(exist_ok=True);rows=[]
 font=ImageFont.truetype('/System/Library/Fonts/STHeiti Medium.ttc',19)
 for job in m['shots']:
  d=ROOT/'clips'/job['id'];source=d/'delivered.mp4';rp=d/'result.json'
  if not rp.exists() or not source.exists():
   if args.final:raise FileNotFoundError(source)
   continue
  result=json.loads(rp.read_text());assert result['input_fingerprint']==job['input_fingerprint'];assert sha(source)==result['media']['sha256']
  if (d/'raw.mp4').exists():assert sha(d/'raw.mp4')==result['raw_sha256']
  targets=out/job['id'];targets.mkdir(exist_ok=True)
  if len(list(targets.glob('f*.jpg')))!=11:
   subprocess.run([FF,'-v','error','-y','-i',str(source),'-vf',r'select=not(mod(n\,12))+eq(n\,119)', '-fps_mode','vfr','-q:v','2',str(targets/'f%03d.jpg')],check=True,capture_output=True)
  files=sorted(targets.glob('f*.jpg'));assert len(files)==11
  timestamps=[x/24 for x in list(range(0,120,12))+[119]]
  sheet=Image.new('RGB',(1536,770),'#191817');draw=ImageDraw.Draw(sheet)
  draw.text((8,4),f"{job['case_id']} {job['method']} · seed{job['seed']}",font=font,fill='#eee5d8')
  for i,(p,t) in enumerate(zip(files,timestamps)):
   im=Image.open(p).convert('RGB').resize((384,216));x=i%4*384;y=i//4*242+26;sheet.paste(im,(x,y));draw.text((x+8,y+216),f'{t:.3f}s',font=font,fill='white')
  sheet.save(out/(job['id']+'_contact.jpg'),quality=92)
  files[0].replace(targets/'f001.jpg') if False else None
  probe=json.loads(subprocess.check_output([FP,'-v','error','-count_frames','-show_streams','-of','json',str(source)]));v=next(s for s in probe['streams'] if s['codec_type']=='video');assert int(v['nb_read_frames'])==120 and (v['width'],v['height'])==(768,432)
  if args.final:subprocess.run([FF,'-v','error','-xerror','-i',str(source),'-f','null','-'],capture_output=True,check=True)
  rows.append(dict(id=job['id'],copy_matches=True,frames=120,sampled_times_s=timestamps,sha256=sha(source),full_decode=bool(args.final)))
 (out/'verification.json').write_text(json.dumps(dict(status='PASS' if args.final else 'incremental',clips=rows,count=len(rows),expected=24,scope='11 samples per clip; no audio or between-sample full-motion acceptance'),indent=2)+'\n');print(json.dumps(dict(verified=len(rows),final=args.final)))
if __name__=='__main__':main()
