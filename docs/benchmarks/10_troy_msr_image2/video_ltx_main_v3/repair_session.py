#!/usr/bin/env python3
"""Extend this owned GPU session, then resume its original restoration supervisor."""
import json,os,signal,subprocess,time
from pathlib import Path
ROOT=Path(__file__).resolve().parent;RUNTIME=Path('/home/admin/sol-spark-runtime')
def save(x):
    p=ROOT/'repairs/session.json';t=p.with_suffix('.partial.json');t.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n');t.replace(p);print(json.dumps(x),flush=True)
def state(pid):
    p=Path('/proc')/str(pid)/'stat'
    return p.read_text().rsplit(')',1)[1].split()[0] if p.exists() else None
def cuda():return subprocess.check_output(['nvidia-smi','--query-compute-apps=pid','--format=csv,noheader,nounits'],text=True).strip()
def main():
    owner=json.loads((ROOT/'launch.json').read_text())['supervisor']
    base=json.loads((ROOT/'session.json').read_text());assert base['status']=='offline_ltx'
    assert state(owner)=='T','Only extend the explicitly suspended owned supervisor'
    parent_manifest=json.loads((ROOT/'manifest.json').read_text())
    repairs=json.loads((ROOT/'repairs/manifest.json').read_text());assert repairs['base_manifest_fingerprint']==parent_manifest['fingerprint']
    receipt=dict(status='waiting_for_base_ltx',started_unix=time.time(),supervisor_pid=owner,base_child_pid=base['child_pid'],phases=[]);child=None;save(receipt)
    def interrupted(sig,frame):raise SystemExit(128+sig)
    for sig in (signal.SIGINT,signal.SIGTERM,signal.SIGHUP):signal.signal(sig,interrupted)
    env=dict(os.environ,SOL_H3_SPARK_RUNTIME_ROOT=str(RUNTIME),CUDA_VISIBLE_DEVICES='0',CUDA_HOME='/usr/local/cuda',CPATH=f'{RUNTIME}/sysroot/usr/include/python3.12:{RUNTIME}/sysroot/usr/include',PATH='/home/admin/.local/bin:/usr/local/cuda/bin:'+os.environ.get('PATH',''),OMP_NUM_THREADS='1',HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',TORCHINDUCTOR_COMPILE_THREADS='1',PYTHONPATH=str(RUNTIME),PYTHONUNBUFFERED='1')
    try:
        deadline=time.monotonic()+2400
        while state(base['child_pid']) not in (None,'Z','X'):
            if time.monotonic()>deadline:raise TimeoutError('Base LTX process did not finish')
            time.sleep(3)
        rows=json.loads((ROOT/'ltx_results.json').read_text());assert rows['status']=='PASS' and len(rows['clips'])==17
        deadline=time.monotonic()+180
        while cuda():
            if time.monotonic()>deadline:raise TimeoutError('GPU remains occupied; preserve other processes')
            time.sleep(2)
        for phase in ('caches','ltx'):
            receipt.update(status='repair_'+phase);save(receipt);t=time.monotonic()
            with (ROOT/'repairs'/(phase+'.log')).open('ab') as log:
                child=subprocess.Popen([str(RUNTIME/'stage2-env/bin/python'),str(ROOT/'run_repairs.py'),'--phase',phase],env=env,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
                receipt['child_pid']=child.pid;save(receipt);code=child.wait(timeout=1800)
            receipt['phases'].append(dict(phase=phase,exit_code=code,wall_s=time.monotonic()-t));save(receipt)
            if code:raise RuntimeError('Repair phase failed: '+phase)
        receipt['generation_status']='complete'
    except BaseException as e:
        receipt.update(generation_status='failed',error=repr(e));raise
    finally:
        if child and child.poll() is None:
            os.killpg(child.pid,signal.SIGTERM)
            try:child.wait(timeout=180)
            except subprocess.TimeoutExpired:receipt['child_shutdown_timeout']=True
        os.kill(owner,signal.SIGCONT)
        receipt.update(status='complete' if receipt.get('generation_status')=='complete' else 'needs_attention',supervisor_resumed=True,finished_unix=time.time());save(receipt)
if __name__=='__main__':main()
