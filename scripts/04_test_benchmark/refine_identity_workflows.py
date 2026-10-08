#!/usr/bin/env python3
"""Reuse completed H3 Ref2VA captures with the tested identity-specific LTX context."""
import json
from pathlib import Path
import sys
sys.path.insert(0,'/home/admin/sol-h3-spark/models/minimax_h3/Sol-H3-Spark')
from runtime.stage2 import Session
from runtime.workflows import concatenate_clips
from run_troy_workflow_comparison import validate
R=Path('/home/admin/sol-spark-runtime');D=R/'identity_tests_20261003'
paths=json.loads((R/'paths.json').read_text());paths['prompt_cache']=str(D/'prompt_caches/specific_refiner.pt')
prompt=json.loads((D/'ltx_prompts.json').read_text())['specific_refiner']
root=D/'optimized_workflows';root.mkdir(exist_ok=True)
session=Session(paths,str(root),dict(compile=False,fixed_prompt=prompt))
rows=[]
try:
 for cid in ['identity_ref_opening','identity_ref_continuation','identity_ref_new_angle']:
  capture=R/'outputs/api_server_runs/session_20261003-235623_ref2va'/cid/'stage1'
  record=json.loads((capture/'capture.json').read_text())
  output=root/cid
  session.prepare(record['request_id'],str(output))
  result=session.run(str(capture),str(output),record['request_id'])
  trim=int(record.get('continuation',{}).get('trim_frames',0))
  count=121-trim
  video=Path(result['output'])
  if trim:
   import subprocess
   delivered=video.with_name('delivered.mp4')
   subprocess.run(['/home/admin/.local/bin/ffmpeg','-y','-v','error','-i',str(video),
    '-vf',f'trim=start_frame={trim}:end_frame=121,setpts=PTS-STARTPTS',
    '-af',f'atrim=start_sample={round(trim/24*32000)}:end_sample={round(121/24*32000)},asetpts=PTS-STARTPTS',
    '-c:v','libx264','-crf','19','-c:a','aac','-ar','32000','-ac','2',str(delivered)],check=True)
   video=delivered
  media=validate(video,count)
  result.update(delivered_output=str(video),delivered_frames=count,trim_frames=trim,media=media)
  (output/'identity_refinement_result.json').write_text(json.dumps(result,indent=2))
  rows.append(result)
  print(json.dumps(dict(status='PASS',case_id=cid,output=str(video),frames=count)),flush=True)
finally:session.close()
films=[]
for name,pair in [('continuous',rows[:2]),('storyboard',[rows[0],rows[2]])]:
 video=root/(name+'.mp4')
 concatenate_clips([r['delivered_output'] for r in pair],[r['delivered_frames'] for r in pair],video)
 films.append(dict(name=name,output=str(video),media=validate(video,sum(r['delivered_frames'] for r in pair))))
(root/'comparison.json').write_text(json.dumps(dict(status='PASS',films=films,clips=rows),indent=2))
print(json.dumps(dict(status='PASS',films=films)),flush=True)
