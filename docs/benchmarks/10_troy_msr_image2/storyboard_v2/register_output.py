#!/usr/bin/env python3
"""Keep unchanged imagegen output copies and a versioned generation receipt."""
import hashlib
import json
from pathlib import Path
import shutil
import struct
import sys

root = Path(__file__).resolve().parent.parent
row = json.loads(sys.argv[1])
source = Path(row['source'])
data = source.read_bytes()
assert data[:8] == bytes([137, 80, 78, 71, 13, 10, 26, 10])
destination = root / row['frame_file']
sha = hashlib.sha256(data).hexdigest()
if destination.exists():
    assert hashlib.sha256(destination.read_bytes()).hexdigest() == sha
else:
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
row.update(width=struct.unpack('>I', data[16:20])[0],
           height=struct.unpack('>I', data[20:24])[0],
           sha256=sha, bytes=len(data), copy_matches_source=True)
is_asset = row['kind'] == 'asset'
receipt = root / ('combat_asset_manifest.json' if is_asset else 'storyboard_v2/results.json')
result = json.loads(receipt.read_text())
key = 'assets' if is_asset else 'shots'
previous = next((r for r in result[key] if r['id'] == row['id']), None)
if previous and previous['source'] != source.as_posix():
    row['previous_versions'] = previous.get('previous_versions', []) + [
        {k: v for k, v in previous.items() if k != 'previous_versions'}]
result[key] = [r for r in result[key] if r['id'] != row['id']] + [row]
result[key].sort(key=lambda r: r['id'])
result['generated_count'] = len(result[key])
expected = result['expected_assets' if is_asset else 'expected_shots']
result['status'] = 'all_generated_pending_review' if len(result[key]) == expected else 'in_progress'
receipt.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
print(json.dumps({'id': row['id'], 'saved': row['frame_file'], 'count': len(result[key])}, ensure_ascii=False))
