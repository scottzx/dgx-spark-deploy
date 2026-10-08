#!/usr/bin/env python3
"""Generate eight shared assets, then compare six-reference composition on three backends."""
import argparse
import base64
from contextlib import ExitStack
import fcntl
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import urllib.request

ROOT = Path('/home/admin/qwen-image-2.1-runtime')
MODEL = '/home/admin/models_cache/Qwen-Image-2.1'
CONTAINER = 'qwen3-8-flash-next'
CHARACTERS = [
    ('man', 'one East Asian man aged 35, short neatly combed black hair, clean shaven, rectangular black glasses, forest-green zip jacket over a white T-shirt, dark navy trousers, white sneakers'),
    ('woman', 'one East Asian woman aged 32, straight shoulder-length black bob hair, round face, red cardigan over a cream blouse, blue jeans, white sneakers'),
    ('child', 'one East Asian boy aged 7, short black bowl-cut hair, yellow hooded sweatshirt, bright blue shorts, red sneakers'),
    ('cat', 'one orange tabby cat with a white muzzle, white chest and four white paws, green eyes, a purple collar'),
    ('dog', 'one medium-sized black and white border collie dog with upright ears, a white blaze down the forehead and nose, white chest, a blue collar'),
]
BACKGROUNDS = [
    ('indoor', 'a spacious modern family living room, beige sofa against the back wall, tall window on the left, a wooden bookcase on the right, open light oak floor in the foreground, warm daylight'),
    ('playground', 'a school athletics playground, red rubber running track in the foreground, green sports field behind it, a low school building in the distance, clear sunny afternoon'),
    ('beach', 'a tranquil sandy beach, broad open dry sand in the foreground, turquoise ocean and gentle waves behind it, a rocky headland on the right, warm late-afternoon sunlight'),
]


def manifest():
    assets = []
    for i, (name, description) in enumerate(CHARACTERS):
        assets.append(dict(name=name, seed=1101+i, size=[768, 1024], references=[], transparent=True,
            prompt='This is an RGBA image with transparency. Photorealistic character asset, ' + description + '. Full body entirely visible, standing naturally, facing the camera, centered, realistic anatomy and proportions, soft even studio lighting, sharp detailed face or muzzle. Exactly one subject, no objects, no text. The image has alpha channel and the background is transparent.'))
    for i, (name, description) in enumerate(BACKGROUNDS):
        assets.append(dict(name=name, seed=1201+i, size=[1344, 768], references=[], transparent=False,
            prompt='Photorealistic cinematic wide establishing photograph of ' + description + '. Eye-level camera, realistic perspective, plenty of unobstructed foreground space for a family group. Empty environment, no people, no animals, no text. Opaque image.'))
    scenes = []
    for i, (name, description) in enumerate(BACKGROUNDS):
        scenes.append(dict(name=name, seed=1301+i, size=[1344, 768], transparent=False,
            references=[f'assets/{n}.png' for n, _ in CHARACTERS] + [f'assets/{name}.png'],
            prompt='Create one photorealistic wide family group photograph by combining all six reference images. Image 1 is the man, image 2 is the woman, image 3 is the boy, image 4 is the orange and white cat, image 5 is the black and white border collie, and image 6 is the background. Preserve the exact facial identity, hairstyle, clothing and colors of each person, and the fur markings and collar of each animal. Use image 6 as the scene and preserve its architecture, layout, camera perspective and major landmarks: ' + description + '. Show exactly three humans and two animals, all five full bodies clearly visible with no cropping. Place the man on the left, the boy in the middle, and the woman on the right, standing together facing the camera. Place the cat sitting in the foreground left near the man, and the dog sitting in the foreground right near the woman. The boy is realistically shorter than the adults, the dog larger than the cat. Natural shared lighting, grounded feet and paws, physically plausible contact shadows. A coherent photograph, no panels, no collage borders, no duplicate subjects, no extra people or animals, no text. Output an opaque image.'))
    return dict(assets=assets, scenes=scenes, policy='One shared base-40-step asset set; identical original PNG references, prompts, dimensions and seeds for all three composition backends. One sample per scene/backend, no quality retries.')


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2))


def record(out, case, variant, data, seconds, **extra):
    from PIL import Image, ImageStat
    import io
    relative = f"assets/{case['name']}.png" if variant == 'asset-base' else f"{variant}/{case['name']}.png"
    path = out / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    with Image.open(io.BytesIO(data)) as img:
        img.load()
        hist = img.getchannel('A').histogram() if 'A' in img.getbands() else None
        alpha_fraction = sum(hist[:6]) / (img.width*img.height) if hist else 0
        valid = list(img.size) == case['size'] and max(ImageStat.Stat(img.convert('RGB')).stddev) > 1
        if case['transparent']:
            valid = valid and alpha_fraction > .001 and sum(hist[250:]) > 0
        row = dict(variant=variant, case=case['name'], seconds=seconds, file=relative,
                   sha256=hashlib.sha256(data).hexdigest(), size=img.size,
                   transparent_fraction=alpha_fraction, structural_check_passed=valid,
                   reference_sha256=[hashlib.sha256((out / p).read_bytes()).hexdigest() for p in case['references']], **extra)
    with (out / 'requests.jsonl').open('a') as stream:
        stream.write(json.dumps(row) + '\n')
    print(json.dumps(row), flush=True)
    if not valid:
        raise RuntimeError(f'Structural check failed: {relative}')


def diffusers_worker(out, spec):
    import io
    import torch
    from PIL import Image
    from diffusers import QwenImage21Pipeline, FlowMatchEulerDiscreteScheduler
    started = time.perf_counter()
    pipe = QwenImage21Pipeline.from_pretrained(MODEL, dtype=torch.bfloat16, local_files_only=True)
    base_config = dict(pipe.scheduler.config)
    pipe.load_lora_weights(str(ROOT / 'turbo'), weight_name='Qwen-Image-2.1-viggle-turbo-v0.2.1-6step-lora-r256.safetensors', local_files_only=True)
    pipe.disable_lora()
    pipe.to('cuda')
    torch.cuda.synchronize()
    write_json(out / 'diffusers-environment.json', dict(load_seconds=time.perf_counter()-started,
        versions={p: importlib.metadata.version(p) for p in ('torch', 'diffusers', 'transformers', 'peft')}, gpu=torch.cuda.get_device_name()))
    def generate(case, variant):
        options = dict(prompt=case['prompt'], width=case['size'][0], height=case['size'][1],
            generator=torch.Generator('cuda').manual_seed(case['seed']), true_cfg_scale=1.0,
            num_inference_steps=6 if variant == 'turbo' else 40)
        refs = []
        for p in case['references']:
            with Image.open(out / p) as image:
                refs.append(image.copy())
        if refs:
            options['image'] = refs
        if variant == 'turbo':
            options['sigmas'] = [1.0, .9375, .875, .75, .5, .25]
        torch.cuda.reset_peak_memory_stats()
        torch.cuda.synchronize()
        start = time.perf_counter()
        result = pipe(**options).images[0]
        torch.cuda.synchronize()
        elapsed = time.perf_counter()-start
        buffer = io.BytesIO()
        result.save(buffer, format='PNG')
        record(out, case, variant, buffer.getvalue(), elapsed, timing='pipeline excluding PNG encoding',
            steps=options['num_inference_steps'], seed=case['seed'], peak_cuda_gib=torch.cuda.max_memory_allocated()/2**30)
    for case in spec['assets']:
        generate(case, 'asset-base')
    for variant in ('turbo', 'base'):
        if variant == 'turbo':
            pipe.enable_lora()
            pipe.scheduler = FlowMatchEulerDiscreteScheduler.from_config(base_config, shift_terminal=None)
        else:
            pipe.disable_lora()
            pipe.scheduler = FlowMatchEulerDiscreteScheduler.from_config(base_config)
        for case in spec['scenes']:
            generate(case, variant)


def http_worker(out, spec):
    import requests
    session = requests.Session()
    for case in spec['scenes']:
        payload = dict(prompt=case['prompt'], size='x'.join(map(str, case['size'])), n=1,
            num_inference_steps=40, guidance_scale=1.0, seed=case['seed'], generator_device='cuda',
            output_format='png', response_format='b64_json')
        with ExitStack() as stack:
            files = [('image[]', (Path(p).name, stack.enter_context((out / p).open('rb')), 'image/png')) for p in case['references']]
            start = time.perf_counter()
            response = session.post('http://127.0.0.1:30010/v1/images/edits', data=payload, files=files, timeout=1200)
            elapsed = time.perf_counter()-start
        if not response.ok:
            raise RuntimeError(f'HTTP {response.status_code}: {response.text[:2000]}')
        data = base64.b64decode(response.json()['data'][0]['b64_json'], validate=True)
        record(out, case, 'sglang', data, elapsed, timing='HTTP including PNG encoding and transfer', steps=40, seed=case['seed'])


def healthy(url):
    try:
        with urllib.request.urlopen(url, timeout=2) as response:
            return response.status == 200
    except Exception:
        return False


def supervise(out):
    def interrupt(signum, frame):
        raise SystemExit(128+signum)
    for signum in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
        signal.signal(signum, interrupt)
    out.mkdir(parents=True, exist_ok=False)
    write_json(out / 'manifest.json', manifest())
    locks = []
    for path in (ROOT / 'inference.lock', Path('/home/admin/sol-spark-runtime/inference.lock')):
        handle = path.open('a')
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        locks.append(handle)
    paused = False
    child = None
    server = None
    receipt = dict(status='starting')
    env = dict(os.environ, HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1', CUDA_VISIBLE_DEVICES='0', PYTHONUNBUFFERED='1')
    def stop(process):
        if process is not None and process.poll() is None:
            os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=30)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait(timeout=10)
    try:
        names = subprocess.check_output(['docker', 'ps', '--format', '{{.Names}}'], text=True).splitlines()
        if CONTAINER in names:
            with urllib.request.urlopen('http://127.0.0.1:8001/slots', timeout=5) as response:
                slots = json.load(response)
            if not slots or not all(s.get('is_processing') is False for s in slots):
                raise RuntimeError('Language model has active requests')
            paused = True
            subprocess.run(['docker', 'stop', '--timeout', '60', CONTAINER], check=True)
        active = subprocess.check_output(['nvidia-smi', '--query-compute-apps=pid', '--format=csv,noheader,nounits'], text=True).strip()
        if active:
            raise RuntimeError(f'Other CUDA work active: {active}')
        child = subprocess.Popen([str(ROOT / 'venv/bin/python'), __file__, '--mode', 'diffusers', '--output', str(out)], env=env, start_new_session=True)
        if child.wait() != 0:
            raise RuntimeError('Diffusers worker failed')
        env.update(PYTHONPATH=str(ROOT / 'sglang-test/python'), CUDA_HOME='/usr/local/cuda',
            CPATH='/home/admin/sol-spark-runtime/sysroot/usr/include/python3.12:/home/admin/sol-spark-runtime/sysroot/usr/include')
        env['PATH'] = str(ROOT / 'sglang-venv/bin') + ':/usr/local/cuda/bin:' + os.environ.get('PATH', '')
        command = [str(ROOT / 'sglang-venv/bin/sglang'), 'serve', '--model-path', MODEL, '--model-id', 'Qwen-Image-2.1',
            '--performance-mode', 'speed', '--attention-backend', 'torch_sdpa', '--backend', 'sglang', '--host', '127.0.0.1', '--port', '30010']
        started = time.monotonic()
        with (out / 'sglang-server.log').open('w') as log:
            server = subprocess.Popen(command, env=env, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        while not healthy('http://127.0.0.1:30010/health'):
            if server.poll() is not None or time.monotonic()-started > 900:
                raise RuntimeError('SGLang failed to start; inspect server log')
            time.sleep(2)
        receipt['sglang_startup_seconds'] = time.monotonic()-started
        child = subprocess.Popen([str(ROOT / 'sglang-venv/bin/python'), __file__, '--mode', 'http', '--output', str(out)], env=env, start_new_session=True)
        if child.wait() != 0:
            raise RuntimeError('SGLang HTTP worker failed')
        receipt['status'] = 'generated_pending_visual_review'
    except BaseException as error:
        receipt.update(status='failed', error=str(error))
        raise
    finally:
        stop(child)
        stop(server)
        if paused:
            subprocess.run(['docker', 'start', CONTAINER], check=True)
            deadline = time.monotonic()+180
            while not healthy('http://127.0.0.1:8001/health') and time.monotonic() < deadline:
                time.sleep(2)
            receipt['language_model_restored'] = healthy('http://127.0.0.1:8001/health')
        write_json(out / 'run.json', receipt)
        print(json.dumps(receipt), flush=True)
        if paused and not receipt.get('language_model_restored'):
            raise RuntimeError('Language model restoration failed')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode', choices=['supervise', 'diffusers', 'http'], default='supervise')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.mode == 'supervise':
        supervise(args.output)
    else:
        spec = json.loads((args.output / 'manifest.json').read_text())
        (diffusers_worker if args.mode == 'diffusers' else http_worker)(args.output, spec)
