#!/usr/bin/env python3
"""Verify actual deliverable media, including complete decoding and audio identity."""
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[3] / 'docs/benchmarks/11_coca_cola_avatar'
FFMPEG = '/opt/homebrew/bin/ffmpeg'
FFPROBE = '/opt/homebrew/bin/ffprobe'


def main():
    records = []
    for directory in ['route_A_musetalk', 'route_B_flashhead', 'route_C_echomimic']:
        path = ROOT / directory / 'coca_cola_vertical.mp4'
        data = json.loads(subprocess.check_output([FFPROBE, '-v', 'error', '-show_streams', '-show_format', '-of', 'json', str(path)]))
        video = next(s for s in data['streams'] if s['codec_type'] == 'video')
        audio = next(s for s in data['streams'] if s['codec_type'] == 'audio')
        assert (video['width'], video['height']) == (1080, 1920)
        assert video['r_frame_rate'] == '25/1' and int(video['nb_frames']) == 661
        assert abs(float(video['duration']) - 26.44) < 0.02
        assert abs(float(audio['duration']) - 26.44) < 0.02
        subprocess.run([FFMPEG, '-v', 'error', '-xerror', '-i', str(path), '-f', 'null', '-'], check=True)
        pcm = subprocess.check_output([FFMPEG, '-v', 'error', '-i', str(path), '-map', '0:a:0', '-f', 's16le', '-ac', '1', '-ar', '24000', '-'])
        records.append({'route': directory, 'file': str(path.relative_to(ROOT)),
                        'width': video['width'], 'height': video['height'],
                        'frames': int(video['nb_frames']), 'duration_seconds': float(video['duration']),
                        'complete_decode': True, 'decoded_audio_sha256': hashlib.sha256(pcm).hexdigest(),
                        'file_sha256': hashlib.file_digest(path.open('rb'), 'sha256').hexdigest()})
    assert len({r['decoded_audio_sha256'] for r in records}) == 1
    receipt = {'all_audio_identical': True, 'files': records}
    (ROOT / 'verification.json').write_text(json.dumps(receipt, indent=2) + '\n')
    print(json.dumps(receipt, indent=2))


if __name__ == '__main__':
    main()
