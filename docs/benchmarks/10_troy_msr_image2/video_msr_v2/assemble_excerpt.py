#!/usr/bin/env python3
"""Render review-bound editorial intervals, without promoting entire clips."""
import hashlib
import json
import subprocess
from pathlib import Path

from assemble_review import FF, check

ROOT = Path(__file__).resolve().parent


def main():
    registry = json.loads((ROOT / 'candidate_registry.json').read_text())
    intervals = registry['editable_intervals']
    assert len(intervals) == 3
    clips = {row['id']: row for row in registry['clips']}
    command = [FF, '-v', 'error', '-y']
    graph, receipts = [], []
    frame_count = 0
    for i, interval in enumerate(intervals):
        clip = clips[interval['id']]
        source = ROOT / clip['file']
        actual = hashlib.sha256(source.read_bytes()).hexdigest()
        assert actual == clip['output_sha256'] == interval['source_sha256']
        start, end = interval['start_frame'], interval['end_frame_exclusive']
        assert isinstance(start, int) and isinstance(end, int)
        assert 0 <= start < end <= 120
        assert (end - start) / 24 == interval['duration_s']
        assert interval['status'] != 'candidate_pending_dense_check'
        command += ['-i', str(source)]
        graph += [
            f'[{i}:v]trim=start_frame={start}:end_frame={end},setpts=PTS-STARTPTS[v{i}]',
            f'[{i}:a]aresample=32000,atrim=start_sample={start * 32000 // 24}:end_sample={end * 32000 // 24},asetpts=PTS-STARTPTS[a{i}]',
        ]
        frame_count += end - start
        receipts.append(dict(**interval, input_fingerprint=clip['input_fingerprint']))
    graph.append(''.join(f'[v{i}][a{i}]' for i in range(len(intervals))) + f'concat=n={len(intervals)}:v=1:a=1[v][a]')
    output = ROOT / 'action_excerpt.mp4'
    command += [
        '-filter_complex', ';'.join(graph), '-map', '[v]', '-map', '[a]',
        '-frames:v', str(frame_count), '-r', '24', '-c:v', 'libx264', '-crf', '19',
        '-preset', 'fast', '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-ar', '32000',
        '-ac', '2', '-b:a', '192k', '-movflags', '+faststart', str(output),
    ]
    subprocess.run(command, capture_output=True, check=True)
    media = check(output, frame_count)
    verification = dict(
        manifest_fingerprint=registry['manifest_fingerprint'],
        file=output.name, media=media, intervals=receipts,
        scope='Editorial action excerpts; source clips remain partial. No production or full audio acceptance.',
    )
    (ROOT / 'comparison' / 'excerpt_verification.json').write_text(json.dumps(verification, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(media))


if __name__ == '__main__':
    main()
