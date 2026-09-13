"""Generate one H3 test clip, preserving job state and frames for visual QA.

Usage on the server: python verify_h3_video.py RUN_NAME SHORT_EDGE SIGMA_POINTS
SIGMA_POINTS includes terminal zero in this H3 backend (5 means 4 evaluations).
File completion is not a visual quality pass.
"""
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

base = 'http://127.0.0.1:30010'
run = Path('/home/admin/h3-lightning/runs') / sys.argv[1]
run.mkdir(parents=True, exist_ok=True)
assert not (run/'job.json').exists(), 'Use a fresh run name; do not resubmit an existing job'
payload = {
    'model': 'MiniMaxAI/MiniMax-H3', 'task': 't2va',
    'prompt': 'A dancer performs a flowing routine in a bright studio, full body shot, smooth camera movement, photorealistic.',
    'conditions': [],
    'target': {'short_edge': int(sys.argv[2]), 'aspect_ratio': '16:9', 'duration_seconds': 5.0},
    'num_inference_steps': int(sys.argv[3]), 'flow_shift': 12.0,
    'audio_flow_shift': 3.0, 'seed': 20260901,
}

def api(path, data=None):
    request = Request(base + path, data=None if data is None else json.dumps(data).encode(),
                      headers={'Content-Type': 'application/json'})
    with urlopen(request, timeout=600 if data is not None else 15) as response:
        return json.load(response)

deadline = time.monotonic() + 900
while True:
    try:
        api('/health')
        break
    except (HTTPError, URLError, TimeoutError):
        if time.monotonic() > deadline:
            raise TimeoutError('Server readiness timed out')
        time.sleep(10)

(run/'request.json').write_text(json.dumps(payload, indent=2))
started = time.monotonic()
job = api('/v1/videos', payload)  # Never retry this POST automatically.
print('Submitted:', job['id'], 'run:', run, flush=True)
last_notice = 0
while True:
    (run/'job.json').write_text(json.dumps(job, indent=2))
    if job['status'] == 'completed':
        break
    if job['status'] in {'failed', 'error', 'cancelled', 'deleted'}:
        raise RuntimeError(job)
    elapsed = time.monotonic() - started
    if elapsed > 7200:
        raise TimeoutError(f"Job {job['id']}; preserve run state and inspect server")
    if elapsed - last_notice >= 60:
        print(f"Elapsed {elapsed:.0f}s; API status={job['status']}", flush=True)
        last_notice = elapsed
    time.sleep(5)
    try:
        job = api('/v1/videos/' + job['id'])
    except (HTTPError, URLError, TimeoutError) as exc:
        print('GET retry:', type(exc).__name__, flush=True)

video = run/'video.mp4'
with urlopen(base + '/v1/videos/' + job['id'] + '/content', timeout=120) as response:
    with video.open('wb') as output:
        shutil.copyfileobj(response, output)
ffmpeg = shutil.which('ffmpeg') or '/home/admin/.local/bin/ffmpeg'
ffprobe = shutil.which('ffprobe') or '/home/admin/.local/bin/ffprobe'
probe = subprocess.check_output([ffprobe, '-v', 'error', '-show_streams', '-show_format', '-of', 'json', str(video)], text=True)
(run/'ffprobe.json').write_text(probe)
subprocess.run([ffmpeg, '-v', 'error', '-i', str(video), '-vf', r'select=eq(n\,0)+eq(n\,24)+eq(n\,60)',
                '-vsync', 'vfr', str(run/'frame_%02d.png')], check=True)
metrics = {'elapsed_s': time.monotonic()-started, 'inference_time_s': job.get('inference_time_s'),
           'peak_memory_mb': job.get('peak_memory_mb'), 'visual_quality': 'PENDING_HUMAN_OR_VISION_REVIEW'}
(run/'metrics.json').write_text(json.dumps(metrics, indent=2))
print('File generation complete; visual review still required:', metrics, flush=True)
