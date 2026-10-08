#!/usr/bin/env python3
"""One exclusive GPU session: Qwen edits, internal frame review, video trials, restore."""
import fcntl,json,os,signal,subprocess,time,urllib.request
from pathlib import Path
ROOT=Path(__file__).resolve().parent
VIDEO=Path('/home/admin/sol-spark-runtime');IMAGE=Path('/home/admin/qwen-image-2.1-runtime')
def save(x):
 p=ROOT/'session.json';t=p.with_suffix('.partial.json');t.write_text(json.dumps(x,indent=2,ensure_ascii=False)+'\n');t.replace(p);print(json.dumps(x,ensure_ascii=False),flush=True)
def health(port):
 try:
  with urllib.request.urlopen(f'http://127.0.0.1:{port}/health',timeout=3) as r:return json.load(r)
 except Exception:return None
def stop(child):
 if child and child.poll() is None:
  os.killpg(child.pid,signal.SIGTERM)
  try:child.wait(timeout=40)
  except subprocess.TimeoutExpired:os.killpg(child.pid,signal.SIGKILL);child.wait(timeout=15)
def main():
 receipt=dict(status='checking_idle',started_unix=time.time(),phases=[])
 locks=[];paused=False;image=None;child=None
 def interrupted(sig,frame):raise SystemExit(128+sig)
 for sig in (signal.SIGINT,signal.SIGTERM,signal.SIGHUP):signal.signal(sig,interrupted)
 env=dict(os.environ,SOL_H3_SPARK_RUNTIME_ROOT=str(VIDEO),CUDA_VISIBLE_DEVICES='0',CUDA_HOME='/usr/local/cuda',CPATH=f'{VIDEO}/sysroot/usr/include/python3.12:{VIDEO}/sysroot/usr/include',PATH='/home/admin/.local/bin:/usr/local/cuda/bin:'+os.environ.get('PATH',''),OMP_NUM_THREADS='1',HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',TORCHINDUCTOR_COMPILE_THREADS='1',PYTHONPATH=str(VIDEO),PYTHONUNBUFFERED='1')
 image_env=dict(env,PYTHONPATH=str(IMAGE/'sglang-test/python'));image_env['PATH']=str(IMAGE/'sglang-venv/bin')+':'+env['PATH']
 try:
  before=health(8090);pids=subprocess.check_output(['pgrep','-f','[s]ol_api_server.py'],text=True).split()
  receipt['video_service_before']=before
  assert len(pids)==1 and before and before['status']=='READY' and before['task']=='fl2va',before
  assert not subprocess.run(['lsof','-nP','-iTCP:8090','-sTCP:ESTABLISHED'],capture_output=True,text=True).stdout.strip(),'active clients'
  assert subprocess.check_output(['nvidia-smi','--query-gpu=utilization.gpu','--format=csv,noheader,nounits'],text=True).strip()=='0','GPU busy'
  receipt.update(status='pausing_idle_service',original_server_pid=int(pids[0]));save(receipt)
  paused=True;os.kill(int(pids[0]),signal.SIGTERM);deadline=time.monotonic()+180
  while subprocess.run(['kill','-0',pids[0]],capture_output=True).returncode==0:
   if time.monotonic()>deadline:raise TimeoutError('Graceful shutdown timeout')
   time.sleep(2)
  for p in (VIDEO/'inference.lock',IMAGE/'inference.lock'):
   h=p.open('a');fcntl.flock(h,fcntl.LOCK_EX|fcntl.LOCK_NB);locks.append(h)
  assert not subprocess.check_output(['nvidia-smi','--query-compute-apps=pid','--format=csv,noheader,nounits'],text=True).strip(),'other CUDA work'
  assert not health(30010),'image port occupied'
  cmd=[str(IMAGE/'sglang-venv/bin/sglang'),'serve','--model-path','/home/admin/models_cache/Qwen-Image-2.1','--model-id','Qwen-Image-2.1','--performance-mode','speed','--attention-backend','torch_sdpa','--backend','sglang','--host','127.0.0.1','--port','30010']
  with (ROOT/'qwen-server.log').open('ab') as log:image=subprocess.Popen(cmd,env=image_env,stdin=subprocess.DEVNULL,stdout=log,stderr=log,start_new_session=True)
  receipt.update(status='loading_qwen',image_server_pid=image.pid);save(receipt);t0=time.monotonic()
  while not health(30010):
   if image.poll() is not None or time.monotonic()-t0>900:raise RuntimeError('Qwen startup failed')
   time.sleep(2)
  deadline=time.monotonic()+10800
  while not (ROOT/'RUN_VIDEO').exists():
   if (ROOT/'STOP').exists():raise RuntimeError('Session stopped by control file')
   if image.poll() is not None or time.monotonic()>deadline:raise RuntimeError('Image session expired or server exited')
   pending=[p for p in sorted((ROOT/'requests').glob('*.json')) if not (ROOT/json.loads(p.read_text())['output']).exists()]
   # End requests depend on their own start; pick a runnable request.
   pending=[p for p in pending if all((ROOT/q).exists() for q in json.loads(p.read_text())['references'])]
   if not pending:
    if receipt['status']!='awaiting_internal_frame_review':receipt.update(status='awaiting_internal_frame_review');save(receipt)
    time.sleep(2);continue
   p=pending[0];receipt.update(status='generating_keyframe',request=p.name);save(receipt)
   with (ROOT/'qwen-requests.log').open('ab') as log:
    child=subprocess.Popen([str(IMAGE/'sglang-venv/bin/python'),str(ROOT/'generate_frame.py'),'--request',str(p),'--root',str(ROOT)],env=image_env,stdin=subprocess.DEVNULL,stdout=log,stderr=log,start_new_session=True);code=child.wait()
   if code:raise RuntimeError('Image request failed: '+p.name)
  stop(image);receipt.update(status='qwen_stopped_video_start');save(receipt)
  deadline=time.monotonic()+180
  while subprocess.check_output(['nvidia-smi','--query-compute-apps=pid','--format=csv,noheader,nounits'],text=True).strip():
   if time.monotonic()>deadline:raise RuntimeError('CUDA image worker did not drain within180s')
   time.sleep(2)
  for phase in ('caches','render'):
   receipt.update(status='video_'+phase);save(receipt);t0=time.monotonic()
   with (ROOT/(phase+'.log')).open('ab') as log:
    child=subprocess.Popen([str(VIDEO/'stage2-env/bin/python'),str(ROOT/'run_trials.py'),'--phase',phase],env=env,stdin=subprocess.DEVNULL,stdout=log,stderr=log,start_new_session=True)
    try:code=child.wait(timeout=10800)
    except subprocess.TimeoutExpired:raise RuntimeError('Video phase timeout')
   receipt['phases'].append(dict(phase=phase,exit_code=code,wall_s=time.monotonic()-t0));save(receipt)
   if code:raise RuntimeError(phase+' failed')
  receipt['status']='generation_complete'
 except BaseException as e:
  receipt.update(status='generation_failed',error=repr(e));raise
 finally:
  stop(child);stop(image)
  for h in locks:h.close()
  if paused:
   receipt['generation_status']=receipt['status'];receipt['status']='restoring_service';save(receipt)
   if not health(8090):
    with (ROOT/'restored-video-server.log').open('ab') as log:
     restored=subprocess.Popen(['bash',str(VIDEO/'start_sol_server.sh')],env=dict(env,SOL_TASK='fl2va',SOL_PATHS_FILE=str(VIDEO/'paths.json')),stdin=subprocess.DEVNULL,stdout=log,stderr=log,start_new_session=True)
    receipt['restored_server_pid']=restored.pid
   deadline=time.monotonic()+3600
   while time.monotonic()<deadline:
    after=health(8090)
    if after and after['status']=='READY' and after['task']=='fl2va':receipt.update(video_service_restored=True,video_service_after=after);break
    time.sleep(3)
   receipt['status']='complete' if receipt.get('video_service_restored') and receipt['generation_status']=='generation_complete' else 'needs_attention'
  receipt['finished_unix']=time.time();save(receipt)
if __name__=='__main__':main()
