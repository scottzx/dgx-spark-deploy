#!/usr/bin/env python3
"""Bind the existing, user-approved generated actions and Serena audio to this suite."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

ROOT = Path('/home/admin/avatar-company-tests')
BASE = Path('/home/admin/digital-human-runtime')
OUT = ROOT / 'inputs'
OUT.mkdir(parents=True, exist_ok=True)
jobs = []
for index, (key, label, appearance) in enumerate([
    ('original', '原味', 'the red and white Coca-Cola Original can on the left'),
    ('diet', '健怡', 'the silver and red Diet Coke can in the middle'),
    ('zero', '零度', 'the red and black Coca-Cola Zero can on the right'),
]):
    case = OUT / key
    case.mkdir(exist_ok=True)
    files = {
        'driver.mp4': BASE / 'outputs/product_actions_ltx' / key / 'motion.mp4',
        'audio.wav': BASE / 'inputs/product_actions_serena' / f'{key}.wav',
        'audio_16k.wav': BASE / 'inputs/product_actions_serena' / f'{key}_16k.wav',
        'reference.png': BASE / 'inputs/product_actions/table.png',
    }
    hashes = {}
    for name, source in files.items():
        shutil.copy2(source, case / name)
        hashes[name] = hashlib.sha256((case / name).read_bytes()).hexdigest()
    subprocess.run(['/home/admin/.local/bin/ffmpeg', '-v', 'error', '-y', '-ss', '0',
                    '-i', str(case / 'driver.mp4'), '-frames:v', '1', str(case / 'first_frame.png')], check=True)
    prompt = (f'A fixed medium shot of an adult Chinese woman with shoulder-length black hair and a red long-sleeved top '
              f'sitting behind a light gray table in a gray studio. Exactly three drink cans stay visible. '
              f'She starts with empty hands, picks up {appearance}, holds that same can at chest height with its front '
              f'facing the camera, speaks naturally to introduce it, then puts that same can back at its original '
              f'position and releases it, ending with both hands empty on the table. The other two cans stay on '
              f'the table throughout. One continuous shot; realistic hand contact, consistent identity, can colors '
              f'and packaging. During the silent beginning and ending her mouth is relaxed and closed.')
    (case / 'prompt.txt').write_text(prompt + '\n')
    jobs.append({'product': key, 'label': label, 'directory': str(case), 'seed': 2026100800 + index,
                 'duration_seconds': 8.04, 'frames': 201, 'fps': 25, 'input_sha256': hashes,
                 'input_kind': 'generated_LTX_video', 'prompt': prompt})
shutil.copy2(BASE / 'inputs/product_actions_serena/voice.json', OUT / 'voice.json')
(OUT / 'manifest.json').write_text(json.dumps(jobs, ensure_ascii=False, indent=2) + '\n')
print(json.dumps({'cases': len(jobs), 'manifest': str(OUT / 'manifest.json')}))
