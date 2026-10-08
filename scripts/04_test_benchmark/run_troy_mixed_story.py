#!/usr/bin/env python3
"""Run both workflow types in one actual /api/story GPU request."""
import argparse
import json
from pathlib import Path
import time

from run_troy_workflow_comparison import request, validate


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('comparison', type=Path)
    parser.add_argument('--base', default='http://127.0.0.1:8090')
    args = parser.parse_args()
    output = args.comparison.parent
    deadline = time.monotonic() + 1200
    while True:
        try:
            status = request(args.base, '/api/status', timeout=5)
            if status['status'] == 'READY':
                break
        except (OSError, RuntimeError):
            pass
        if time.monotonic() > deadline:
            raise TimeoutError('Server did not become READY')
        time.sleep(10)
    shots = []
    for i, label in enumerate(('opening', 'continuation', 'angle')):
        previous = json.loads((output / f'{label}_request.json').read_text())
        shots.append(dict(shot_id=f'shot_{i+1}', **{key: previous[key] for key in
            ('prompt', 'transition', 'first_frame', 'last_frame', 'duration_s', 'seed',
             'context_frames', 'audio_context_frames') if key in previous}))
    payload = dict(story_id='troy_mixed_' + time.strftime('%Y%m%d_%H%M%S'),
        mode='final', initial_frame=shots[0]['first_frame'], shots=shots)
    (output / 'mixed_story_request.json').write_text(json.dumps(payload, indent=2))
    print('GENERATING ' + payload['story_id'], flush=True)
    response = request(args.base, '/api/story', payload)
    (output / 'mixed_story_response.json').write_text(json.dumps(response, indent=2))
    a, b, c = response['shots']
    assert [r['transition'] for r in (a, b, c)] == ['independent', 'continue', 'independent']
    assert b['previous_clip_id'] == a['case_id'] and b['continuation']['frozen_prefix_verified']
    assert not c.get('continuation') and c['trim_frames'] == 0
    count = sum(r['delivered_frames'] for r in response['shots'])
    assert response['delivered_frames'] == count == 344
    for row in response['shots']:
        validate(Path(row['output']), row['delivered_frames'])
    media = validate(Path(response['video_path']), count)
    result = dict(status='PASS', media=media, story=response,
        test_sequence=['independent', 'continue', 'independent'])
    (output / 'mixed_story.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result), flush=True)


if __name__ == '__main__':
    main()
