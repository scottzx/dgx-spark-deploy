"""Durable measured queue; the existing business services remain paused."""
import datetime
import fcntl
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from config import ROOT, CASES

ROOT.mkdir(parents=True,exist_ok=True)
(ROOT/'logs').mkdir(exist_ok=True)
environment=dict(os.environ,AVATAR_BENCH_ROOT=str(ROOT),PYTHONUNBUFFERED='1',
                 HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1')
environment['PATH']='/home/admin/.local/bin:'+environment.get('PATH','')
STAGE2='/home/admin/sol-spark-runtime/stage2-env/bin/python'
AVATAR='/home/admin/digital-human-runtime/avatar-env/bin/python'
stages=[('voice',[AVATAR,str(ROOT/'prepare_voice.py')],True),
        ('cache',[STAGE2,str(ROOT/'run_ltx.py'),'cache'],True),
        ('ltx',[STAGE2,str(ROOT/'run_ltx.py'),'generate'],True),
        ('inputs',[AVATAR,str(ROOT/'prepare_inputs.py')],False),
        ('latentsync',[AVATAR,str(ROOT/'run_latentsync.py')],False),
        ('longcat',[AVATAR,str(ROOT/'run_longcat.py')],False),
        ('infinitetalk',[AVATAR,str(ROOT/'run_infinitetalk.py')],False)]

def now():return datetime.datetime.now(datetime.timezone.utc).isoformat()
state={'pid':os.getpid(),'started_at_utc':now(),'state':'running','stages':[]}
def save():
    state['updated_at_utc']=now()
    temp=ROOT/'queue_status.writing.json'
    temp.write_text(json.dumps(state,ensure_ascii=False,indent=2)+'\n')
    temp.replace(ROOT/'queue_status.json')

queue_lock=(ROOT/'queue.lock').open('w')
fcntl.flock(queue_lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
for stage,command,needs_lock in stages:
    if stage=='cache':
        state['current_stage']='waiting_portrait_assets';save()
        while not (ROOT/'assets_ready.json').exists():time.sleep(5)
    marker=ROOT/'logs'/f'{stage}.done.json'
    if marker.exists():
        state['stages'].append(json.loads(marker.read_text()));save();continue
    item={'stage':stage,'state':'running','started_at_utc':now(),'command':command}
    state['stages'].append(item);state['current_stage']=stage;save()
    print(json.dumps(item),flush=True)
    lock=None;started=time.perf_counter()
    if needs_lock:
        lock=(ROOT/'gpu.lock').open('w');fcntl.flock(lock,fcntl.LOCK_EX)
    try:
        with (ROOT/'logs'/f'{stage}.log').open('a') as stream:
            result=subprocess.run(command,cwd=ROOT,env=environment,stdout=stream,stderr=subprocess.STDOUT)
    finally:
        if lock:lock.close()
    item.update(returncode=result.returncode,seconds=time.perf_counter()-started,ended_at_utc=now())
    item['state']='complete' if result.returncode==0 else 'failed'
    if result.returncode:
        state['state']='failed';save();raise SystemExit(result.returncode)
    marker.write_text(json.dumps(item,indent=2)+'\n');save()
    print(json.dumps(item),flush=True)
state['state']='complete';state['completed_at_utc']=now();save()
print(json.dumps({'state':'complete','expected_clips':len(CASES)*3}),flush=True)
