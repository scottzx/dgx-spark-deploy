#!/usr/bin/env python3
"""Content-addressed jobs: conditioning is the only A/B/C variable."""
import hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parent
OLD=ROOT.parent/'video_msr_v1'
def digest(x):return hashlib.sha256(json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
spec=json.loads((ROOT/'shot_specs.json').read_text());old=json.loads((OLD/'manifest.json').read_text());jobs=[];cases=[]
selected=json.loads((ROOT/'selected_keyframes.json').read_text()) if (ROOT/'selected_keyframes.json').exists() else {}
style='A five-second continuous photorealistic 1970s Shaw Brothers historical Troy film shot. Practical night lighting: warm amber torches and cold blue moonlight, gritty bronze, rough wood and cloth. The camera is locked off throughout: no zoom, pan or crane. No dialogue, no music, only diegetic footsteps, armor, wood or sword sounds. No captions, no blood or visible wounds. '
actions={
'S10':'At the start ONE Odysseus is on the upper third of ONE ladder facing the wooden horse, with both hands gripping its rails. He steadily DESCENDS DOWNWARD by exactly TWO rungs, alternating one hand and one foot, lowering his pelvis throughout. He finishes on lower rungs still above ground and still facing the horse. Do not ascend, reverse direction, turn to camera, jump or leave the ladder. Sword remains sheathed at LEFT hip, NO shield. One upward-open top-hinged hatch, one rigid horse facing right on fixed wheels, closed gate left, fountain right. The horse, hatch and ladder are motionless.',
'S15':'Exactly SIX different people: Odysseus foreground LEFT with RIGHT sword and LEFT hand EMPTY, no shield; foreground RIGHT Trojan guard with pointed helmet, ochre tunic and rust cloak, RIGHT spear and LEFT shield. The guard thrusts once; Odysseus parries the spear upward with his sword. The guard recoils half a step to the right. The same two background Greek/Trojan pairs continuously strike and block. Each keeps weapons in its original hands. Closed double gate throughout. No additional people or equipment transfers.',
'S16':'Exactly SEVEN different people. At the closed double gate, LEFT Odysseus in indigo with NO shield and RIGHT young clean-shaven Greek with ONE shield strapped flat on his BACK each grip ONE horizontal wooden gate bar with BOTH hands. Both swords remain sheathed LEFT. Together they lift the SAME heavy bar VERTICALLY 25 centimeters CLEAR ABOVE BOTH side-wall brackets. The bar remains HORIZONTAL in their FOUR hands in front of the still CLOSED gate until the last frame. They do not carry it away, turn it vertical, draw swords or open the gate. At right exactly three blue-gray Greeks and two ochre/rust Trojans continue sword and shield fighting to cover the operators. Grounded feet, constant cast and equipment.',
'S20':'A sustained anonymous large-army battle, with no named heroes. Greeks wear blue-gray cloth and bronze armor; Trojans wear ochre tunics and rust-red capes. Foreground TWO distinct opposed pairs keep RIGHT swords and LEFT shields: blue-gray Greek left, ochre/rust Trojan right. Both pairs strike, block and recoil through the shot; attackers lean forward while defenders recoil half a step. Middle and background infantry continuously clash in staggered opposing pairs on both sides of the horse, with thrusts, defensive shields and recoils. No parade, idle formation or walking away. ONE motionless rigid wooden horse center faces right, ONE hatch stays raised, ONE ladder stays fixed. Gate at LEFT remains OPEN; fountain stays at RIGHT. Maintain all three depths of action and clear faction colors.'}
for case in spec['cases']:
 cid=case['id'];original=next(x for x in old['shots'] if x['id']==cid);slots=[]
 for slot in original['slots']:
  s={k:slot[k] for k in ['slot','id','kind','role','file']}
  if s['id']=='board':s['file']=selected.get(cid,{}).get('start',f'keyframes/{cid}_start.png');s['role']='start-state composition reference; same cast, not additional people'
  s['sha256']=sha(ROOT/s['file']);slots.append(s)
 frames={phase:dict(file=selected.get(cid,{}).get(phase,f'keyframes/{cid}_{phase}.png'),sha256=sha(ROOT/selected.get(cid,{}).get(phase,f'keyframes/{cid}_{phase}.png')),frame_index=0 if phase=='start' else 120,strength=1.) for phase in ('start','end')}
 labels=' '.join(f'Picture {s["slot"]}: {s["role"]}.' for s in slots)
 prompt=style+labels+' '+actions[cid]
 psha=hashlib.sha256(prompt.encode()).hexdigest();(ROOT/'prompts').mkdir(exist_ok=True);(ROOT/'prompts'/f'{cid}.txt').write_text(prompt+'\n')
 inputs=dict(shot_spec=case,prompt_sha256=psha,slots=slots,native_size=[768,448],frames=121,fps=24,steps=8,msr_strength=1.,distilled_strength=1.,adapter_revision='03061c18f8a79d26f3c63931dd8e28f5e5d872a6',ltx_revision='d151147788a9284cca791edc6ce898007e727fe6')
 for method in spec['conditioning_methods']:
  for seed in spec['seeds']:
   temporal=[] if method=='msr' else [frames['start']] if method=='msr_first' else list(frames.values())
   job=dict(**inputs,case_id=cid,id=f'{cid}_{method}_{seed}',title=case['title'],method=method,seed=seed,temporal=temporal,prompt=prompt)
   job['input_fingerprint']=digest(job);jobs.append(job)
 cases.append(dict(id=cid,title=case['title'],spec=case,keyframes=frames))
manifest=dict(version=2,remote_root=spec['remote_root'],method='controlled_msr_temporal_keyframe_regression',steps=8,fps=24,frames=2880,shots=jobs,cases=cases,comparison='24 NEW clips: same revised prompt, MSR refs, seed, duration and weights within each case. v1 is historical reference only; no paired inference from unmatched old clips.',endpoint='last guide at native pixel frame120 (5.0s); delivered clip120 frames ends at4.958s',quality_gate='technical PASS plus manual hard-state and motion review required; no automatic creative selection')
manifest['fingerprint']=digest(manifest)
p=ROOT/'manifest.json'
if p.exists() and json.loads(p.read_text())['fingerprint']!=manifest['fingerprint']:raise RuntimeError('Frozen manifest differs; new version required')
p.write_text(json.dumps(manifest,indent=2,ensure_ascii=False)+'\n');print(manifest['fingerprint'],len(jobs))
