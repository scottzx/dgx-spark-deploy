#!/usr/bin/env python3
"""Resolve official model revisions and fetch only the inference files for this comparison."""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import fnmatch
import hashlib
import json
import os
from pathlib import Path
import time
from urllib.request import urlopen

ROOT = Path('/home/admin/avatar-company-tests')
MODEL = Path('/home/admin/models_cache/company_avatars')
SPECS = {
    'latentsync': ('ByteDance/LatentSync-1.6', ['latentsync_unet.pt', 'whisper/tiny.pt']),
    'liveportrait': ('KwaiVGI/LivePortrait', ['liveportrait/*', 'insightface/*']),
    'joyvasa': ('jdh-algo/JoyVASA', ['*.pth', '*.pkl', '*.json', '*.pt']),
    'hubert': ('TencentGameMate/chinese-hubert-base', ['*.bin', '*.json']),
    'joyhallo': ('jdh-algo/JoyHallo-v1', ['*.pth', '*.json']),
    'hallo_base': ('fudan-generative-ai/hallo', ['*']),
    'infinitetalk': ('MeiGen-AI/InfiniteTalk', ['single/infinitetalk.safetensors']),
    'wan21': ('Wan-AI/Wan2.1-I2V-14B-480P', ['*.pth', '*.safetensors', '*.json', '*.model', '*.txt']),
    'longcat': ('meituan-longcat/LongCat-Video-Avatar-1.5', ['*']),
    'avatarforever': ('LetsThink/AvatarForever', ['*.safetensors']),
}
parser = argparse.ArgumentParser()
parser.add_argument('names', nargs='+', choices=list(SPECS))
args = parser.parse_args()
MODEL.mkdir(parents=True, exist_ok=True)
os.environ['HF_HUB_DISABLE_XET'] = '1'
from huggingface_hub import hf_hub_download

def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        while b := f.read(8 * 1024 * 1024): h.update(b)
    return h.hexdigest()

def resolve(name):
    repo, patterns = SPECS[name]
    with urlopen(f'https://huggingface.co/api/models/{repo}?blobs=true', timeout=60) as response:
        info = json.load(response)
    rows = []
    for item in info['siblings']:
        file = item['rfilename']
        if not any(fnmatch.fnmatch(file, pattern) for pattern in patterns): continue
        if file.startswith('.') or file.endswith(('.md', '.mp4', '.jpg', '.png', '.zip', '.gif')): continue
        if any(part in file.lower() for part in ['animals', 'int8', 'multi/', 'optimizer']): continue
        rows.append({'repo': repo, 'revision': info['sha'], 'file': file, 'size': item.get('size'),
                     'expected_sha256': item.get('lfs', {}).get('sha256')})
    (ROOT / f'{name}_model_manifest.json').write_text(json.dumps(rows, indent=2) + '\n')
    print(json.dumps({'stage': 'resolved', 'name': name, 'files': len(rows), 'gigabytes': sum(r['size'] or 0 for r in rows)/1e9}), flush=True)
    return rows

def fetch(name, row):
    start = time.monotonic()
    path = Path(hf_hub_download(row['repo'], row['file'], revision=row['revision'], local_dir=str(MODEL/name)))
    actual = sha(path)
    if row['expected_sha256'] and actual != row['expected_sha256']: raise RuntimeError(f'Hash mismatch: {path}')
    if row['size'] is not None and path.stat().st_size != row['size']: raise RuntimeError(f'Size mismatch: {path}')
    receipt = {**row, 'path': str(path), 'sha256': actual, 'seconds': time.monotonic()-start}
    print(json.dumps({'stage': 'verified', 'name': name, 'file': row['file'], 'seconds': receipt['seconds']}), flush=True)
    return receipt

receipts = []
for name in args.names:
    rows = resolve(name)
    with ThreadPoolExecutor(4) as pool:
        pending = [pool.submit(fetch, name, row) for row in rows]
        for future in as_completed(pending):
            receipts.append(future.result())
            (ROOT / ('download_receipt_' + '_'.join(args.names) + '.json')).write_text(json.dumps(receipts, indent=2) + '\n')
print('DOWNLOAD COMPLETE', args.names, flush=True)
