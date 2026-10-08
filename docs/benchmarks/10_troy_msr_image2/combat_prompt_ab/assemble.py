#!/usr/bin/env python3
"""Assemble all three seed comparisons; manual review chooses any featured candidate."""
import hashlib,json,shutil,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parent
FONT='/System/Library/Fonts/Supplemental/Arial.ttf'
def sha(p):
 with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def verify(p,frames,size):
 x=json.loads(subprocess.check_output(['ffprobe','-v','error','-count_frames','-show_streams','-of','json',str(p)]));v=next(s for s in x['streams'] if s['codec_type']=='video')
 assert int(v['nb_read_frames'])==frames and [v['width'],v['height']]==size and v['r_frame_rate']=='24/1'
 subprocess.run(['ffmpeg','-v','error','-xerror','-i',str(p),'-f','null','-'],check=True,capture_output=True)
 return dict(path=p.name,frames=frames,size=size,fps=24,duration_s=frames/24,sha256=sha(p),full_decode=True)
def main():
 m=json.loads((ROOT/'manifest.json').read_text());q=json.loads((ROOT/'quality_review.json').read_text())
 assert q['manifest_fingerprint']==m['fingerprint']
 for j in m['jobs']:
  r=json.loads((ROOT/'clips'/j['id']/'result.json').read_text());assert r['input_fingerprint']==j['input_fingerprint']
  assert sha(ROOT/'clips'/j['id']/'delivered.mp4')==r['media']['sha256']
  qr=next(x for x in q['clips'] if x['id']==j['id']);assert qr['output_sha256']==r['media']['sha256']
 out=ROOT/'comparison';out.mkdir(exist_ok=True);pieces=[];rows=[]
 for n,seed in enumerate((2026100601,2026100602,2026100603),1):
  cmd=['ffmpeg','-y','-v','error'];filters=[]
  for i,(model,var) in enumerate((('ltx','old'),('ltx','new'),('h3','old'),('h3','new'))):
   j=next(x for x in m['jobs'] if x['model']==model and x['variant']==var and x['seed']==seed)
   cmd+=['-i',str(ROOT/'clips'/j['id']/'delivered.mp4')]
   label=f'{model.upper()} - {"original action" if var=="old" else "continuous action"} - seed 0{n}'
   filters.append(f"[{i}:v]setpts=PTS-STARTPTS,drawbox=x=0:y=0:w=iw:h=30:color=black@0.75:t=fill,drawtext=fontfile={FONT}:text='{label}':x=12:y=7:fontsize=17:fontcolor=white[v{i}]")
  filters.append('[v0][v1]hstack[top];[v2][v3]hstack[bottom];[top][bottom]vstack[v]')
  p=out/f'seed_{n:02d}.mp4';cmd+=['-filter_complex',';'.join(filters),'-map','[v]','-an','-frames:v','120','-r','24','-c:v','libx264','-crf','18','-pix_fmt','yuv420p',str(p)]
  subprocess.run(cmd,check=True);rows.append(verify(p,120,[1344,768]));pieces.append(p)
 listing=out/'concat.txt';listing.write_text(''.join("file '"+p.name+"'\n" for p in pieces))
 result=ROOT/'comparison_15s.mp4'
 subprocess.run(['ffmpeg','-y','-v','error','-f','concat','-safe','0','-i',str(listing),'-c','copy',str(result)],check=True);rows.append(verify(result,360,[1344,768]))
 best=q.get('featured_candidate')
 if best:
  chosen=next(x for x in q['clips'] if x['id']==best)
  assert chosen['quality_status']!='pending_manual'
  source=ROOT/'clips'/best/'delivered.mp4';assert sha(source)==chosen['output_sha256']
  shutil.copy2(source,ROOT/'best_duel.mp4');rows.append(verify(ROOT/'best_duel.mp4',120,[672,384]))
 (ROOT/'assembly_verification.json').write_text(json.dumps(dict(status='PASS',clips=rows,featured_candidate=best,featured_is_production_approved=q.get('featured_is_production_approved',False)),indent=2)+'\n')
 print(json.dumps(dict(status='PASS',outputs=len(rows))))
if __name__=='__main__':main()
