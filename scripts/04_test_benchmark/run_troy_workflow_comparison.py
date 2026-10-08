#!/usr/bin/env python3
"""Exercise independent->continue->independent through the live Sol API.

The two films share clip A to make their different second-shot transitions
directly comparable. Runs three real generations, then validates both masters.
"""
import argparse
import json
from pathlib import Path
import subprocess
import time
import urllib.error
import urllib.request
import sys

sys.path.insert(0, '/home/admin/sol-h3-spark/models/minimax_h3/Sol-H3-Spark')
from runtime.workflows import concatenate_clips

FFMPEG = '/home/admin/.local/bin/ffmpeg'
FFPROBE = '/home/admin/.local/bin/ffprobe'
STYLE = ('Live action in the visual style of a 1970s Shaw Brothers swordplay film, '
    'set in ancient Troy, anamorphic widescreen, theatrical amber hard light and cyan night shadows, '
    'handmade studio courtyard set, rich red and gold color, slight 35mm film grain. '
    'Exactly two adult Greek warriors with bronze cuirasses, leather sandals, short bronze swords and round shields. '
    'The bearded warrior wears a red cloak; the curly-haired clean-shaven warrior wears a blue cloak. '
    'A massive wooden Trojan horse stands behind them between ancient stone walls and two burning braziers. '
    'Clear choreographed stage combat, visible footwork, anatomically coherent bodies and swords. '
    'No wounds, no blood, no text, no extra people. ')
SOUND = (' overall_soundscape: Continuous quiet night wind and steady crackling braziers, '
    'leather sandals scuff the sand, a short clear bronze sword clash at each parry. '
    'No voices or dialogue. non_diegetic_music: None.')


def request(base, path, payload=None, timeout=1800):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(base+path, data=data, headers={'Content-Type':'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f'HTTP {exc.code}: {exc.read().decode()}') from exc


def validate(path, frames):
    info = json.loads(subprocess.check_output([FFPROBE, '-v','error','-count_frames',
        '-show_streams','-show_format','-of','json',str(path)]))
    video = next(s for s in info['streams'] if s['codec_type']=='video')
    audio = next(s for s in info['streams'] if s['codec_type']=='audio')
    assert (video['width'],video['height'],int(video['nb_read_frames']))==(1344,768,frames), info
    assert video['r_frame_rate']=='24/1' and audio['sample_rate']=='32000' and audio['channels']==2,info
    subprocess.run([FFMPEG,'-v','error','-xerror','-i',str(path),'-f','null','-'],check=True)
    return dict(status='PASS',frames=frames,duration_s=float(video['duration']),width=1344,height=768,
        sample_rate=32000,full_decode=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base',default='http://127.0.0.1:8090')
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--boards',type=Path,default=Path('/home/admin/sol-spark-runtime/inputs/troy_workflows_20261003'))
    parser.add_argument('--assemble-only',action='store_true',help='Reuse completed API responses without another generation')
    args=parser.parse_args()
    args.output.mkdir(parents=True,exist_ok=args.assemble_only)
    deadline=time.monotonic()+1200
    while True:
        try:
            status=request(args.base,'/api/status',timeout=5)
            if status['status']=='READY':
                break
        except (OSError,RuntimeError):
            pass
        if time.monotonic()>deadline:
            raise TimeoutError('Video server did not become READY')
        time.sleep(10)
    (args.output/'status_before.json').write_text(json.dumps(status,indent=2))
    prefix='troy_'+time.strftime('%Y%m%d_%H%M%S')
    cases=[dict(case_id=prefix+'_opening',transition='independent',first_frame=str(args.boards/'board_01.png'),
        seed=2026100301,duration_s=5,mode='final',prompt='integrated_multimodal_description: '+STYLE+
        'One continuous five-second wide shot, no cuts. The camera tracks slowly to the right at waist height '
        'while keeping both fighters full body. From 0 to 2 seconds the red warrior advances two steps and '
        'delivers a controlled diagonal sword strike, which the blue warrior parries with his sword. '
        'From 2 to 5 seconds both retreat a half step, circle each other with flowing capes and raise their swords '
        'for another exchange. The camera and both performers remain in motion through the end.'+SOUND),
        dict(case_id=prefix+'_continuation',transition='continue',previous_clip_id=prefix+'_opening',
        context_frames=22,audio_context_frames=24,seed=2026100302,duration_s=5,mode='final',
        prompt='integrated_multimodal_description: '+STYLE+
        'Continue the preceding uninterrupted wide tracking shot at exactly the same camera height, '
        'framing, direction and speed. No cuts, no zoom, no sudden viewpoint change. During the first second '
        'the fighters carry on their exact circling movement from the pinned context, without freezing. '
        'Then the blue warrior makes two quick forward steps and a controlled thrust; the red warrior '
        'deflects it with his shield, pivots and answers with a broad non-contact sword sweep. '
        'Both keep moving, capes fluttering, the wooden horse remains behind them.'+SOUND),
        dict(case_id=prefix+'_new_angle',transition='independent',first_frame=str(args.boards/'board_02.png'),
        seed=2026100303,duration_s=5,mode='final',prompt='integrated_multimodal_description: '+STYLE+
        'A separately staged five-second action insert. In the first half second a classic Shaw Brothers '
        'rapid crash zoom pushes from the wide view into a dramatic low-angle medium shot of the two fighters. '
        'Then hold that closer camera position. The blue warrior raises his round shield against a red warrior '
        'diagonal sword strike, turns sideways and counters with a thrust; the red warrior steps back and '
        'parries. Strong readable choreographed gestures with swinging cloaks. End on the crossed swords. '
        'No other shots or people within this insert.'+SOUND)]
    rows=[]
    for case in ([] if args.assemble_only else cases):
        label=case['case_id'].rsplit('_',1)[-1]
        (args.output/f'{label}_request.json').write_text(json.dumps(case,indent=2))
        print(f"GENERATING {case['case_id']} transition={case['transition']}",flush=True)
        row=request(args.base,'/api/generate',case)
        validate(Path(row['video_path']),row['delivered_frames'])
        (args.output/f'{label}_response.json').write_text(json.dumps(row,indent=2))
        print(json.dumps(row),flush=True)
        rows.append(row)
    if args.assemble_only:
        rows=[json.loads((args.output/f'{name}_response.json').read_text())
            for name in ('opening','continuation','angle')]
    assert rows[1]['continuation']['frozen_prefix_verified'] is True
    assert rows[1]['trim_frames']==19 and rows[1]['delivered_frames']==102
    assert not rows[2]['continuation'] and rows[2]['trim_frames']==0
    films=[]
    for name, pair in [('storyboard',[rows[0],rows[2]]),('continuous',[rows[0],rows[1]])]:
        listing=args.output/f'{name}_concat.txt'
        listing.write_text(''.join(f"file '{r['video_path']}'\n" for r in pair))
        master=args.output/f'troy_{name}.mp4'
        concatenate_clips([r['video_path'] for r in pair], [r['delivered_frames'] for r in pair], master)
        frames=sum(r['delivered_frames'] for r in pair)
        media=validate(master,frames)
        selected=sorted(set([0,24,72,116,120,121,122,125,145,frames-1]))
        vf="select='"+'+'.join(f'eq(n\\,{n})' for n in selected)+"',scale=448:256,tile=5x2"
        sheet=args.output/f'{name}_contact_sheet.png'
        subprocess.run([FFMPEG,'-y','-i',str(master),'-vf',vf,'-frames:v','1',str(sheet)],check=True,capture_output=True)
        film=dict(name=name,file=str(master),contact_sheet=str(sheet),media=media,
            seam_frame=121,shots=[r['case_id'] for r in pair])
        films.append(film)
    report=dict(status='PASS',shots=rows,films=films,
        test_sequence=['independent','continue','independent'],
        continuity_scope='Frozen native H3 AV prefix verified; LTX delivery needs visual/audio review')
    (args.output/'comparison.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report),flush=True)


if __name__=='__main__':
    main()
