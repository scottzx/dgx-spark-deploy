#!/usr/bin/env python3
"""Record and pause the explicitly authorized competing Spark model services."""
import json
import os
from pathlib import Path
import signal
import subprocess
import time

root = Path('/home/admin/digital-human-runtime')
snapshot_path = root / 'services_before_tests.json'
patterns = ('sol_api_server.py', 'sol_async_gateway.py', 'session_fifo_proxy.py')
rows = subprocess.check_output(['ps', '-eo', 'pid=,ppid=,args='], text=True)
processes = {}
for line in rows.splitlines():
    pid, ppid, args = line.strip().split(None, 2)
    processes[int(pid)] = {'pid': int(pid), 'ppid': int(ppid), 'command': args}
parents = [pid for pid, p in processes.items()
           if any(pat in p['command'] for pat in patterns)
           and p['command'].split()[0].endswith(('python', 'python3'))]
selected = set(parents)
while True:
    children = {pid for pid, p in processes.items() if p['ppid'] in selected}
    new = children - selected
    if not new:
        break
    selected.update(new)
containers = subprocess.check_output(['docker', 'ps', '--format', '{{.Names}}'], text=True).splitlines()
containers = [n for n in containers if any(x in n.lower() for x in ('qwen', 'sol-h3', 'llama', 'sglang'))]
snapshot = {'recorded_at': time.strftime('%Y-%m-%dT%H:%M:%S%z'),
            'processes': [processes[p] for p in sorted(selected)], 'running_containers': containers}
for p in snapshot['processes']:
    try:
        p['cwd'] = os.readlink(f"/proc/{p['pid']}/cwd")
    except OSError:
        p['cwd'] = None
if not snapshot_path.exists():
    snapshot_path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2) + '\n')
print(json.dumps(snapshot, ensure_ascii=False, indent=2), flush=True)
for pid in parents:
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
for name in containers:
    subprocess.run(['docker', 'stop', '-t', '25', name], check=True)
deadline = time.monotonic() + 25
while time.monotonic() < deadline and any(Path(f'/proc/{p}').exists() for p in selected):
    time.sleep(1)
for pid in selected:
    if Path(f'/proc/{pid}').exists():
        # Only terminate members of the recorded model process tree.
        try:
            if Path(f'/proc/{pid}/cmdline').read_bytes().replace(b'\0', b' ').decode().strip() == processes[pid]['command']:
                os.kill(pid, signal.SIGTERM)
        except (OSError, ProcessLookupError):
            pass
print(subprocess.check_output(['nvidia-smi'], text=True))
print(subprocess.check_output(['free', '-h'], text=True))
