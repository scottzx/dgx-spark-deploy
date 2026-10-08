#!/usr/bin/env python3
"""Resume the video phase after the task-owned image-service shutdown."""
import fcntl,json,os,signal,subprocess,time,urllib.request
from pathlib import Path
ROOT=Path(__file__).resolve().parent;VIDEO=Path('/home/admin/sol-spark-runtime')
def save(x):
 p=ROOT/'video_session.json';t=p.with_suffix('.partial.json');t.write_text(json.dumps(x,indent=2,ensure_ascii=False)+'\n');t.replace(p);print(json.dumps(x,ensure_ascii=False),flush=True)
def health():
 try:
  with urllib.request.urlopen('http://127.0.0.1:8090/health',timeout=3) as r:return json.load(r)
 except Exception:return None
def main():
 original=json.loads((ROOT/'session.json').read_text());assert original['video_service_before']['task']=='fl2va' and original['generation_status']=='generation_failed'
 receipt=dict(status='checking_exclusive_resume',started_unix=time.time(),video_service_before=original['video_service_before'],phases=[],resume_reason=original['error']);locks=[];child=None;owned=False
 def interrupted(sig,frame):raise SystemExit(128+sig)
 for sig in (signal.SIGINT,signal.SIGTERM,signal.SIGHUP):signal.signal(sig,interrupted)
 env=dict(os.environ,SOL_H3_SPARK_RUNTIME_ROOT=str(VIDEO),CUDA_VISIBLE_DEVICES='0',CUDA_HOME='/usr/local/cuda',CPATH=f'{VIDEO}/sysroot/usr/include/python3.12:{VIDEO}/sysroot/usr/include',PATH='/home/admin/.local/bin:/usr/local/cuda/bin:'+os.environ.get('PATH',''),OMP_NUM_THREADS='1',HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',TORCHINDUCTOR_COMPILE_THREADS='1',PYTHONPATH=str(VIDEO),PYTHONUNBUFFERED='1')
 try:
  assert not health(),'Service already resumed; do not interrupt'
  assert subprocess.run(['pgrep','-f','[s]ol_api_server.py'],capture_output=True).returncode==1,'Video server still exists'
  assert subprocess.run(['pgrep','-f','[s]glang serve'],capture_output=True).returncode==1,'Image server still exists'
  for p in (VIDEO/'inference.lock',Path('/home/admin/qwen-image-2.1-runtime/inference.lock')):
   h=p.open('a');fcntl.flock(h,fcntl.LOCK_EX|fcntl.LOCK_NB);locks.append(h)
  deadline=time.monotonic()+180
  while subprocess.check_output(['nvidia-smi','--query-compute-apps=pid','--format=csv,noheader,nounits'],text=True).strip():
   if time.monotonic()>deadline:raise RuntimeError('CUDA has not drained; no forced GPU termination')
   time.sleep(2)
  owned=True
  for phase in ('caches','render'):
   receipt.update(status='video_'+phase);save(receipt);t0=time.monotonic()
   with (ROOT/(phase+'.log')).open('ab') as log:
    child=subprocess.Popen([str(VIDEO/'stage2-env/bin/python'),str(ROOT/'run_trials.py'),'--phase',phase],env=env,stdin=subprocess.DEVNULL,stdout=log,stderr=log,start_new_session=True)
    receipt['child_pid']=child.pid;save(receipt);code=child.wait(timeout=10800)
   receipt['phases'].append(dict(phase=phase,exit_code=code,wall_s=time.monotonic()-t0));save(receipt)
   if code:raise RuntimeError(phase+' failed')
  receipt.update(status='generation_complete')
 except BaseException as e:receipt.update(status='generation_failed',error=repr(e));raise
 finally:
  if child and child.poll() is None:
   os.killpg(child.pid,signal.SIGTERM)
   try:child.wait(timeout=40)
   except subprocess.TimeoutExpired:os.killpg(child.pid,signal.SIGKILL);child.wait(timeout=15)
  for h in locks:h.close()
  if owned:
   receipt['generation_status']=receipt['status'];receipt['status']='restoring_service';save(receipt)
   if not health():
    with (ROOT/'restored-video-server-final.log').open('ab') as log:
     restored=subprocess.Popen(['bash',str(VIDEO/'start_sol_server.sh')],env=dict(env,SOL_TASK='fl2va',SOL_PATHS_FILE=str(VIDEO/'paths.json')),stdin=subprocess.DEVNULL,stdout=log,stderr=log,start_new_session=True)
    receipt['restored_server_pid']=restored.pid;save(receipt)
   deadline=time.monotonic()+3600
   while time.monotonic()<deadline:
    after=health()
    if after and after['status']=='READY' and after['task']=='fl2va':receipt.update(video_service_restored=True,video_service_after=after);break
    time.sleep(3)
   receipt['status']='complete' if receipt.get('video_service_restored') and receipt['generation_status']=='generation_complete' else 'needs_attention'
  receipt['finished_unix']=time.time();save(receipt)
if __name__=='__main__':main()
