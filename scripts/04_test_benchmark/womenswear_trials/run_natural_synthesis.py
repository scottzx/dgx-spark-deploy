"""Durable three-route queue using the approved default conversational voice."""
import datetime
import fcntl
import json
import os
from pathlib import Path
import subprocess
import time

ROOT = Path(os.environ.get('AVATAR_BENCH_ROOT', '/home/admin/womenswear-avatar-natural-v2'))
ROOT.mkdir(parents=True, exist_ok=True)
(ROOT/'logs').mkdir(exist_ok=True)
environment = dict(os.environ, AVATAR_BENCH_ROOT=str(ROOT), PYTHONUNBUFFERED='1',
                   HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1')
environment['PATH'] = '/home/admin/.local/bin:'+environment.get('PATH','')
python = '/home/admin/digital-human-runtime/avatar-env/bin/python'
now = lambda: datetime.datetime.now(datetime.timezone.utc).isoformat()
state = {'pid':os.getpid(),'started_at_utc':now(),'state':'running','stages':[],
         'voice_profile':'serena_default','ltx_motion_reused':True}
def save():
    state['updated_at_utc'] = now()
    temporary = ROOT/'queue_status.writing.json'
    temporary.write_text(json.dumps(state,ensure_ascii=False,indent=2)+'\n')
    temporary.replace(ROOT/'queue_status.json')
queue_lock = (ROOT/'queue.lock').open('w')
fcntl.flock(queue_lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
for stage in ('latentsync','longcat','infinitetalk'):
    marker = ROOT/'logs'/f'{stage}.done.json'
    if marker.exists():
        state['stages'].append(json.loads(marker.read_text()));save();continue
    command = [python,str(ROOT/f'run_{stage}.py')]
    item = {'stage':stage,'state':'running','started_at_utc':now(),'command':command}
    state['stages'].append(item);state['current_stage']=stage;save()
    print(json.dumps(item),flush=True)
    started = time.perf_counter()
    with (ROOT/'logs'/f'{stage}.log').open('a') as stream:
        result = subprocess.run(command,cwd=ROOT,env=environment,stdout=stream,stderr=subprocess.STDOUT)
    item.update(returncode=result.returncode,seconds=time.perf_counter()-started,ended_at_utc=now())
    item['state'] = 'complete' if result.returncode==0 else 'failed'
    if result.returncode:
        state['state']='failed';save();raise SystemExit(result.returncode)
    marker.write_text(json.dumps(item,indent=2)+'\n');save()
    print(json.dumps(item),flush=True)
state['state']='complete';state['completed_at_utc']=now();save()
print(json.dumps({'state':'complete','expected_clips':9}),flush=True)
