#!/usr/bin/env python3
"""Compose matched-seed comparisons and a clearly scoped diagnostic reel."""
import hashlib,json,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parent
FF='/opt/homebrew/bin/ffmpeg';FP='/opt/homebrew/bin/ffprobe'
font='/System/Library/Fonts/STHeiti Medium.ttc'
def check(path,frames):
 data=json.loads(subprocess.check_output([FP,'-v','error','-count_frames','-show_streams','-show_format','-of','json',str(path)]));v=next(s for s in data['streams'] if s['codec_type']=='video');assert int(v['nb_read_frames'])==frames and v['r_frame_rate']=='24/1'
 subprocess.run([FF,'-v','error','-xerror','-i',str(path),'-f','null','-'],capture_output=True,check=True)
 return dict(sha256=hashlib.sha256(path.read_bytes()).hexdigest(),frames=frames,fps=24,duration_s=frames/24,size=[v['width'],v['height']],full_decode=True)
def main():
 m=json.loads((ROOT/'manifest.json').read_text());out=ROOT/'comparison';out.mkdir(exist_ok=True);clips=[];rows=[]
 for case in m['cases']:
  for seed in (2026100601,2026100602):
   jobs=[next(x for x in m['shots'] if x['case_id']==case['id'] and x['method']==method and x['seed']==seed) for method in ('msr','msr_first','msr_first_last')]
   sources=[ROOT/'clips'/x['id']/'delivered.mp4' for x in jobs];target=out/f'{case["id"]}_{seed}.mp4'
   if not all(x.exists() for x in sources):continue
   if not target.exists():
    command=[FF,'-v','error','-y']
    for src in sources:command+=['-i',str(src)]
    graph=[]
    for i,label in enumerate(['A MSR','B MSR + first','C MSR + first & last']):graph.append(f"[{i}:v]scale=576:324,drawtext=fontfile='{font}':text='{label}':x=12:y=12:fontsize=21:fontcolor=white:box=1:boxcolor=black@0.7[v{i}]")
    title=f'{case["id"]} · {case["title"]} · seed {seed}'
    graph.append(f"[v0][v1][v2]hstack=inputs=3,pad=iw:ih+48:0:48:color=0x171815,drawtext=fontfile='{font}':text='{title}':x=12:y=12:fontsize=23:fontcolor=white[v]")
    command+=['-filter_complex',';'.join(graph),'-map','[v]','-an','-frames:v','120','-r','24','-c:v','libx264','-crf','19','-preset','fast','-pix_fmt','yuv420p','-movflags','+faststart',str(target)]
    subprocess.run(command,capture_output=True,check=True)
   rows.append(dict(case_id=case['id'],seed=seed,jobs=[x['id'] for x in jobs],file=str(target.relative_to(ROOT)),media=check(target,120)));clips.append(target)
 if len(clips)==8:
  listing=out/'concat.txt';listing.write_text(''.join("file '"+str(x)+"'\n" for x in clips));film=ROOT/'comparison_40s.mp4'
  subprocess.run([FF,'-v','error','-y','-f','concat','-safe','0','-i',str(listing),'-c','copy','-movflags','+faststart',str(film)],check=True,capture_output=True);comparison=check(film,960)
 else:comparison=None
 selection_path=ROOT/'selection.json';selected=None
 if selection_path.exists():
  selection=json.loads(selection_path.read_text());ids=selection['diagnostic_candidates'];assert len(ids)==4
  command=[FF,'-v','error','-y'];graph=[]
  for i,jid in enumerate(ids):
   command+=['-i',str(ROOT/'clips'/jid/'delivered.mp4')]
   graph+=[f'[{i}:v]trim=end_frame=120,setpts=PTS-STARTPTS[v{i}]',f'[{i}:a]aresample=32000,atrim=end_sample=160000,asetpts=PTS-STARTPTS[a{i}]']
  graph.append(''.join(f'[v{i}][a{i}]' for i in range(4))+'concat=n=4:v=1:a=1[v][a]')
  target=ROOT/'selected_diagnostic.mp4';command+=['-filter_complex',';'.join(graph),'-map','[v]','-map','[a]','-frames:v','480','-r','24','-c:v','libx264','-crf','19','-preset','fast','-pix_fmt','yuv420p','-c:a','aac','-ar','32000','-ac','2','-b:a','192k','-movflags','+faststart',str(target)]
  subprocess.run(command,check=True,capture_output=True);selected=check(target,480)
 (out/'verification.json').write_text(json.dumps(dict(groups=rows,comparison=comparison,selected_diagnostic=selected),ensure_ascii=False,indent=2)+'\n');print(json.dumps(dict(comparison_groups=len(rows),comparison=comparison,selected=selected)))
if __name__=='__main__':main()
