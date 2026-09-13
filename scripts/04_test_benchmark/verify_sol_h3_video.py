#!/usr/bin/env python3
"""Validate the Sol-H3-Spark media contract and extract frames for human review.

Passing these checks establishes decodability and format, not visual quality.
Inspect the generated contact sheet before accepting the deployment.
"""
import argparse
import json
from pathlib import Path
import subprocess


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('video', type=Path)
    parser.add_argument('--output-dir', required=True, type=Path)
    args = parser.parse_args()
    video = args.video.resolve(strict=True)
    out = args.output_dir.resolve()
    out.mkdir(parents=True, exist_ok=False)
    metadata = json.loads(subprocess.check_output([
        'ffprobe', '-v', 'error', '-count_frames', '-show_streams',
        '-show_format', '-of', 'json', str(video)], text=True))
    streams = metadata['streams']
    visual = next(s for s in streams if s['codec_type'] == 'video')
    audio = next(s for s in streams if s['codec_type'] == 'audio')
    checks = {
        'resolution_1344x768': (visual['width'], visual['height']) == (1344, 768),
        'frames_121': int(visual['nb_read_frames']) == 121,
        'fps_24': visual['avg_frame_rate'] == '24/1',
        'h264_video': visual['codec_name'] == 'h264',
        'aac_audio': audio['codec_name'] == 'aac',
        'stereo_audio': audio['channels'] == 2,
    }
    decoded = subprocess.run([
        'ffmpeg', '-v', 'error', '-xerror', '-i', str(video),
        '-map', '0:v:0', '-map', '0:a:0', '-f', 'null', '-'],
        capture_output=True, text=True)
    checks['full_decode'] = decoded.returncode == 0
    select = '+'.join(f'eq(n,{n})' for n in [0, 24, 48, 72, 96, 120])
    subprocess.run([
        'ffmpeg', '-v', 'error', '-i', str(video), '-vf',
        f"select='{select}',scale=448:256,tile=3x2", '-frames:v', '1',
        str(out / 'contact-sheet.png')], check=True)
    report = {'video': str(video), 'checks': checks, 'metadata': metadata,
              'decode_errors': decoded.stderr, 'visual_review': 'PENDING',
              'contact_sheet': str(out / 'contact-sheet.png')}
    (out / 'media-validation.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'checks': checks, 'visual_review': 'PENDING',
                      'contact_sheet': report['contact_sheet']}, indent=2))
    return 0 if all(checks.values()) else 1


if __name__ == '__main__':
    raise SystemExit(main())
