#!/usr/bin/env python3
"""Call only the task's loopback, self-hosted Qwen Image 2.1 endpoint."""
import argparse
import base64
from contextlib import ExitStack
import hashlib
import importlib.metadata
import io
import json
from pathlib import Path
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--request', type=Path, required=True)
    parser.add_argument('--root', type=Path, required=True)
    args = parser.parse_args()
    import requests
    from PIL import Image, ImageStat
    spec = json.loads(args.request.read_text())
    root = args.root.resolve()
    output = root / spec['output']
    if output.exists() or output.with_suffix('.json').exists():
        raise FileExistsError(output)
    refs = [root / p for p in spec['references']]
    hashes = [hashlib.sha256(p.read_bytes()).hexdigest() for p in refs]
    payload = dict(model='Qwen-Image-2.1', prompt=spec['prompt'], size='1536x864', n=1,
        num_inference_steps=40, guidance_scale=1.0, seed=spec['seed'],
        generator_device='cuda', output_format='png', response_format='b64_json')
    started = time.monotonic()
    with ExitStack() as stack:
        files = [('image[]', (p.name, stack.enter_context(p.open('rb')), 'image/png')) for p in refs]
        response = requests.post('http://127.0.0.1:30010/v1/images/edits', data=payload,
                                 files=files, timeout=1200)
    elapsed = time.monotonic() - started
    if not response.ok:
        raise RuntimeError(f'Local Qwen HTTP {response.status_code}: {response.text[:1800]}')
    data = base64.b64decode(response.json()['data'][0]['b64_json'], validate=True)
    with Image.open(io.BytesIO(data)) as image:
        image.load()
        if image.size != (1536, 864) or max(ImageStat.Stat(image.convert('RGB')).stddev) < 3:
            raise RuntimeError('Unexpected size or uniform output')
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(data)
    versions = {}
    for package in ('sglang', 'torch', 'diffusers', 'transformers'):
        try:
            versions[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            versions[package] = None
    receipt = dict(**spec, source=str(output), model='Qwen-Image-2.1', provider='self-hosted',
        host='spark-e72e', endpoint='http://127.0.0.1:30010/v1/images/edits', backend='sglang',
        precision='BF16', steps=40, lora=None, guidance_scale=1.0, size=[1536, 864],
        seconds=elapsed, timing='HTTP including encoding and loopback transfer',
        reference_sha256=hashes, sha256=hashlib.sha256(data).hexdigest(), bytes=len(data),
        client_versions=versions)
    output.with_suffix('.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({k:v for k,v in receipt.items() if k not in ('prompt','references')}, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
