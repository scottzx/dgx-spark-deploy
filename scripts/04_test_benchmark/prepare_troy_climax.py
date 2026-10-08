#!/usr/bin/env python3
"""Prepare a pinned six-beat Trojan Horse story and shared visual inputs."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil

from PIL import Image, ImageOps

REMOTE = Path('/home/admin/sol-spark-runtime/troy_climax_20261004')
STYLE = ('Live-action 1970s Shaw Brothers historical studio cinema, ancient Troy, '
         'saturated 35mm film colors, theatrical hard light, practical timber and stone sets. ')
RULES = ('One enormous hollow wooden Trojan horse, visibly made from timber planks with the same '
         'golden bronze bands, mounted on the same four-wheeled timber platform. Its four rigid '
         'wooden legs never walk, its head never moves, and its wheels rotate only while pulled. '
         'One rectangular hinged hatch on its camera-facing belly and one wooden ladder. '
         'The Greek leader is the bearded short-dark-haired man in engraved bronze armor and a red cloak, '
         'with one sword sheathed at his right hip and no shield. His companion is the clean-shaven '
         'curly-dark-haired man in engraved bronze armor and a blue cloak, with one sword sheathed '
         'at his right hip and one round bronze shield strapped to his back. They use free hands to climb. '
         'Keep faces, hair, armor, cloak colors, equipment ownership and horse construction consistent. ')
BEATS = [
    ('01_gate', '木马进城', 'independent',
     'Daylight. Wide establishing shot outside the arched stone gate of Troy. A few Trojan workers '
     'in simple tan tunics pull ropes, slowly rolling the enormous rigid wooden horse into the city. '
     'The camera tracks right at ground level, showing wooden wheels rotating and the horse passing '
     'under the arch. The hatch is completely shut. All Greek soldiers remain hidden inside, invisible.'),
    ('02_square', '进入广场', 'continue',
     'Daylight. Continue the previous rightward tracking movement without a cut. The Trojan workers '
     'continue pulling the same wheeled wooden horse away from the gate into the paved central square. '
     'A stone fountain and two bronze braziers establish the square. The camera keeps the whole horse '
     'and platform visible. The hatch stays shut and all Greek soldiers remain hidden inside, invisible.'),
    ('03_park', '木马停驻', 'independent',
     'Sunset. New wide shot of the central square. The wooden horse rolls its last small distance and '
     'comes to a complete stop beside the stone fountain between two bronze braziers. The Trojan '
     'workers release the ropes and walk away. The wooden body remains rigid, hatch completely shut. '
     'All Greek soldiers are concealed and invisible. Hold the final parked position with a slow push-in.'),
    ('04_night', '夜间静场', 'independent',
     'Night. New medium-wide shot of the now empty central square. The same wooden horse is parked '
     'motionless beside the same fountain between two braziers. Moonlight is cobalt blue and torches '
     'are warm amber, with enough fill light to read timber details. The camera slowly pushes toward '
     'the camera-facing belly hatch, which stays closed throughout this shot. No soldier is visible yet.'),
    ('05_hatch', '舱门开启', 'continue',
     'Night. Continue the previous slow camera push without a cut. The single hinged belly hatch '
     'of the parked wooden horse opens outward gradually, revealing a dark hollow interior. The '
     'same bearded red-cloaked Greek leader cautiously looks out, lowers the one wooden ladder '
     'from the hatch to the platform, then starts descending one rung. He has no shield and his '
     'sword stays sheathed. The same blue-cloaked companion waits inside behind him. The horse stays rigid.'),
    ('06_exit', '希腊士兵出马', 'continue',
     'Night. Continue the same camera movement and unfolding action without a cut. The red-cloaked '
     'bearded Greek leader climbs down the ladder from the open belly hatch, steps from the timber '
     'platform onto the square, looks around and signals quietly with his empty left hand. The '
     'clean-shaven curly-haired blue-cloaked companion emerges from that SAME hatch and climbs down '
     'the SAME ladder behind him, shield strapped to his back and sword sheathed. Exactly these '
     'two Greek soldiers emerge in sequence, no fight. The wooden horse and platform remain motionless.'),
]
SOUNDS = [
    'Ropes creak, wooden wheels rumble on stone, sandals scuff, distant city ambience.',
    'Wooden wheels rumble, ropes creak, light fountain water and distant city ambience.',
    'Wheels slow and stop, footsteps recede, fountain water and evening wind.',
    'Quiet night wind, fountain water and crackling braziers.',
    'Quiet night wind, torch crackle, wooden hatch and ladder creaks, faint armor rustle.',
    'Quiet night wind, ladder creaks, sandals land on stone, soft armor rustle and torches.',
]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sheet', type=Path, required=True)
    parser.add_argument('--identity-assets', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    assets = args.output / 'assets'
    assets.mkdir(parents=True, exist_ok=True)
    source = Image.open(args.sheet).convert('RGB')
    # Inspect the generated sheet before choosing these panel boundaries.
    assert source.size == (1363, 1154), source.size
    xs, ys = [0, 681, 1363], [0, 385, 741, 1154]
    shutil.copy2(args.sheet, assets / 'storyboard_source.png')
    panels = []
    for i in range(6):
        x, y = i % 2, i // 2
        panel = source.crop((xs[x], ys[y], xs[x+1], ys[y+1]))
        panel = ImageOps.fit(panel, (1344, 768), method=Image.Resampling.LANCZOS)
        filename = f'board_{i+1:02d}.png'
        panel.save(assets / filename)
        panels.append(filename)
    for filename in ['red_identity.png', 'blue_identity.png', 'equipment.png']:
        shutil.copy2(args.identity_assets / filename, assets / filename)
    # Stable daylight/night environment reference, without changing the horse's design.
    horse = Image.new('RGB', (1344, 1536), 'black')
    horse.paste(Image.open(assets/'board_03.png'), (0, 0))
    horse.paste(Image.open(assets/'board_04.png'), (0, 768))
    horse.save(assets / 'horse_square.png')
    shots = []
    prompts = {}
    for i, (cid, title, transition, action) in enumerate(BEATS):
        early = i < 4
        ref_files = (['horse_square.png', panels[i]] if early else
                     ['red_identity.png', 'blue_identity.png', 'equipment.png',
                      'horse_square.png', panels[i]])
        refs = [str(REMOTE/'assets'/name) for name in ref_files]
        sheet = Image.new('RGB', (1536, 896), 'black')
        boxes = ([(0,0,1536,384),(0,384,1536,896)] if early else
                 [(0,0,384,384), (384,0,768,384), (768,0,1152,384),
                  (1152,0,1536,384), (0,384,1536,896)])
        for name, box in zip(ref_files, boxes):
            part = ImageOps.contain(Image.open(assets/name).convert('RGB'),
                (box[2]-box[0], box[3]-box[1]), Image.Resampling.LANCZOS)
            sheet.paste(part, (box[0]+(box[2]-box[0]-part.width)//2,
                              box[1]+(box[3]-box[1]-part.height)//2))
        sheet_name = f'ingredients_{i+1:02d}.png'
        sheet.save(assets/sheet_name)
        sound = SOUNDS[i] + ' No dialogue or music.'
        rules = (RULES.split('The Greek leader')[0] +
                 'The belly hatch is shut and no ladder is visible. No Greek soldier is visible. '
                 if early else RULES)
        ltx = STYLE + rules + action + ' One uninterrupted five-second shot. ' + sound
        definitions = ('subject_definitions:\n'
            '<Subject 1> is the red-cloaked bearded Greek leader in <Picture 1>.\n'
            '<Subject 2> is the blue-cloaked clean-shaven Greek soldier in <Picture 2>.\n'
            '<Subject 3> is their equipment in <Picture 3>; swords stay sheathed for climbing, '
            'only the blue soldier owns one round shield, strapped to his back.\n'
            '<Subject 4> is the rigid wooden horse and Troy square in <Picture 4>.\n'
            '<Picture 5> is the framing, time of day and narrative staging reference for this shot.\n'
            'summary: [reference generation] The Trojan Horse enters Troy, is parked in the square, '
            'and conceals Greek soldiers until night.\nretention_analysis:\n'
            '<Subject 1>: fully_preserved - identity and costume reference only; hidden until the hatch opens.\n'
            '<Subject 2>: fully_preserved - identity and costume reference only; hidden until the hatch opens.\n'
            '<Subject 3>: fully_preserved - preserve equipment ownership and design.\n'
            '<Subject 4>: fully_preserved - preserve horse design, wheels, hatch and square landmarks.\n'
            '<Picture 5>: partially_preserved - preserve shot staging; follow the specified action.\n'
            'detailed_description: ')
        if early:
            definitions = ('subject_definitions:\n'
                '<Subject 1> is the rigid wheeled timber horse and square in <Picture 1>.\n'
                '<Picture 2> is this shot framing, time of day and staging reference.\n'
                'summary: [reference generation] '+action+'\nretention_analysis:\n'
                '<Subject 1>: fully_preserved - horse construction, wheels, shut hatch and landmarks.\n'
                '<Picture 2>: partially_preserved - preserve staging and follow the action.\n'
                'detailed_description: ')
        shot = dict(case_id='climax_v2_'+cid, title=title, transition=transition,
            seed=2026100401+i, duration_s=5, source_frames=121,
            delivered_frames=102 if transition=='continue' else 121,
            references=refs, reference_files=ref_files,
            ingredients_sheet=str(REMOTE/'assets'/sheet_name),
            h3_prompt=definitions+STYLE+rules+'[Shot 1] '+action+
                ' overall_soundscape: '+sound+' non_diegetic_music: None.',
            ltx_prompt=ltx)
        shot['prompt_keys'] = {method: f'{method}_{cid}' for method in ['specific','ingredients','msr']}
        prompts[shot['prompt_keys']['specific']] = ltx
        ingredients_prefix = ('Reference sheet: the top panel shows the timber horse and square; '
            'the bottom panel shows this shot staging. Generated video: ' if early else
            'Reference sheet: top panels show the red Greek leader, blue Greek soldier, their '
            'equipment, and the wooden horse in the square. The bottom panel shows this shot staging. '
            'Reference characters remain hidden until the narrative calls for emergence. Generated video: ')
        prompts[shot['prompt_keys']['ingredients']] = ingredients_prefix+ltx
        msr_prefix = ('pic1 is the timber horse and square; pic2 is this shot staging. ' if early else
            'pic1 is the red Greek leader, pic2 the blue Greek soldier, pic3 their equipment, '
            'pic4 the wooden horse and square, pic5 this shot staging. Characters in identity '
            'references remain hidden until the narrative calls for emergence. ')
        prompts[shot['prompt_keys']['msr']] = msr_prefix+ltx
        shots.append(shot)
    manifest = dict(schema_version=1, title='木马计高潮：进城、停驻、夜间出马', shots=shots,
        frames=sum(s['delivered_frames'] for s in shots), fps=24,
        source_sheet=str(args.sheet.resolve()),
        asset_files={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in assets.glob('*.png')},
        comparison_scope='H3 generic/specific share captures. Native LTX methods generate independent '
            'shots; shorten their ending to matched timeline lengths, without claiming motion continuation.',
        reference_policy='Story-stage gating, shared by all methods: first four shots use horse/square '
            'and staging only; last two add both soldier identities and equipment. Initial all-subject '
            'reference attempt is archived because soldiers appeared before the night reveal.',
        identity_source='Previous benchmark crops; generated storyboard is additional staging reference, '
            'not a newly verified multi-view identity dataset.',
        image_generation=dict(mode='built-in image_gen', reference='08_identity_consistency/assets/board.png',
            prompt_summary='Six-panel 1970s Shaw Brothers Troy storyboard: gate, square, sunset parking, '
            'night parking, opening belly hatch and ladder, red then blue soldiers emerging. '
            'Preserve reference faces, cloak colors, engraved armor and timber horse; add wheeled platform.'))
    (args.output/'story.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2)+'\n')
    (args.output/'ltx_prompts.json').write_text(json.dumps(prompts, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps(dict(status='PREPARED', shots=len(shots), frames=manifest['frames'],
        duration_s=manifest['frames']/24, assets=len(manifest['asset_files'])), ensure_ascii=False))


if __name__ == '__main__':
    main()
