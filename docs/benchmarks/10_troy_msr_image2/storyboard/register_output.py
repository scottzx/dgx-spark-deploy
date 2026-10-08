#!/usr/bin/env python3
"""Copy an imagegen output unchanged and persist a storyboard generation receipt."""
import hashlib
import json
from pathlib import Path
import shutil
import struct
import sys

root = Path(__file__).resolve().parent.parent
row = json.loads(sys.argv[1])
source = Path(row['source'])
destination = root / row['frame_file']
data = source.read_bytes()
assert data[:8] == b'\x89PNG\r\n\x1a\n', source
sha = hashlib.sha256(data).hexdigest()
destination.parent.mkdir(parents=True, exist_ok=True)
if destination.exists():
    assert hashlib.sha256(destination.read_bytes()).hexdigest() == sha, destination
else:
    shutil.copy2(source, destination)
row.update(width=struct.unpack('>I',data[16:20])[0],
           height=struct.unpack('>I',data[20:24])[0],
           sha256=sha, bytes=len(data), copy_matches_source=True)
receipt = root/'storyboard/results.json'
result = json.loads(receipt.read_text()) if receipt.exists() else {
    'title':'木马计：开门','version':'v1','expected_shots':16,
    'generation_tool':'built-in image_gen','model_version_reported_by_tool':None,
    'shots':[]}
previous = next((r for r in result['shots'] if r['id'] == row['id']), None)
if previous and previous['source'] != row['source']:
    history = previous.get('previous_versions', [])
    archived = {k:v for k,v in previous.items() if k != 'previous_versions'}
    row['previous_versions'] = history + [archived]
result['shots'] = [r for r in result['shots'] if r['id'] != row['id']] + [row]
result['shots'].sort(key=lambda r:r['id'])
result['generated_count'] = len(result['shots'])
result['status'] = 'all_frames_generated' if len(result['shots']) == 16 else 'in_progress'
receipt.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'id':row['id'],'generated_count':len(result['shots']),'file':row['frame_file']},ensure_ascii=False))
