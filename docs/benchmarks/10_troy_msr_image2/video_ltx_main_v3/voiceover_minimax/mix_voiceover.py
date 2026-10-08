#!/usr/bin/env python3
"""Place MiniMax narration on the edited timeline and mix with native scene audio."""
import hashlib
import html
import json
import math
import re
import subprocess
import wave
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent

def save(name, obj):
    (ROOT / name).write_text(json.dumps(obj, ensure_ascii=False, indent=2) + '\n')

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def ffmpeg(args):
    return subprocess.run(['ffmpeg', '-hide_banner', '-nostdin', '-y', *args],
                          capture_output=True, text=True, check=True)

def probe(path):
    r = subprocess.run(['ffprobe', '-v', 'error', '-show_streams', '-show_format',
                        '-of', 'json', str(path)], capture_output=True, text=True, check=True)
    return json.loads(r.stdout)

def pcm(path):
    r = subprocess.run(['ffmpeg', '-v', 'error', '-i', str(path), '-vn', '-ac', '1',
                        '-ar', '32000', '-f', 'f32le', 'pipe:1'], capture_output=True, check=True)
    return np.frombuffer(r.stdout, dtype='<f4')

def write_wav(path, values):
    samples = np.rint(np.clip(values, -1, 1) * 32767).astype('<i2')
    with wave.open(str(path), 'wb') as w:
        w.setnchannels(2 if values.ndim == 2 else 1)
        w.setsampwidth(2)
        w.setframerate(32000)
        w.writeframes(samples.tobytes())

def normalize(source, dest, target_i):
    target = f'loudnorm=I={target_i}:TP=-1.5:LRA=11'
    first = ffmpeg(['-i', str(source), '-af', target + ':print_format=json', '-f', 'null', '-'])
    matches = re.findall(r'\{\s*"input_i".*?\}', first.stderr, re.S)
    assert matches, first.stderr[-500:]
    data = json.loads(matches[-1])
    for key in ['input_i', 'input_tp', 'input_lra', 'input_thresh', 'target_offset']:
        assert math.isfinite(float(data[key]))
    second = (target + f":measured_I={data['input_i']}:measured_TP={data['input_tp']}"
              + f":measured_LRA={data['input_lra']}:measured_thresh={data['input_thresh']}"
              + f":offset={data['target_offset']}:linear=true:print_format=json")
    samples = round(float(probe(source)['format']['duration']) * 32000)
    second += f',aresample=32000,apad=whole_len={samples},atrim=end_sample={samples}'
    ffmpeg(['-i', str(source), '-af', second, '-ar', '32000', '-ac', '2',
            '-c:a', 'pcm_s16le', str(dest)])
    save(dest.stem + '_loudness_input.json', data)
    return data

def stamp(seconds, comma=True):
    total = round(seconds * 1000)
    hours, remainder = divmod(total, 3600000)
    minutes, remainder = divmod(remainder, 60000)
    whole, ms = divmod(remainder, 1000)
    return f'{hours:02}:{minutes:02}:{whole:02}{"," if comma else "."}{ms:03}'

def video_hash(path):
    r = ffmpeg(['-v', 'error', '-i', str(path), '-map', '0:v:0', '-c:v', 'copy',
                '-f', 'hash', '-hash', 'sha256', '-'])
    return r.stdout.strip()

def media_receipt(path, expected_s, frames=None):
    data = probe(path)
    audio = next(s for s in data['streams'] if s['codec_type'] == 'audio')
    duration = float(data['format']['duration'])
    assert abs(duration - expected_s) < .03, (path, duration, expected_s)
    assert int(audio['sample_rate']) == 32000 and audio['channels'] == 2
    ffmpeg(['-v', 'error', '-i', str(path), '-f', 'null', '-'])
    row = dict(path=path.name, duration_s=duration, audio_sample_rate=32000,
               channels=2, full_decode=True, sha256=sha(path), bytes=path.stat().st_size)
    if frames is not None:
        video = next(s for s in data['streams'] if s['codec_type'] == 'video')
        assert int(video['nb_frames']) == frames
        assert video['r_frame_rate'] == '24/1'
        assert [video['width'], video['height']] == [672, 384]
        row.update(frames=frames, fps=24, size=[672, 384])
    return row

def main():
    plan = json.loads((ROOT / 'plan.json').read_text())
    result = json.loads((ROOT / 'synthesis_results.json').read_text())
    assert result['status'] == 'PASS' and len(result['clips']) == 12
    by_id = {r['id']: r for r in result['clips']}
    source = ROOT / plan['source_film']
    assert sha(source) == plan['source_film_sha256']
    sample_count = round(plan['film_duration_s'] * 32000)
    narration = np.zeros(sample_count, dtype=np.float64)
    coverage = np.zeros(sample_count, dtype=np.uint8)
    placements, subtitles, spoken = [], [], []
    for cue in plan['cues']:
        raw = ROOT / cue['audio_file']
        row = by_id[cue['id']]
        assert row['plan_fingerprint'] == plan['fingerprint']
        assert sha(raw) == row['audio_sha256']
        signal = pcm(raw).astype(np.float64)
        start = round(cue['start_s'] * 32000)
        end = start + len(signal)
        assert end <= round(cue['latest_end_s'] * 32000), cue['id']
        assert not coverage[start:end].any(), cue['id']
        # Brief edge fades prevent clicks without changing sentence timing.
        fade = min(320, len(signal) // 4)
        signal[:fade] *= np.linspace(0, 1, fade)
        signal[-fade:] *= np.linspace(1, 0, fade)
        narration[start:end] += signal
        coverage[start:end] = 1
        spoken.append(signal)
        placements.append(dict(id=cue['id'], text=cue['text'], audio_sha256=row['audio_sha256'],
                               start_sample=start, end_sample=end, start_s=start / 32000,
                               end_s=end / 32000, duration_s=len(signal) / 32000,
                               latest_end_s=cue['latest_end_s'], time_stretch=1.0))
        srt = ROOT / cue['subtitles_file']
        assert srt.exists(), f'Missing provider subtitle: {cue["id"]}'
        for block in re.split(r'\n\s*\n', srt.read_text().strip()):
            lines = block.splitlines()
            assert len(lines) >= 3
            match = re.fullmatch(r'(\d\d):(\d\d):(\d\d),(\d{3}) --> (\d\d):(\d\d):(\d\d),(\d{3})', lines[1])
            assert match, lines[1]
            n = [int(x) for x in match.groups()]
            a = n[0] * 3600 + n[1] * 60 + n[2] + n[3] / 1000
            b = n[4] * 3600 + n[5] * 60 + n[6] + n[7] / 1000
            assert 0 <= a < b <= len(signal) / 32000 + .1
            subtitles.append((start / 32000 + a, start / 32000 + b, '\n'.join(lines[2:])))
    assert np.max(np.abs(narration)) <= 1.001
    save('placement.json', dict(plan_fingerprint=plan['fingerprint'], source_film_sha256=sha(source),
                                sample_rate=32000, film_samples=sample_count, cues=placements,
                                time_stretch_applied=False, overlaps=False))
    write_wav(ROOT / 'narration_raw.wav', narration)
    write_wav(ROOT / 'narration_spoken_only.wav', np.concatenate(spoken))
    normalize(ROOT / 'narration_raw.wav', ROOT / 'narration.wav', -18)
    (ROOT / 'narration.srt').write_text('\n\n'.join(f'{i}\n{stamp(a)} --> {stamp(b)}\n{t}'
                                                    for i, (a, b, t) in enumerate(subtitles, 1)) + '\n')
    (ROOT / 'narration.vtt').write_text('WEBVTT\n\n' + '\n\n'.join(f'{stamp(a, False)} --> {stamp(b, False)}\n{t}'
                                                                    for a, b, t in subtitles) + '\n')
    mix_filter = ('[0:a]aresample=32000,aformat=sample_fmts=fltp:channel_layouts=stereo,volume=0.55[amb];'
                  '[1:a]asplit=2[sc][vo];'
                  '[amb][sc]sidechaincompress=threshold=0.025:ratio=6:attack=10:release=300:makeup=1[duck];'
                  '[duck][vo]amix=inputs=2:duration=first:dropout_transition=0:normalize=0,'
                  'alimiter=limit=0.90:level=false:latency=true,aresample=32000,'
                  f'apad=whole_len={sample_count},atrim=end_sample={sample_count}[m]')
    ffmpeg(['-i', str(source), '-i', str(ROOT / 'narration.wav'), '-filter_complex', mix_filter,
            '-map', '[m]', '-t', str(plan['film_duration_s']), '-c:a', 'pcm_s16le', str(ROOT / 'mix_raw.wav')])
    normalize(ROOT / 'mix_raw.wav', ROOT / 'mix.wav', -16)
    film = ROOT / 'film_voiced.mp4'
    ffmpeg(['-i', str(source), '-i', str(ROOT / 'mix.wav'), '-map', '0:v:0', '-map', '1:a:0',
            '-c:v', 'copy', '-c:a', 'aac', '-b:a', '192k', '-t', str(plan['film_duration_s']),
            '-movflags', '+faststart', str(film)])
    # Extract the existing S14 boundary exactly; encode this shorter preview independently.
    battle = ROOT / 'battle_voiced.mp4'
    ffmpeg(['-i', str(film), '-ss', '59.5', '-t', '31.75', '-map', '0:v:0', '-map', '0:a:0',
            '-c:v', 'libx264', '-preset', 'fast', '-crf', '18', '-c:a', 'aac', '-b:a', '192k',
            '-movflags', '+faststart', str(battle)])
    original_packets, voiced_packets = video_hash(source), video_hash(film)
    assert original_packets == voiced_packets
    final_measure = ffmpeg(['-i', str(film), '-af', 'loudnorm=I=-16:TP=-1.5:LRA=11:print_format=json', '-f', 'null', '-'])
    loudness = json.loads(re.findall(r'\{\s*"input_i".*?\}', final_measure.stderr, re.S)[-1])
    assert -17 <= float(loudness['input_i']) <= -15
    assert float(loudness['input_tp']) <= -.9
    save('mix_verification.json', dict(status='PASS', plan_fingerprint=plan['fingerprint'],
         source_film_sha256=sha(source), film=media_receipt(film, 91.25, 2190),
         battle_excerpt=media_receipt(battle, 31.75, 762), narration=media_receipt(ROOT / 'narration.wav', 91.25),
         mix=media_receipt(ROOT / 'mix.wav', 91.25), cues=len(placements), subtitles=len(subtitles),
         source_video_packet_hash=original_packets, voiced_video_packet_hash=voiced_packets,
         video_reencoded=False, narration_time_stretched=False, subtitles_source='MiniMax returned segment timing',
         final_loudness=loudness, mix_filter=mix_filter, independent_listening_review=False,
         independent_asr_review=False))
    print(json.dumps({'status': 'PASS', 'cues': len(placements), 'film_s': 91.25,
                      'video_packet_hash_identical': True, 'loudness_i': loudness['input_i'],
                      'true_peak_db': loudness['input_tp']}, ensure_ascii=False), flush=True)

if __name__ == '__main__':
    main()
