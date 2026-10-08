#!/usr/bin/env python3
"""Generate scene-aligned narration with the authenticated official MiniMax CLI."""
import hashlib
import json
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')

def main():
    plan = json.loads((ROOT / 'plan.json').read_text())
    rows = []
    for cue in plan['cues']:
        audio = ROOT / cue['audio_file']
        folder = audio.parent
        receipt = folder / 'result.json'
        assert sha(ROOT / cue['text_file']) == cue['text_sha256']
        if receipt.exists():
            row = json.loads(receipt.read_text())
            assert row['plan_fingerprint'] == plan['fingerprint']
            assert sha(audio) == row['audio_sha256']
            rows.append(row)
            continue
        cmd = ['mmx', 'speech', 'synthesize', '--text-file', cue['text_file'],
               '--model', plan['speech_model'], '--voice', plan['voice_id'],
               '--speed', str(cue['speed']), '--pitch', str(plan['pitch']),
               '--language', plan['language'], '--format', plan['audio_format'],
               '--sample-rate', str(plan['sample_rate']), '--channels', str(plan['channels']),
               '--subtitles', '--out', cue['audio_file'], '--output', 'json', '--non-interactive']
        print(json.dumps({'status': 'GENERATING', 'cue': cue['id'], 'completed': len(rows)}, ensure_ascii=False), flush=True)
        start = time.monotonic()
        result = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=330)
        (folder / 'cli_stdout.json').write_text(result.stdout)
        (folder / 'cli_stderr.log').write_text(result.stderr)
        if result.returncode:
            save(folder / 'failure.json', {'returncode': result.returncode, 'command': cmd,
                                          'stdout': result.stdout, 'stderr': result.stderr})
            raise RuntimeError(f"MiniMax synthesis failed for {cue['id']}: {result.stdout[:500]}")
        assert audio.exists() and audio.stat().st_size > 1000
        probe = subprocess.run(['ffprobe', '-v', 'error', '-show_streams', '-show_format',
                                '-of', 'json', str(audio)], capture_output=True, text=True, check=True)
        metadata = json.loads(probe.stdout)
        stream = metadata['streams'][0]
        assert stream['codec_type'] == 'audio'
        assert int(stream['sample_rate']) == plan['sample_rate']
        assert stream['channels'] == plan['channels']
        subprocess.run(['ffmpeg', '-v', 'error', '-i', str(audio), '-f', 'null', '-'], check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        duration = float(metadata['format']['duration'])
        budget = cue['latest_end_s'] - cue['start_s']
        row = {'status': 'TECHNICAL_PASS', 'id': cue['id'], 'plan_fingerprint': plan['fingerprint'],
               'text_sha256': cue['text_sha256'], 'audio_sha256': sha(audio), 'audio_file': cue['audio_file'],
               'duration_s': duration, 'window_s': budget, 'fit_speed_needed': max(1.0, duration / (budget - .08)),
               'sample_rate': int(stream['sample_rate']), 'channels': stream['channels'],
               'model': plan['speech_model'], 'voice_id': plan['voice_id'], 'speed': cue['speed'],
               'subtitles_available': (ROOT / cue['subtitles_file']).exists(),
               'client_wall_s': time.monotonic() - start, 'command': cmd}
        save(receipt, row)
        rows.append(row)
        save(ROOT / 'synthesis_results.json', {'status': 'RUNNING', 'clips': rows})
        print(json.dumps({'status': 'GENERATED', 'cue': cue['id'], 'duration_s': duration,
                          'window_s': budget, 'fit_speed_needed': row['fit_speed_needed']}, ensure_ascii=False), flush=True)
    save(ROOT / 'synthesis_results.json', {'status': 'PASS', 'clips': rows})

if __name__ == '__main__':
    main()
