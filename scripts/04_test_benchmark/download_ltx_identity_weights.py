#!/usr/bin/env python3
"""Download verified ModelScope mirrors using resumable bounded range requests."""
import argparse
import hashlib
import json
from pathlib import Path
import time
import urllib.request

MODELS = [
 ('Lightricks/LTX-2.5-22b-IC-LoRA-Ingredients',
  'ltx-2.5-22b-ic-lora-ingredients-0.9.safetensors', 1308787472,
  'ff873a5beada3c579a8137c7c53343916f78bcc9a529ba910143073fe8715e95'),
 ('LiconStudio/LTX-2.5-Multiple-Subject-Reference',
  'LTX-2.5-Licon-MSR-V2.safetensors', 2215094328,
  '7cf982168d4f77f44b02943fb458f937f90c89335dcf7cf71b2f425e78bab713'),
]

def download(root, repo, filename, size, sha):
 url = f'https://modelscope.cn/api/v1/models/{repo}/repo?Revision=master&FilePath={filename}'
 path = root / filename
 partial = path.with_suffix('.part')
 if not path.exists():
  offset = partial.stat().st_size if partial.exists() else 0
  with partial.open('ab') as target:
   while offset < size:
    end = min(size, offset + 4 * 1024**2) - 1
    for attempt in range(5):
     try:
      request = urllib.request.Request(url + f'&range_offset={offset}', headers={'Range': f'bytes={offset}-{end}'})
      with urllib.request.urlopen(request, timeout=30) as source:
       expected = f'bytes {offset}-{end}/{size}'
       if source.status not in (200,206) or source.headers.get('Content-Range') != expected:
        raise ValueError('Unexpected range response')
       chunk = source.read(end - offset + 1)
      if len(chunk) != end - offset + 1:
       raise ValueError('Incomplete range response')
      break
     except Exception as exc:
      if attempt == 4: raise
      print(json.dumps(dict(status='RETRY',file=filename,offset=offset,error=type(exc).__name__)),flush=True)
      time.sleep(2**attempt)
    target.write(chunk)
    target.flush()
    offset += len(chunk)
    print(json.dumps(dict(status='DOWNLOADING',file=filename,bytes=offset,total=size)),flush=True)
  with partial.open('rb') as source:
   digest = hashlib.file_digest(source, 'sha256').hexdigest()
  if partial.stat().st_size != size or digest != sha:
   raise ValueError('ModelScope mirror does not match official Hub SHA-256')
  partial.rename(path)
 with path.open('rb') as source:
  digest = hashlib.file_digest(source, 'sha256').hexdigest()
 if path.stat().st_size != size or digest != sha:
  raise ValueError('Existing weight checksum mismatch')
 result = dict(status='PASS',source='ModelScope',repo=repo,file=filename,bytes=size,sha256=sha,
  checksum_source='official Hugging Face revision metadata, independently verified')
 (root / (filename + '.receipt.json')).write_text(json.dumps(result,indent=2)+'\n')
 print(json.dumps(result),flush=True)

def main():
 parser = argparse.ArgumentParser(description=__doc__)
 parser.add_argument('--output',type=Path,required=True)
 args = parser.parse_args()
 args.output.mkdir(parents=True,exist_ok=True)
 for model in MODELS: download(args.output,*model)

if __name__ == '__main__': main()
