"""Verify that each candidate contains the exact same decoded speech as its baseline."""
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[3]/'docs/benchmarks/14_company_avatar_comparison'
target = ROOT/'audio_verification.json'
cached = {r['path']:r for r in json.loads(target.read_text())['clips']} if target.exists() else {}
rows = []
baselines = {}
paths = sorted(p for p in (ROOT/'baseline').glob('*.mp4') if p.name!='three_products.mp4')
paths += sorted((ROOT/'results').glob('*/*/video.mp4'))
for path in paths:
    key = str(path.relative_to(ROOT))
    video_hash = hashlib.sha256(path.read_bytes()).hexdigest()
    row = cached.get(key)
    if not row or row['video_sha256']!=video_hash:
        pcm = subprocess.check_output(['ffmpeg','-v','error','-i',str(path),'-map','0:a:0',
                                       '-f','s16le','-ac','1','-ar','24000','-'])
        row = {'path':key,'video_sha256':video_hash,
               'pcm_sha256':hashlib.sha256(pcm).hexdigest(),'samples':len(pcm)//2}
    if key.startswith('baseline/'):
        baselines[path.stem] = row
        row['matches_baseline'] = True
    else:
        baseline = baselines[path.parent.name]
        row['matches_baseline'] = (row['pcm_sha256']==baseline['pcm_sha256'] and
                                   row['samples']==baseline['samples'])
        if not row['matches_baseline']:
            raise RuntimeError(f'Audio differs from the shared Serena baseline: {key}')
    rows.append(row)
target.write_text(json.dumps({'sample_rate':24000,'channels':1,'format':'decoded signed 16-bit PCM',
                              'note':'Decoded sample counts include AAC trailing packet padding. Compilations are re-encoded and verified separately for duration.',
                              'clips':rows},ensure_ascii=False,indent=2)+'\n')
print(f'Same Serena audio verified: {len(rows)-3} candidate clips')
