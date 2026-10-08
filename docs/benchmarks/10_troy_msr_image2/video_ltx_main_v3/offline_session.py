#!/usr/bin/env python3
"""Wait for owned API captures, run offline phases, and restore the original service."""
import fcntl,json,os,signal,subprocess,time,urllib.request
from pathlib import Path
ROOT=Path(__file__).resolve().parent;VIDEO=Path('/home/admin/sol-spark-runtime')
def save(x):
 p=ROOT/'session.json';t=p.with_suffix('.partial.json');t.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n');t.replace(p);print(json.dumps(x,ensure_ascii=False),flush=True)
def health():
 try:
  with urllib.request.urlopen('http://127.0.0.1:8090/health',timeout=3) as r:return json.load(r)
 except Exception:return None
def active_cuda():return subprocess.check_output(['nvidia-smi','--query-compute-apps=pid','--format=csv,noheader,nounits'],text=True).strip()
def drain(timeout=300):
 deadline=time.monotonic()+timeout
 while active_cuda():
  if time.monotonic()>deadline:raise TimeoutError('CUDA processes remain; preserve them without forced termination')
  time.sleep(2)
def main():
 receipt=dict(status='waiting_for_h3_captures',started_unix=time.time(),phases=[]);locks=[];paused=False;child=None
 def interrupted(sig,frame):raise SystemExit(128+sig)
 for sig in (signal.SIGINT,signal.SIGTERM,signal.SIGHUP):signal.signal(sig,interrupted)
 env=dict(os.environ,SOL_H3_SPARK_RUNTIME_ROOT=str(VIDEO),CUDA_VISIBLE_DEVICES='0',CUDA_HOME='/usr/local/cuda',
          CPATH=f'{VIDEO}/sysroot/usr/include/python3.12:{VIDEO}/sysroot/usr/include',PATH='/home/admin/.local/bin:/usr/local/cuda/bin:'+os.environ.get('PATH',''),
          OMP_NUM_THREADS='1',HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',TORCHINDUCTOR_COMPILE_THREADS='1',PYTHONPATH=str(VIDEO),PYTHONUNBUFFERED='1')
 save(receipt)
 try:
  deadline=time.monotonic()+2400
  while True:
   p=ROOT/'h3_capture_results.json'
   if p.exists() and json.loads(p.read_text()).get('status')=='PASS':break
   if time.monotonic()>deadline:raise TimeoutError('H3 captures not complete; leave original service running')
   time.sleep(3)
  before=health();pids=subprocess.check_output(['pgrep','-f','[s]ol_api_server.py'],text=True).split()
  assert len(pids)==1 and before and before['status']=='READY' and before['task']=='fl2va',before
  baseline=json.loads((ROOT/'h3_service_before.json').read_text())
  assert before['requests_served']==baseline['requests_served']+3,'Other clients have used this service; preserve it for review'
  assert not subprocess.run(['lsof','-nP','-iTCP:8090','-sTCP:ESTABLISHED'],capture_output=True,text=True).stdout.strip(),'active clients'
  deadline=time.monotonic()+60
  while subprocess.check_output(['nvidia-smi','--query-gpu=utilization.gpu','--format=csv,noheader,nounits'],text=True).strip()!='0':
   if time.monotonic()>deadline:raise RuntimeError('GPU busy; preserve the original service')
   time.sleep(2)
  receipt.update(status='pausing_idle_service',video_service_before=before,original_server_pid=int(pids[0]));save(receipt)
  paused=True;os.kill(int(pids[0]),signal.SIGTERM);deadline=time.monotonic()+180
  while subprocess.run(['kill','-0',pids[0]],capture_output=True).returncode==0:
   if time.monotonic()>deadline:raise TimeoutError('Graceful server shutdown timed out')
   time.sleep(2)
  drain()
  for p in (VIDEO/'inference.lock',Path('/home/admin/qwen-image-2.1-runtime/inference.lock')):
   h=p.open('a');fcntl.flock(h,fcntl.LOCK_EX|fcntl.LOCK_NB);locks.append(h)
  for phase,python in [('native','stage1-env'),('caches','stage2-env'),('ltx','stage2-env')]:
   receipt.update(status='offline_'+phase);save(receipt);t=time.monotonic()
   with (ROOT/(phase+'.log')).open('ab') as log:
    child=subprocess.Popen([str(VIDEO/python/'bin/python'),str(ROOT/'run_offline.py'),'--phase',phase],env=env,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
    receipt['child_pid']=child.pid;save(receipt);code=child.wait(timeout=7200)
   receipt['phases'].append(dict(phase=phase,exit_code=code,wall_s=time.monotonic()-t));save(receipt)
   if code:raise RuntimeError(phase+' failed')
   drain()
  receipt.update(generation_status='complete')
 except BaseException as e:
  receipt.update(generation_status='failed',error=repr(e));raise
 finally:
  if child and child.poll() is None:
   os.killpg(child.pid,signal.SIGTERM)
   try:child.wait(timeout=180)
   except subprocess.TimeoutExpired:receipt['child_shutdown_timeout']=True
  for h in locks:h.close()
  if paused:
   receipt['status']='restoring_original_service';save(receipt)
   try:
    drain()
    if not health():
     with (ROOT/'restored_server.log').open('ab') as log:
      restored=subprocess.Popen(['bash',str(VIDEO/'start_sol_server.sh')],env=dict(env,SOL_TASK='fl2va',SOL_PATHS_FILE=str(VIDEO/'paths.json')),stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
     receipt['restored_server_pid']=restored.pid;save(receipt)
    deadline=time.monotonic()+3600
    while time.monotonic()<deadline:
     after=health()
     if after and after['status']=='READY' and after['task']=='fl2va':receipt.update(video_service_restored=True,video_service_after=after);break
     time.sleep(3)
   except Exception as e:receipt['restoration_error']=repr(e)
  receipt.update(status='complete' if receipt.get('generation_status')=='complete' and receipt.get('video_service_restored') else 'needs_attention',finished_unix=time.time());save(receipt)
if __name__=='__main__':main()
