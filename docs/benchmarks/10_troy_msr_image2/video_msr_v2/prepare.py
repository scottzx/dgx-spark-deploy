#!/usr/bin/env python3
"""Freeze four regression specs and self-hosted Qwen edit requests."""
import hashlib,json,shutil
from pathlib import Path
ROOT=Path(__file__).resolve().parent
OLD=ROOT.parent/'video_msr_v1'
REMOTE='/home/admin/sol-spark-runtime/troy_msr_controls_20261006'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def save(p,x):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n')
old=json.loads((OLD/'manifest.json').read_text())
source={x['id']:x for x in old['shots']}
common='Edit the supplied film still into a single photorealistic 1970s Shaw Brothers historical Troy film frame. Preserve the identical camera, framing, fixed masonry, lighting, actor faces, armor and cloth textures. Night, practical amber torches and blue moonlight. No text, panels, collage, modern objects, blood, wounds, extra limbs or duplicate heroes. '
specs=[
 dict(id='S10',title='奥德修斯向下爬梯',actors=['odysseus'],camera='locked full-body medium wide side view',
 start=dict(actor='one Odysseus on upper ladder; torso faces wooden horse; hands grip both rails; feet on upper rungs',hatch='open upward, top hinge',ladder='one fixed ladder',gate='closed'),
 end=dict(actor='same Odysseus exactly two rungs lower, facing horse, hands grip rails, feet still on ladder',hatch='unchanged',ladder='unchanged',gate='closed'),
 invariants=['one Odysseus, no duplicates','no shield','sword stays sheathed at left hip','one rigid wooden horse facing right','one ladder and one hatch','camera stationary'],
 acceptance=['pelvis visibly moves down at least two rungs','no upward travel or direction reversal','both hands alternate secure ladder grips','identity, sword sheath and horse remain stable'],
 edits=[
 'Preserve the supplied composition and the ONE ladder. Pose ONE Odysseus facing the horse with his back three-quarters to camera, head looking down at the rungs. His torso is at the upper third of the ladder just below the open hatch. Both hands hold separate ladder rails, both feet supported on upper rungs. Keep his indigo cloak, dark curly hair and short beard. His sword is sheathed at LEFT hip, he has NO shield. The feet must remain clearly visible. Horse and wheels stationary. Closed gate left, fountain right.',
 'Use image 1 as the exact start frame. Change ONLY Odysseus to the same man TWO RUNG SPACINGS LOWER on the same ladder. His pelvis, head, hands and both feet shift downward together. Both feet still stand on the lower rungs ABOVE the ground, his torso still faces the horse, both hands hold the rails. Sword remains sheathed LEFT, NO shield. The upward-open hatch, ladder feet, platform, wheels, gate, fountain, fixed camera and lighting must be identical. Show the whole downward change clearly without changing scale.']),
 dict(id='S15',title='剑矛交锋对照',actors=['odysseus','guard','greeks','trojans'],camera='locked full-body medium wide',
 start=dict(odysseus='left foreground right-hand sword raised before parry; left hand empty',guard='right foreground spear thrust beginning; left shield',extras='two background fighting pairs',gate='closed'),
 end=dict(odysseus='same left foreground sword high right after parry; left hand empty',guard='same right foreground recoils one half-step after spear deflection; shield left',extras='same two background pairs at next fight phase',gate='closed'),
 invariants=['six distinct people','Odysseus has no shield','guard keeps right spear and left shield','two background Greek/Trojan pairs','closed gate and camera fixed'],
 acceptance=['visible spear thrust and sword parry','no equipment transfer or duplication','both background pairs continue combat','lead faces and gate preserved'],
 edits=[
 'Exactly SIX people, preserving reference cast. Foreground LEFT Odysseus indigo cloak, sword in RIGHT hand lifted diagonally ready to parry; LEFT hand EMPTY, NO shield. Foreground RIGHT pointed-helmet Trojan in ochre with rust cloak, spear in RIGHT hand beginning a thrust toward Odysseus, ONE shield in LEFT hand. Their weapons have NOT touched yet; spear tip and sword are visibly separate. Background exactly two separate fighting pairs: two blue-gray Greeks facing two ochre/rust Trojans. Closed double gate. Preserve background people positions and distance.',
 'Use image 1 as exact start composition, same SIX people. Show the next instant AFTER one sword parry: Odysseus LEFT stays in place, his RIGHT sword now raised diagonally higher, LEFT hand still EMPTY and no shield. The foreground guard RIGHT recoils half a step right, leaning back, his RIGHT spear deflected upward, his LEFT hand still holds the same shield. Maintain the gap between fighters, no gore. The same two background pairs each move into a different sword-block pose. Gate and camera unchanged.']),
 dict(id='S16',title='双人抬闩与掩护',actors=['odysseus','soldier','greeks','trojans'],camera='locked wide inner-gate view',
 start=dict(bar='one wooden bar horizontal and seated in two wall brackets',operators='Odysseus left and young Greek right grip bar with both hands',soldier_shield='strapped flat on back',swords='both sheathed left',gate='closed',extras='three Greeks and two Trojans fighting at right'),
 end=dict(bar='same bar lifted 25cm vertically clear above both brackets, held horizontally in front of closed gate',operators='same two actors, both hands still carry bar',soldier_shield='same flat back shield',swords='both sheathed',gate='closed',extras='same five cover fighters continue at right'),
 invariants=['seven distinct actors total','operators never draw swords','young soldier shield stays on back','Odysseus no shield','one bar only','both gate leaves closed','no camera move'],
 acceptance=['two operators jointly lift the bar clear of both brackets','four hands stay on bar','no shield appears in operators hands','cover fighters engage throughout','gate remains closed'],
 edits=[
 'Inner side of CLOSED wooden double gate, same masonry, exactly SEVEN people. Two operators at the gate: LEFT Odysseus indigo cloak NO shield, RIGHT young clean-shaven Greek blue-gray tunic with ONE shield strapped FLAT on his BACK. BOTH swords sheathed LEFT. Both operators grip the SAME heavy wooden gate bar with BOTH hands. The single bar is perfectly HORIZONTAL at chest height and still seated securely in TWO side-wall brackets. It has not been removed. Right side: exactly five distinct cover fighters (three blue-gray Greeks and two ochre/rust Trojans) in sword-and-shield combat. Operators have no handheld weapon. Keep all four operator hands readable and all feet grounded.',
 'Use image 1 as exact start composition. Change ONLY the bar and operators arms: the SAME single wooden bar is lifted VERTICALLY 25 centimeters ABOVE and CLEAR OF BOTH empty wall brackets, still HORIZONTAL across the CLOSED gate, held by FOUR hands of the same two operators. Their feet and bodies stay in the same positions, swords still sheathed LEFT, young Greek shield strapped flat on BACK, Odysseus has NO shield. Do not turn the bar vertical or carry it away. The same five right-side fighters advance to the next sword-and-shield pose. Closed gate, stone walls, framing and lighting unchanged.']),
 dict(id='S20',title='大军团持续群战',actors=['greeks','trojans'],camera='locked elevated wide master shot; no crane this regression',
 start=dict(foreground='two readable Greek/Trojan sword-shield combat pairs, attack preparation',middle='blue-gray and rust-colored infantry fighting around both sides of horse',background='dense opposing armies clash between open left gate and right fountain',horse='one rigid horse, hatch up, ladder down'),
 end=dict(foreground='same four foreground fighters after blocked strikes, half-step recoil',middle='same armies advance and recoil during combat',background='same dense clash with weapons raised',horse='unchanged'),
 invariants=['no named heroes','Greeks blue-gray, Trojans ochre/rust','one horse, one hatch, one ladder','gate open on left and fountain on right','foreground, middle and background combat','locked camera'],
 acceptance=['both foreground pairs visibly strike, block and recoil','middle and rear lines fight rather than parade or stand still','factions visually distinct','no living horse motion or hero duplication','spatial landmarks remain fixed'],
 edits=[
 'Anonymous mass army battle. Preserve the wide frame, ONE rigid wooden horse facing RIGHT center, one upward-open hatch and one ladder, open gate LEFT, fountain RIGHT. NO named heroes. Improve clear faction colors: all Greeks blue-gray cloth and bronze, all Trojans ochre tunics and rust-red short capes. In the foreground exactly TWO readable opposed fighting pairs: Greek at left versus Trojan at right in each pair, RIGHT-hand sword, LEFT-hand shield, swords raised before strike and shields braced. Behind them many different infantry visibly fight in staggered opposing pairs across middle and rear zones, with crossing swords and defensive shields; no symmetrical parade, no line facing camera. Keep camera, stonework, horse scale and illumination fixed.',
 'Use image 1 as exact composition with identical horse, hatch, ladder, open gate, fountain and camera. Show same anonymous armies ONE BEAT LATER in continuous battle. The SAME TWO foreground pairs have just blocked sword strikes: swords touch shields, blue-gray attackers lean forward, ochre/rust defenders recoil HALF A STEP to right, all four keep swords RIGHT and shields LEFT. Middle and background fighters also show the next active combat phase with thrusts, blocks and recoils, not walking or standing ranks. Keep faction colors and density, no heroes, no gore.'])]
for spec in specs:
 slots=source[spec['id']]['slots']
 for slot in slots:
  target=ROOT/slot['file'];target.parent.mkdir(parents=True,exist_ok=True)
  if not target.exists():shutil.copy2(OLD/slot['file'],target)
 for phase,text in zip(('start','end'),spec.pop('edits')):
  refs=[f'inputs/board_{spec["id"]}.png'] if phase=='start' else [f'keyframes/{spec["id"]}_start.png']
  # single composition reference prevents a portrait being mistaken for an additional actor
  request=dict(id=f'{spec["id"]}_{phase}',title=spec['title'],output=f'keyframes/{spec["id"]}_{phase}.png',references=refs,prompt=common+text,seed=2026100600+int(spec['id'][1:])*2+(phase=='end'))
  save(ROOT/'requests'/f'{spec["id"]}_{phase}.json',request)
save(ROOT/'shot_specs.json',dict(version=2,remote_root=REMOTE,cases=specs,conditioning_methods=['msr','msr_first','msr_first_last'],seeds=[2026100601,2026100602],frames=121,fps=24,steps=8,delivery_frames=120,native_size=[768,448],delivery_size=[768,432],camera_change_from_v1='locked in all four regression cases',quality_gate='manual criteria; technical decode PASS does not imply creative acceptance'))
print('Prepared four ShotSpecs and eight Qwen requests')
