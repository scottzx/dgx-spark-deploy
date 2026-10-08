#!/usr/bin/env python3
"""Continue the continued clip for ten seconds and validate the three-part film."""
import argparse
import json
from pathlib import Path
import subprocess
import time

from run_troy_workflow_comparison import FFMPEG, STYLE, SOUND, concatenate_clips, request, validate


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('comparison', type=Path)
    parser.add_argument('--base', default='http://127.0.0.1:8090')
    parser.add_argument('--assemble-only', action='store_true')
    args = parser.parse_args()
    report = json.loads(args.comparison.read_text())
    output = args.comparison.parent
    opening, previous = report['shots'][:2]
    payload = dict(case_id='troy_long_' + time.strftime('%Y%m%d_%H%M%S'),
        transition='continue', previous_clip_id=previous['case_id'],
        context_frames=22, audio_context_frames=24, seed=2026100304,
        duration_s=10, mode='final', prompt='integrated_multimodal_description: ' + STYLE +
        'Continue the preceding uninterrupted tracking shot. Preserve both actors, costumes, '
        'sword hands, shields, camera height and direction. No cuts or abrupt zoom. '
        'The blue warrior finishes his forward thrust as the red warrior pivots away. '
        'They circle clockwise with light dancing footwork, then exchange two clearly separated '
        'sword strikes and shield parries. The camera slowly tracks right with their movement. '
        'For the last three seconds they retreat one step, hold their guard and keep circling. '
        'The wooden horse remains in the background throughout this continuous ten-second take.' + SOUND)
    response_path = output / 'long_continuation_response.json'
    if args.assemble_only:
        row = json.loads(response_path.read_text())
    else:
        (output / 'long_continuation_request.json').write_text(json.dumps(payload, indent=2))
        print('GENERATING ' + payload['case_id'], flush=True)
        row = request(args.base, '/api/generate', payload)
        response_path.write_text(json.dumps(row, indent=2))
    assert row['continuation']['frozen_prefix_verified'] is True, row
    assert row['trim_frames'] == 19 and row['delivered_frames'] == 222, row
    clip_media = validate(Path(row['video_path']), row['delivered_frames'])
    clips = [opening, previous, row]
    master = output / 'troy_continuous_extended.mp4'
    concatenate_clips([r['video_path'] for r in clips], [r['delivered_frames'] for r in clips], master)
    count = sum(r['delivered_frames'] for r in clips)
    media = validate(master, count)
    indices = [0, 120, 121, 222, 223, 224, 250, 300, 400, count-1]
    vf = "select='" + '+'.join(f'eq(n\\,{n})' for n in indices) + "',scale=448:256,tile=5x2"
    sheet = output / 'continuous_extended_contact_sheet.png'
    subprocess.run([FFMPEG, '-y', '-i', str(master), '-vf', vf, '-frames:v', '1', str(sheet)],
        check=True, capture_output=True)
    result = dict(status='PASS', predecessor=previous['case_id'], shot=row, clip_media=clip_media,
        film=str(master), media=media, contact_sheet=str(sheet), seams=[121, 223])
    (output / 'extension.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result), flush=True)


if __name__ == '__main__':
    main()
