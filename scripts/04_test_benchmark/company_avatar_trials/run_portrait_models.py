#!/usr/bin/env python3
"""Exercise official LivePortrait or JoyVASA models; disclose every driving source."""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

ROOT = Path('/home/admin/avatar-company-tests')
MODEL = Path('/home/admin/models_cache/company_avatars')
os.environ['PATH'] = '/home/admin/.local/bin:' + os.environ.get('PATH', '')
parser = argparse.ArgumentParser()
parser.add_argument('--engine', choices=['liveportrait', 'joyvasa'], required=True)
parser.add_argument('--products', nargs='+', default=['original', 'diet', 'zero'])
args = parser.parse_args()
lock = (ROOT / 'gpu.lock').open('w')
fcntl.flock(lock, fcntl.LOCK_EX)
source = ROOT / 'sources' / ('LivePortrait' if args.engine == 'liveportrait' else 'JoyVASA')
os.chdir(source)
sys.path.insert(0, str(source))
os.environ['HF_HUB_OFFLINE'] = '1'
os.environ['TRANSFORMERS_OFFLINE'] = '1'
sys.path.insert(0, str(ROOT / 'deps/common'))
import torch
import onnxruntime as ort

# ARM64 currently has CPU ONNX Runtime. The neural renderer still runs on GB10.
original_session = ort.InferenceSession
class CPUSession(original_session):
    def __init__(self, path, sess_options=None, providers=None, provider_options=None, **kwargs):
        options = sess_options or ort.SessionOptions()
        options.intra_op_num_threads = 4
        options.inter_op_num_threads = 1
        super().__init__(path, sess_options=options, providers=['CPUExecutionProvider'], **kwargs)
ort.InferenceSession = CPUSession

# Official JoyVASA checkpoints include configuration objects as well as tensors.
original_load = torch.load
def trusted_checkpoint_load(*positional, **kwargs):
    kwargs.setdefault('weights_only', False)
    return original_load(*positional, **kwargs)
torch.load = trusted_checkpoint_load

def link(target, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink():
        if path.resolve() != target.resolve(): raise RuntimeError(f'Unexpected existing link: {path}')
    elif not path.exists(): path.symlink_to(target, target_is_directory=target.is_dir())

weights = source / 'pretrained_weights'
weights.mkdir(exist_ok=True)
link(MODEL / 'liveportrait/liveportrait', weights / 'liveportrait')
link(MODEL / 'liveportrait/insightface', weights / 'insightface')
if args.engine == 'joyvasa':
    link(MODEL / 'joyvasa', weights / 'JoyVASA')
    link(MODEL / 'hubert', weights / 'hubert-base-ls960')
    link(MODEL / 'hubert', weights / 'chinese-hubert-base')
    link(MODEL / 'hubert', weights / 'TencentGameMate:chinese-hubert-base')

from src.config.argument_config import ArgumentConfig
from src.config.inference_config import InferenceConfig
from src.config.crop_config import CropConfig
if args.engine == 'liveportrait':
    from src.live_portrait_pipeline import LivePortraitPipeline
else:
    from src.modules.hubert import HubertModel
    original_hubert_loader = HubertModel.from_pretrained
    @classmethod
    def eager_hubert(cls, *positional, **kwargs):
        kwargs['attn_implementation'] = 'eager'
        return original_hubert_loader(*positional, **kwargs)
    HubertModel.from_pretrained = eager_hubert
    from src.live_portrait_wmg_pipeline import LivePortraitPipeline

def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()

start = time.perf_counter()
pipeline = LivePortraitPipeline(inference_cfg=InferenceConfig(), crop_cfg=CropConfig())
torch.cuda.synchronize()
loaded = time.perf_counter()
print(json.dumps({'stage': 'loaded', 'engine': args.engine, 'seconds': loaded-start}), flush=True)
jobs = json.loads((ROOT / 'inputs/manifest.json').read_text())
for job in jobs:
    name = job['product']
    if name not in args.products: continue
    case = Path(job['directory'])
    out = ROOT / 'outputs' / args.engine / name
    out.mkdir(parents=True, exist_ok=True)
    torch.manual_seed(job['seed'])
    torch.cuda.reset_peak_memory_stats()
    kwargs = dict(output_dir=str(out), flag_do_crop=True, flag_pasteback=True, flag_stitching=True,
                  flag_relative_motion=True, flag_use_half_precision=True, flag_do_torch_compile=False,
                  flag_source_video_eye_retargeting=False)
    if args.engine == 'liveportrait':
        driver = Path('/home/admin/digital-human-runtime/outputs/product_actions_dubbed_serena_smooth') / name / 'dubbed.mp4'
        if not driver.is_file(): raise FileNotFoundError(driver)
        options = ArgumentConfig(source=str(case/'driver.mp4'), driving=str(driver), animation_region='lip',
                                 flag_crop_driving_video=True, audio_priority='driving', **kwargs)
        scope = 'Lip-region retargeting onto LTX action video. Driver is the previously generated Serena/MuseTalk video; this is not an independent audio-to-motion model.'
    else:
        driver = case/'audio_16k.wav'
        options = ArgumentConfig(reference=str(case/'first_frame.png'), audio=str(driver), animation_mode='human',
                                 animation_region='all', cfg_scale=2.8, **kwargs)
        scope = 'Official image-and-audio portrait animation. Hands and products originate from one still image; this test does not generate pickup/return actions.'
    render_start = time.perf_counter()
    with torch.inference_mode(): result = pipeline.execute(options)
    torch.cuda.synchronize()
    rendered = time.perf_counter()
    if isinstance(result, tuple): native = Path(result[0])
    else:
        native = max([p for p in out.glob('*.mp4') if 'concat' not in p.name], key=lambda p: p.stat().st_mtime)
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', str(native), '-i', str(case/'audio.wav'),
                    '-map', '0:v:0', '-map', '1:a:0', '-vf', 'fps=25', '-t', '8.04',
                    '-c:v', 'libx264', '-crf', '18', '-pix_fmt', 'yuv420p', '-c:a', 'aac', str(out/'video.mp4')], check=True)
    receipt = {'engine': args.engine, 'product': name, 'scope': scope, 'input_sha256': job['input_sha256'],
               'driver': str(driver), 'driver_sha256': sha(driver), 'native_output': str(native),
               'native_output_sha256': sha(native), 'video_sha256': sha(out/'video.mp4'),
               'shared_model_load_seconds': loaded-start, 'render_seconds': rendered-render_start,
               'peak_cuda_allocated_gib': torch.cuda.max_memory_allocated()/2**30,
               'commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip(),
               'compatibility': ['CPU ONNX face detection/landmarks, four threads', 'PyTorch trusted official checkpoint weights_only=False'] +
                                (['HuBERT eager attention restores original attention-output behavior'] if args.engine == 'joyvasa' else []),
               'model_generates_product_actions': False, 'original_LTX_actions_preserved': args.engine == 'liveportrait'}
    (out/'metrics.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps(receipt, ensure_ascii=False), flush=True)
