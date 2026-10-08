#!/usr/bin/env python3
"""Freeze the selected twenty-shot story into typed MSR video references."""
import hashlib
import json
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT.parent
REMOTE = '/home/admin/sol-spark-runtime/troy_image2_msr_20261005'
ASSETS = {
    'sinon': ('character', 'assets/characters/sinon_v1.png', 'Sinon, an unarmed persuasive Greek captive'),
    'odysseus': ('character', 'assets/characters/odysseus_v1.png', 'Odysseus, dark short wavy hair and trimmed beard, indigo cloak, no shield'),
    'agamemnon': ('character', 'assets/characters/agamemnon_v1.png', 'Agamemnon, older stocky gray-black bearded commander, lion cuirass, crimson cloak, no shield'),
    'guard': ('character', 'assets/characters/trojan_guard_01_v1.png', 'the Trojan guard, pointed bronze helmet, ochre armor and rust cloak'),
    'worker': ('character', 'assets/characters/trojan_worker_01_v1.png', 'the unarmed Trojan rope-pulling worker'),
    'citizen': ('character', 'assets/characters/trojan_citizen_01_v1.png', 'the unarmed Trojan woman citizen'),
    'soldier': ('character', 'assets/characters/greek_soldier_01_v1.png', 'the young clean-shaven Greek soldier, gray-blue tunic and bronze armor, exactly one shield'),
    'greeks': ('group', 'assets/groups/greek_infantry_v1.png', 'Greek infantry costume reference: gray-blue cloth and bronze armor; different individual faces'),
    'trojans': ('group', 'assets/groups/trojan_defenders_v1.png', 'Trojan defenders costume reference: ochre and rust cloth, bronze armor; different individual faces'),
    'horse': ('prop', 'assets/scenes/trojan_horse_v1.png', 'rigid wooden horse design on one four-wheeled platform, facing right'),
    'gate': ('scene', 'assets/scenes/gate_day_v1.png', 'sandstone city-gate exterior architecture'),
    'day': ('scene', 'assets/scenes/square_day_v1.png', 'square architecture by day: gate rear left, fountain right'),
    'dusk': ('scene', 'assets/scenes/square_dusk_v1.png', 'square architecture at dusk: gate rear left, fountain right'),
}
SLOTS = [
    ['sinon','guard','citizen','gate'], ['sinon','guard','worker','gate'],
    ['worker','horse','gate'], ['worker','citizen','day'], ['worker','citizen','dusk'],
    ['guard'], ['horse'], ['odysseus','horse'], ['odysseus','horse'],
    ['odysseus','horse'], ['odysseus','horse'], ['odysseus','soldier','horse'],
    ['odysseus','soldier','greeks'], ['guard','trojans'],
    ['odysseus','guard','greeks','trojans'], ['odysseus','soldier','greeks','trojans'],
    ['agamemnon','greeks'], ['odysseus','soldier','greeks','trojans'],
    ['agamemnon','greeks','trojans'], ['greeks','trojans'],
]
ACTIONS = [
    ('Exactly three people. Sinon left opens his empty hands and gestures calmly toward the wooden horse outside the open gate. The guard right listens and turns his head, keeping his right-hand spear upright and his left-hand shield steady. The woman farther back watches. No one speaks or moves their lips in speech. The horse hatch remains closed and no ladder is visible.', 'Slow medium push-in; wind and soft cloth rustle.'),
    ('Exactly three people: Sinon, the guard, and the worker. The guard nods once and steps aside while still holding spear right and shield left. The worker grasps the hauling rope with both hands and leans to take its weight. Sinon lowers his empty hands. The rope leads toward the offscreen horse. Open guarded gate; no Greek army.', 'Steady medium shot; taut rope fibers, footsteps and quiet armor movement.'),
    ('One worker is visible only as legs and lower torso. He pulls the taut rope with both hands off the top of frame. The near wooden wheel rotates slowly across the stone threshold into the gateway. The wooden horse legs remain rigid on the platform; it never walks like a living animal. Closed hatch, no ladder.', 'Low close tracking shot following the turning wheel; wooden wheel thuds and shoes scrape stone.'),
    ('Exactly three people: the worker, one different anonymous unarmed worker, and the woman citizen. Two workers steadily pull the rigid wooden horse on its four-wheel platform into the square, then slow it to a stop at center-left. The woman walks alongside at a safe distance. Horse faces right. Gate rear left, fountain right; closed hatch, no ladder, no Greek soldiers.', 'Wide slow lateral track; wheels turn, rope strains, footsteps and fountain water.'),
    ('Exactly two people: the worker and woman citizen. At dusk the horse is already parked; its wheels stop, the hauling ropes slacken. The two people walk away from the horse toward the edge of the square. Horse remains rigid and motionless, facing right, hatch closed, ladder hidden.', 'Wide static dusk shot; departing footsteps, fountain and evening wind.'),
    ('Exactly one guard is inside the gate at dusk. His spear and shield are set aside and both hands are empty except for gripping the wooden door and bar. He settles the two wooden leaves firmly closed and presses one horizontal locking bar securely into its sockets. Finish with the gate fully closed and locked. No extra arm, no other people.', 'Medium stable shot; heavy wood creak and one low locking-bar thud.'),
    ('No people at all. Empty square at night. The wooden horse stands center-left facing right, hatch shut, no ladder. City gate rear left is firmly closed. Fountain right flows and two braziers flicker. Nothing emerges yet.', 'Very slow wide push-in; blue night light, amber flames, fountain and night wind only.'),
    ('Exactly one Odysseus, only his head and torso inside the single camera-facing belly hatch. He lifts the TOP-hinged flap upward with his hands, pauses and peers cautiously into the empty square. His sword stays sheathed at his anatomical left hip; no shield. No ladder is present yet and nobody stands on the ground. Gate remains closed.', 'Close slow push toward the hatch; restrained wood hinge creak, cloth and distant fire.'),
    ('Exactly one Odysseus stays in the open hatch. With both empty hands he lowers and steadies one wooden ladder from the hatch to clear stone paving away from the platform wheels. The top-hinged flap stays raised. Sword sheathed at anatomical left hip, no shield; no second face in the hatch and nobody on the ground.', 'Medium steady shot; ladder scrapes the hatch edge, then its feet touch stone.'),
    ('Exactly one Odysseus is halfway down the single ladder, facing the wooden horse. Both hands grip the rails as he carefully descends two rungs, one foot at a time. Sword remains sheathed at his anatomical left hip, no shield. Hatch is open and empty above him. The horse and its wheels do not move; gate closed.', 'Medium lateral shot with a small downward follow; rung creaks and quiet leather and bronze movement.'),
    ('Exactly one Odysseus completes the last ladder step onto the stone paving, turns slightly toward the closed gate, then raises one EMPTY hand in a quiet signal toward the open, empty hatch. Sword remains sheathed at his anatomical left hip, no shield. One ladder only, no duplicate figure inside the horse.', 'Medium gentle follow; one soft footfall, fountain water and night wind.'),
    ('Exactly two people. Odysseus stands on the paving watching the closed gate with empty hands and his sword sheathed at anatomical left hip, no shield. The young Greek soldier faces the horse and descends the same single ladder, holding both rails; his one shield is strapped on his BACK and sword sheathed at his anatomical left hip. No one else inside the hatch.', 'Medium steady shot; rung creaks, muted armor and careful footfalls.'),
    ('Exactly six Greek people: one Odysseus, one young Greek soldier, and four distinct anonymous Greek infantry. All are already on the paving and crouch-advance together toward the closed gate. Odysseus holds one drawn sword in his RIGHT hand, LEFT hand empty, no shield. The young soldier holds one shield LEFT and one sword RIGHT. Empty hatch and single ladder remain behind them.', 'Low medium lateral tracking; a brief sword draw followed by synchronized quiet steps and shield straps.'),
    ('Exactly six Trojan defenders: one pointed-helmet guard and five distinct anonymous soldiers. The guard notices the offscreen attackers, turns sharply and raises his right-hand spear while holding his left-hand shield. His companions run a few steps into a defensive line inside the closed gate. The horizontal locking bar stays seated. No Greek appears in this shot.', 'Medium quick pan following the guard, settling on the defense; running feet, armor and a distant bronze alarm strike, no shouted words.'),
    ('Exactly six people in three clear fighting pairs inside the closed gate. Foreground Odysseus parries the Trojan guard spear with one sword in his RIGHT hand, LEFT hand empty, no shield. Guard has spear RIGHT and shield LEFT. Behind them two Greek infantry exchange short controlled sword and shield blows with two Trojan defenders. Each pair strikes, blocks and recoils; distinct bodies keep their own weapons. Gate bar stays seated; no gore.', 'Medium restrained handheld lateral movement; sharp metal contacts, shield knocks, hurried feet and nonverbal breathing.'),
    ('Exactly seven people. Odysseus and the young Greek soldier operate the ONE horizontal gate bar together. Both have swords fully SHEATHED at anatomical LEFT hips; Odysseus has no shield, young soldier one shield strapped on his BACK. Each uses both hands to lift the same heavy bar clear of the sockets and carry it toward the left wall. The two door leaves remain fully CLOSED. Two Greek covering soldiers fight three Trojan defenders in the side forecourt, all inside the gate. No extra operator or arm.', 'Medium stable lateral view; wooden bar scrapes and thuds, continuous off-to-the-side sword and shield clashes.'),
    ('One Agamemnon at the front left, with dozens of distinct Greek soldiers in several ranks outside Troy at night. Agamemnon raises one drawn sword in his RIGHT hand as a forward signal; LEFT hand empty, no shield. Soldiers tighten their formation and take one deliberate step. The massive gate is still closed in the right background. Plain crimson banners flutter. No Trojan, horse, fountain or Odysseus appears.', 'Wide slow forward move with layered foreground, middle and rear ranks; disciplined feet, shield and spear rattle, night wind, no chanting.'),
    ('Exactly seven people as in the bar-removal shot. The locking bar is already removed. Odysseus at the left leaf and the young Greek soldier at the right leaf each push their own heavy door using BOTH empty hands, widening one central gap to reveal blue night outside. Both swords remain SHEATHED at anatomical LEFT hips; young soldier shield on BACK, Odysseus no shield. Two Greek covering soldiers continue fighting three Trojan defenders at the side, all inside. No army crosses the threshold yet.', 'Medium steady camera; heavy hinge creaks, wood friction and side-forecourt shield and sword clashes.'),
    ('Massed Greek infantry surge from outside through the now fully OPEN gate into the interior. One Agamemnon in crimson is at the threshold behind the first fighters, moving forward with one sword RIGHT, LEFT empty, no shield. Dozens of Greek gray-blue soldiers in continuous rear ranks collide with an ochre/rust Trojan shield line. Foreground pairs exchange short thrusts, shield blocks and recoil; middle and background ranks keep advancing. Odysseus and the young named soldier remain offscreen. Plain crimson banners, no gore.', 'Wide low forward tracking through the interior forecourt; dense running footsteps, shield-wall impact and repeated metal blows, no speech or music.'),
    ('Large square battle with many dozens of distinct ANONYMOUS soldiers on both sides; all named heroes stay OFFSCREEN. Greek gray-blue ranks keep entering from the open gate at rear LEFT and press the ochre/rust Trojan line beside the fountain at RIGHT. Several readable foreground pairs exchange sword or spear strikes and shield blocks; middle shield formations push and rear ranks continue flowing in. Wooden horse stays parked center-left facing RIGHT, hatch open and empty, one ladder untouched, legs and wheels rigid. Maintain clear faction colors, plain crimson banners, no gore.', 'Wide camera slowly rises slightly to reveal the sustained multi-layer battle; many footsteps and repeated shield, sword and spear impacts over faint fountain and fire, no chanting.'),
]

def digest(path):
    with path.open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()

def main():
    source_plan = ROOT/'source_storyboard_plan.json'
    if not source_plan.exists():
        source_plan = SOURCE/'storyboard_v2/shotlist.json'
    original = json.loads(source_plan.read_text())
    assert len(original['shots']) == len(SLOTS) == len(ACTIONS) == 20
    (ROOT/'inputs').mkdir(exist_ok=True)
    (ROOT/'prompts').mkdir(exist_ok=True)
    shots = []
    for i, (source, names, action) in enumerate(zip(original['shots'], SLOTS, ACTIONS), 1):
        entries = [(name, *ASSETS[name]) for name in names]
        entries.append(('board', 'staging', source['frame_file'], 'this shot staging, composition, lighting and current gate/hatch/ladder state; the visible people are the same referenced actors, not additional copies'))
        slots = []
        for j, (name, kind, relative, role) in enumerate(entries, 1):
            path = SOURCE/relative
            target = ROOT/'inputs'/('board_'+source['id']+'.png' if name == 'board' else name+'.png')
            shutil.copyfile(path, target)
            slots.append(dict(slot=j, id=name, kind=kind, role=role, source_file=relative,
                              file=str(target.relative_to(ROOT)), remote_file=REMOTE+'/'+str(target.relative_to(ROOT)), sha256=digest(target)))
        prompt = '\n'.join(f"pic{x['slot']} is {x['role']}." for x in slots)
        prompt += '\nGenerate one continuous five-second live-action shot. '+action[0]
        prompt += '\nCamera and synchronized sound: '+action[1]
        prompt += '\nPhotorealistic 1970s Shaw Brothers historical studio film set in ancient Troy. Handmade sandstone and timber, woven fabrics, aged bronze, saturated restrained 35mm colors, fine film grain. Match reference faces and costumes. At night use readable blue ambient light and warm amber fire. Respect the action-specific weapon and gate states even when identity plates show other poses. Reference group images describe clothing, not extra people to add. No duplicate named person, extra limbs, panels, captions, writing, watermark, modern objects, fantasy magic or Achilles. No dialogue, intelligible speech, singing, music or score. Only synchronized physical action sounds and environmental ambience.'
        (ROOT/'prompts'/(source['id']+'.txt')).write_text(prompt+'\n')
        shots.append(dict(id=source['id'], index=i, title=source['title'], scene=source['scene'], seed=2026100500+i,
            start_s=(i-1)*5, end_s=i*5, delivered_frames=120, native_frames=121, prompt=prompt,
            prompt_sha256=hashlib.sha256(prompt.encode()).hexdigest(), slots=slots, storyboard_file=source['frame_file'],
            motion=action[0], camera_sound=action[1]))
    manifest = dict(title='木马计：夺门 · MSR V2 测试片 V1', status='prepared', remote_root=REMOTE,
        source_story='storyboard_v2/shotlist.json', source_story_sha256=digest(source_plan),
        method='LTX-2.5 native + Licon MSR V2 + distilled LoRA', source_benchmark='09_troy_climax/msr',
        steps=8, msr_strength=1.0, distilled_strength=1.0, native_size=[768,448], delivery_size=[768,432],
        delivery_crop='remove 8 pixels from top and bottom', fps=24, frames=2400, duration_s=100,
        audio=dict(dialogue=False,music=False,ambience=True,source='native generated audio, no external soundtrack'),
        transition='independent shots, chronological hard cuts', samples_per_shot=1, shots=shots,
        image_policy='Reuse selected existing assets and boards; no new image generation; future stills use self-hosted Qwen-Image-2.1')
    manifest['fingerprint'] = hashlib.sha256(json.dumps(manifest,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
    if (ROOT/'manifest.json').exists():
        existing = json.loads((ROOT/'manifest.json').read_text())
        if existing['fingerprint'] != manifest['fingerprint']:
            raise RuntimeError('Existing batch inputs differ; use a new test directory instead of overwriting its manifest')
    (ROOT/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(dict(shots=len(shots), inputs=len(list((ROOT/'inputs').glob('*.png'))), slots=[len(s['slots']) for s in shots], fingerprint=manifest['fingerprint'])))

if __name__ == '__main__':
    main()
