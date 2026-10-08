#!/usr/bin/env python3
"""Pin public ModelScope files and retain authoritative HF hashes for the remaining models."""
import json
from pathlib import Path

ROOT = Path('/home/admin/avatar-company-tests')
SPECS = {
    'liveportrait': ('KwaiVGI/LivePortrait', ['liveportrait/', 'insightface/']),
    'infinitetalk': ('MeiGen-AI/InfiniteTalk', ['single/']),
    'wan21': ('Wan-AI/Wan2.1-I2V-14B-480P', ['']),
    'longcat': ('meituan-longcat/LongCat-Video-Avatar-1.5', ['base_model/', 'lora/', 'scheduler/', 'whisper-large-v3/', 'vocal_separator/']),
    'longcat_base': ('meituan-longcat/LongCat-Video', ['tokenizer/', 'text_encoder/', 'vae/', 'scheduler/']),
    'gemma3': ('google/gemma-3-12b-it-qat-q4_0-unquantized', ['']),
}
rows = []
for name, (repo, prefixes) in SPECS.items():
    files = json.loads((ROOT / (repo.replace('/', '_') + '_ms.json')).read_text())
    count = 0
    size = 0
    for file in files:
        path = file['Path']
        if file['Type'] != 'blob' or not any(path.startswith(prefix) for prefix in prefixes): continue
        if path.startswith('.') or path.endswith(('.md', '.mp4', '.png', '.jpg', '.gif', '.msgpack')): continue
        if any(part in path for part in ['fp32', 'flax', 'pytorch_model.bin']): continue
        rows.append({'provider': 'modelscope', 'repo': repo, 'revision': file['Revision'], 'name': path,
                     'target': name + '/' + path, 'size': file['Size'], 'sha256': file['Sha256']})
        count += 1
        size += file['Size']
    print(name, count, round(size / 1e9, 2), flush=True)
(ROOT / 'modelscope_range_manifest.json').write_text(json.dumps(rows, indent=2) + '\n')
for name in ['latentsync', 'joyhallo', 'avatarforever']:
    old = json.loads((ROOT / (name + '_model_manifest.json')).read_text())
    new = [{'repo': row['repo'], 'revision': row['revision'], 'name': row['file'],
            'target': name + '/' + row['file'], 'size': row['size'], 'sha256': row['expected_sha256']} for row in old]
    (ROOT / (name + '_range_manifest.json')).write_text(json.dumps(new, indent=2) + '\n')
fetch = ROOT / 'fetch_ranges.py'
source = Path('/home/admin/digital-human-runtime/fetch_weights.py').read_text()
source = source.replace('Request(url,headers=', "Request(url + ('&' if '?' in url else '?') + f'benchmark_range={first}',headers=")
fetch.write_text(source)
