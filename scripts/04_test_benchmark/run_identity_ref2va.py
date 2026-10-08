#!/usr/bin/env python3
"""Run identical-asset H3 Ref2VA independent and motion-prefix identity trials."""
import json
from pathlib import Path
import sys
import time
sys.path.insert(0,'/home/admin/sol-h3-spark/models/minimax_h3/Sol-H3-Spark')
from run_troy_workflow_comparison import request, validate
from runtime.workflows import concatenate_clips

ROOT=Path('/home/admin/sol-spark-runtime/identity_tests_20261003')
ASSETS=ROOT/'assets'
DEFINITIONS='''subject_definitions:
<Subject 1> is the bearded Greek warrior in <Picture 1>, with short dark hair, engraved bronze cuirass, red cloak and brown sandals.
<Subject 2> is the clean-shaven Greek warrior in <Picture 2>, with curly black hair, engraved bronze cuirass, blue cloak and brown sandals.
<Subject 3> is the equipment in <Picture 3>: two straight silver swords, and one round bronze shield belonging only to <Subject 2>. Both men carry a sword in their right hand; the red warrior's left hand remains empty and the blue warrior's left hand carries the shield.
<Subject 4> is the Troy courtyard in <Picture 4>, with a large stationary wooden horse sculpture assembled from timber planks, stone walls, sand and burning braziers.
<Picture 5> is the shot composition reference with red warrior left, blue warrior right and the wooden horse behind them.
summary: [reference generation] Two consistent Greek warriors perform a controlled stage duel in the Troy courtyard, filmed like a 1970s Shaw Brothers studio action movie.
retention_analysis:
<Subject 1>: fully_preserved - preserve face, beard, hair, armor and red cloak.
<Subject 2>: fully_preserved - preserve face, hair, armor and blue cloak.
<Subject 3>: fully_preserved - exactly two swords and one shield, with unchanged ownership throughout.
<Subject 4>: fully_preserved - preserve the wooden construction, courtyard and torch lighting.
<Picture 5>: partially_preserved - preserve blocking and lighting while changing camera framing only as specified.
detailed_description: The target video uses warm torchlight, a theatrical studio set, saturated red and blue cloaks, 35mm grain and clear Shaw Brothers sword choreography.
'''
SOUND=' overall_soundscape: Quiet night wind, crackling braziers, sandal scuffs and metallic sword clashes. No dialogue. non_diegetic_music: None.'


def main():
 out=ROOT/'ref2va';out.mkdir(exist_ok=True)
 deadline=time.monotonic()+1800
 while True:
  try:
   status=request('http://127.0.0.1:8090','/api/status',timeout=5)
   if status['status']=='READY':break
  except (OSError,RuntimeError):pass
  if time.monotonic()>deadline:raise TimeoutError('Ref2VA server not ready')
  time.sleep(10)
 assert status['task']=='ref2va',status
 (out/'status_before.json').write_text(json.dumps(status,indent=2))
 references=[dict(type='image',path=str(ASSETS/f)) for f in
  ['red_identity.png','blue_identity.png','equipment.png','setting.png','board.png']]
 actions=[
  '[Shot 1] One uninterrupted five-second waist-height wide shot. The red warrior advances two measured steps and swings his right-hand sword diagonally. The blue warrior parries with his right-hand sword while holding his round shield steadily in his left hand. They circle and reset their stance. The camera tracks slowly right, keeping both whole bodies and both faces readable. Preserve their bronze cuirasses, hair, faces and cloak colors; keep the timber horse completely stationary in the background.',
  '[Shot 1] Continue the previous continuous waist-height tracking shot, retaining exact camera speed and movement from the previous action context. The blue warrior steps forward with his shield on his left arm and thrusts his right-hand sword. The red warrior, whose left hand is empty, parries with his right-hand sword, pivots and counters with a controlled broad sword sweep. Both actors keep their original faces, bronze cuirasses, cloaks and weapons throughout. The timber horse remains stationary behind them.',
  '[Shot 1] A new independent low-angle medium-wide shot. The same red warrior stands on the left and the same blue warrior stands on the right. Hold this closer camera framing, making their faces and engraved armor readable. The blue warrior raises his left-hand round bronze shield to block the red warrior right-hand sword strike, then counters with his own right-hand sword. The red warrior steps back and parries. Preserve both faces, beards, hair, red and blue cloaks, the two silver swords and the single blue-warrior shield. The wooden timber horse remains behind them.'
 ]
 ids=['identity_ref_opening','identity_ref_continuation','identity_ref_new_angle']
 rows=[]
 for i,(cid,action) in enumerate(zip(ids,actions)):
  case=dict(case_id=cid,prompt=DEFINITIONS+action+SOUND,references=references,
   seed=2026100301+i,duration_s=5,mode='final',transition='continue' if i==1 else 'independent')
  if i==1:case.update(previous_clip_id=ids[0],context_frames=22,audio_context_frames=24)
  (out/(cid+'_request.json')).write_text(json.dumps(case,indent=2))
  print(json.dumps(dict(status='GENERATING',case_id=cid)),flush=True)
  row=request('http://127.0.0.1:8090','/api/generate',case)
  validate(Path(row['video_path']),row['delivered_frames'])
  (out/(cid+'_response.json')).write_text(json.dumps(row,indent=2))
  rows.append(row)
  print(json.dumps(dict(status='PASS',case_id=cid,output=row['video_path'],frames=row['delivered_frames'])),flush=True)
 assert rows[1]['continuation']['frozen_prefix_verified']
 for name,pair in [('continuous',[rows[0],rows[1]]),('storyboard',[rows[0],rows[2]])]:
  video=out/(name+'.mp4')
  concatenate_clips([r['video_path'] for r in pair],[r['delivered_frames'] for r in pair],video)
  validate(video,sum(r['delivered_frames'] for r in pair))
 (out/'comparison.json').write_text(json.dumps(dict(status='PASS',clips=rows),indent=2))

if __name__=='__main__':main()
