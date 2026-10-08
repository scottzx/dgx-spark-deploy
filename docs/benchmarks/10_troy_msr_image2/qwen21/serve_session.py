#!/usr/bin/env python3
"""Task-scoped, offline Qwen Image 2.1 session; restore the idle video server."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import signal
import subprocess
import time
import urllib.request

RUNTIME = Path('/home/admin/qwen-image-2.1-runtime')
VIDEO = Path('/home/admin/sol-spark-runtime')


def health(url):
    try:
        with urllib.request.urlopen(url, timeout=3) as response:
            data = response.read()
            try:
                return json.loads(data)
            except (ValueError, UnicodeError):
                return {'http_status': response.status}
    except Exception:
        return None


def write(path, data):
    temporary = path.with_suffix('.partial.json')
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n')
    temporary.replace(path)
    print(json.dumps(data, ensure_ascii=False), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=True)
    receipt = dict(status='checking_idle_video_service', model='Qwen-Image-2.1',
                   backend='sglang', steps=40, lora=None, offline=True)
    locks, server, paused = [], None, False
    def interrupted(signum, frame):
        raise SystemExit(128 + signum)
    for signum in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
        signal.signal(signum, interrupted)
    try:
        video_health = health('http://127.0.0.1:8090/health')
        receipt['video_service_before'] = video_health
        pids = subprocess.check_output(['pgrep', '-f', '[s]ol_api_server.py'], text=True).split()
        if len(pids) != 1 or not video_health or video_health.get('status') != 'READY':
            raise RuntimeError('Expected exactly one ready video server')
        if video_health.get('task') != 'fl2va':
            raise RuntimeError('Unexpected video task; preserve its configuration before switching')
        connections = subprocess.run(['lsof', '-nP', '-iTCP:8090', '-sTCP:ESTABLISHED'],
                                     capture_output=True, text=True)
        if connections.stdout.strip():
            raise RuntimeError('Video service has established client connections; leave it running')
        utilization = subprocess.check_output(['nvidia-smi', '--query-gpu=utilization.gpu',
            '--format=csv,noheader,nounits'], text=True).strip()
        if utilization != '0':
            raise RuntimeError('GPU is busy; leave video service running')
        paused = True
        # Graceful Uvicorn shutdown waits for any request arriving during this check.
        os.kill(int(pids[0]), signal.SIGTERM)
        deadline = time.monotonic() + 180
        while subprocess.run(['kill', '-0', pids[0]], capture_output=True).returncode == 0:
            if time.monotonic() > deadline:
                raise RuntimeError('Video server did not finish graceful shutdown; no forced termination')
            time.sleep(2)
        for path in (RUNTIME / 'inference.lock', VIDEO / 'inference.lock'):
            handle = path.open('a')
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            locks.append(handle)
        active = subprocess.check_output(['nvidia-smi', '--query-compute-apps=pid',
            '--format=csv,noheader,nounits'], text=True).strip()
        if active:
            raise RuntimeError(f'Other CUDA work remains: {active}')
        if health('http://127.0.0.1:30010/health'):
            raise RuntimeError('Image service port is already occupied')
        env = dict(os.environ, HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1',
            CUDA_VISIBLE_DEVICES='0', PYTHONUNBUFFERED='1', CUDA_HOME='/usr/local/cuda',
            PYTHONPATH=str(RUNTIME / 'sglang-test/python'),
            CPATH=f'{VIDEO}/sysroot/usr/include/python3.12:{VIDEO}/sysroot/usr/include')
        env['PATH'] = str(RUNTIME / 'sglang-venv/bin') + ':/usr/local/cuda/bin:' + env.get('PATH', '')
        command = [str(RUNTIME / 'sglang-venv/bin/sglang'), 'serve', '--model-path',
            '/home/admin/models_cache/Qwen-Image-2.1', '--model-id', 'Qwen-Image-2.1',
            '--performance-mode', 'speed', '--attention-backend', 'torch_sdpa',
            '--backend', 'sglang', '--host', '127.0.0.1', '--port', '30010']
        receipt.update(status='loading_qwen', server_command=command)
        write(out / 'session.json', receipt)
        started = time.monotonic()
        with (out / 'sglang-server.log').open('w') as log:
            server = subprocess.Popen(command, env=env, stdout=log, stderr=subprocess.STDOUT,
                                      start_new_session=True)
        while not health('http://127.0.0.1:30010/health'):
            if server.poll() is not None or time.monotonic() - started > 900:
                raise RuntimeError('Qwen server failed to become healthy; inspect its log')
            time.sleep(2)
        receipt.update(status='qwen_ready', startup_seconds=time.monotonic() - started)
        write(out / 'session.json', receipt)
        deadline = time.monotonic() + 2700
        while not (out / 'STOP').exists():
            if server.poll() is not None:
                raise RuntimeError('Qwen server exited unexpectedly')
            if time.monotonic() > deadline:
                raise RuntimeError('Session limit reached; restoring video service')
            time.sleep(2)
        receipt['status'] = 'generation_finished'
    except BaseException as error:
        receipt.update(status='failed', error=str(error))
        raise
    finally:
        if server is not None and server.poll() is None:
            os.killpg(server.pid, signal.SIGTERM)
            try:
                server.wait(timeout=40)
            except subprocess.TimeoutExpired:
                os.killpg(server.pid, signal.SIGKILL)
                server.wait(timeout=15)
        for handle in locks:
            handle.close()
        if paused:
            receipt['status_before_restore'] = receipt['status']
            receipt['status'] = 'restoring_video_service'
            write(out / 'session.json', receipt)
            if not health('http://127.0.0.1:8090/health'):
                env = dict(os.environ, SOL_TASK='fl2va', SOL_PATHS_FILE=str(VIDEO / 'paths.json'))
                with (out / 'restored-video-server.log').open('w') as log:
                    restore = subprocess.Popen(['bash', str(VIDEO / 'start_sol_server.sh')],
                        env=env, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
                receipt['restored_server_pid'] = restore.pid
            deadline = time.monotonic() + 1200
            while time.monotonic() < deadline:
                state = health('http://127.0.0.1:8090/health')
                if state and state.get('status') == 'READY' and state.get('task') == 'fl2va':
                    receipt.update(video_service_restored=True, video_service_after=state)
                    break
                time.sleep(3)
            receipt['status'] = 'complete' if receipt.get('video_service_restored') else 'restore_failed'
        write(out / 'session.json', receipt)
        if paused and not receipt.get('video_service_restored'):
            raise RuntimeError('Video server restoration did not become healthy')


if __name__ == '__main__':
    main()
