"""Shared measurement and media helpers for official-model benchmark runs."""
import fcntl
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

ROOT = Path(os.environ.get('AVATAR_BENCH_ROOT', '/home/admin/avatar-company-tests'))
MODELS = Path('/home/admin/models_cache/company_avatars')
os.environ['PATH'] = '/home/admin/.local/bin:' + os.environ.get('PATH', '')
os.environ['HF_HUB_OFFLINE'] = '1'
os.environ['TRANSFORMERS_OFFLINE'] = '1'
os.environ.setdefault('CPATH', '/home/admin/sol-spark-runtime/sysroot/usr/include/python3.12:/home/admin/sol-spark-runtime/sysroot/usr/include')

def gpu_lock():
    handle = (ROOT / 'gpu.lock').open('w')
    fcntl.flock(handle, fcntl.LOCK_EX)
    return handle

def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        while block := stream.read(8 * 1024 * 1024):
            digest.update(block)
    return digest.hexdigest()

def jobs():
    return json.loads((ROOT / 'inputs/manifest.json').read_text())

def cpu_onnx():
    import onnxruntime as ort
    original = ort.InferenceSession
    class CPUSession(original):
        def __init__(self, path, sess_options=None, providers=None, provider_options=None, **kwargs):
            options = sess_options or ort.SessionOptions()
            options.intra_op_num_threads = 4
            options.inter_op_num_threads = 1
            super().__init__(path, sess_options=options, providers=['CPUExecutionProvider'], **kwargs)
    ort.InferenceSession = CPUSession

def trusted_torch_load():
    import torch
    original = torch.load
    def load(*args, **kwargs):
        kwargs.setdefault('weights_only', False)
        return original(*args, **kwargs)
    torch.load = load

def link(target, path):
    target, path = Path(target), Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink():
        if path.resolve() != target.resolve():
            raise RuntimeError(f'Unexpected existing symlink: {path}')
    elif not path.exists():
        path.symlink_to(target, target_is_directory=target.is_dir())

def mux(native, job, out):
    """Trim longer output; normalize an exact one-frame rounding tail by display hold."""
    native, out = Path(native), Path(out)
    info = json.loads(subprocess.check_output(['ffprobe', '-v', 'error', '-show_streams', '-of', 'json', str(native)]))
    video = next(s for s in info['streams'] if s['codec_type'] == 'video')
    duration = float(video.get('duration', 0))
    if duration < 8.00:
        raise RuntimeError(f'Incomplete native video: {duration:.3f}s; retained at {native}')
    hold = 0.0
    filters = ['fps=25']
    if abs(duration-8.0)<1e-6 and video.get('avg_frame_rate')=='25/1' and int(video.get('nb_frames',0))==200:
        hold = 0.04
        filters.append('tpad=stop_mode=clone:stop_duration=0.04')
    encoded = out/'video.normalizing.mp4'
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', str(native), '-i', str(Path(job['directory'])/'audio.wav'),
                    '-map', '0:v:0', '-map', '1:a:0', '-vf', ','.join(filters), '-t', '8.04',
                    '-c:v', 'libx264', '-crf', '18', '-pix_fmt', 'yuv420p', '-c:a', 'aac', str(encoded)], check=True)
    subprocess.run(['ffmpeg', '-v', 'error', '-i', str(encoded), '-f', 'null', '-'], check=True)
    encoded.replace(out/'video.mp4')
    return {'native_duration_seconds': duration, 'native_output_sha256': sha(native), 'video_sha256': sha(out/'video.mp4'),
            'final_frame_hold_seconds':hold, 'normalization_note':'Exact 200-frame/8.00s native output: one 40ms display hold of its final real frame.' if hold else 'Trim only; no tail hold.'}

def save_frames(frames, path, fps=25):
    import imageio_ffmpeg
    import numpy as np
    frames = iter(frames)
    first = np.ascontiguousarray(np.asarray(next(frames), dtype=np.uint8))
    height, width = first.shape[:2]
    writer = imageio_ffmpeg.write_frames(str(path), (width, height), fps=fps, codec='libx264',
                                         pix_fmt_in='rgb24', pix_fmt_out='yuv420p', quality=8,
                                         macro_block_size=1, ffmpeg_log_level='error')
    writer.send(None)
    count = 0
    try:
        writer.send(first); count += 1
        for frame in frames:
            writer.send(np.ascontiguousarray(np.asarray(frame, dtype=np.uint8))); count += 1
    finally:
        writer.close()
    return count

def receipt(engine, job, source, out, native, loaded_seconds, render_start, extra):
    import torch
    torch.cuda.synchronize()
    render_seconds = time.perf_counter() - render_start
    peak = torch.cuda.max_memory_allocated() / 2**30
    data = {'engine': engine, 'product': job['product'], 'input_sha256': job['input_sha256'],
            'commit': subprocess.check_output(['git', '-C', str(source), 'rev-parse', 'HEAD'], text=True).strip(),
            'shared_model_load_seconds': loaded_seconds, 'render_seconds': render_seconds,
            'peak_cuda_allocated_gib': peak, 'native_output': str(native), **extra}
    data.update(mux(native, job, out))
    (out/'metrics.json').write_text(json.dumps(data, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps(data, ensure_ascii=False), flush=True)
    return data
