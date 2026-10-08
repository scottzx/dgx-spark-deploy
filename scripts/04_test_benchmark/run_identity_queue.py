#!/usr/bin/env python3
"""Resume the pinned identity benchmark with exclusive GPU ownership.

Completed result files are reused. Download weights before invoking this script.
Use --stop-server-pid only for the video server that must yield the GPU; the
process identity is checked before signalling. No PID is embedded in the source.
"""
import argparse
import fcntl
import json
import os
from pathlib import Path
import signal
import subprocess
import time

R=Path('/home/admin/sol-spark-runtime');D=R/'identity_tests_20261003'


def completed(path):
 if not path.exists():return False
 result=json.loads(path.read_text())
 return result.get('status')=='PASS'


def main():
 parser=argparse.ArgumentParser(description=__doc__)
 parser.add_argument('--stop-server-pid',type=int)
 parser.add_argument('--restore-server',action='store_true')
 args=parser.parse_args()
 env=dict(os.environ,SOL_H3_SPARK_RUNTIME_ROOT=str(R),CUDA_VISIBLE_DEVICES='0',
  CUDA_HOME='/usr/local/cuda',CPATH=str(R/'sysroot/usr/include/python3.12')+':'+str(R/'sysroot/usr/include'),
  PATH='/home/admin/.local/bin:/usr/local/cuda/bin:'+os.environ.get('PATH',''),OMP_NUM_THREADS='1',
  HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',TORCHINDUCTOR_COMPILE_THREADS='1',
  PYTHONPATH=str(R),PYTHONUNBUFFERED='1')
 if args.stop_server_pid:
  pid=args.stop_server_pid
  command=Path(f'/proc/{pid}/cmdline')
  if command.exists():
   if str(R/'sol_api_server.py') not in command.read_text():
    raise ValueError('Requested PID is not the Sol-H3 video server')
   os.kill(pid,signal.SIGTERM)
   deadline=time.monotonic()+600
   while command.exists():
    if time.monotonic()>deadline:raise TimeoutError('Video server shutdown incomplete')
    time.sleep(3)
 lock=(R/'inference.lock').open('a')
 try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
 except BlockingIOError:raise RuntimeError('A video session still owns the GPU')
 results=[]
 def run(name,cmd,result_path=None):
  if result_path is not None and completed(result_path):
   print(json.dumps(dict(status='REUSED',name=name)),flush=True);return
  print(json.dumps(dict(status='START',name=name)),flush=True)
  started=time.monotonic()
  with (D/(name+'.log')).open('ab') as log:
   proc=subprocess.run(cmd,env=env,stdout=log,stderr=log)
  row=dict(name=name,status='PASS' if proc.returncode==0 else 'FAIL',exit_code=proc.returncode,
   elapsed_s=time.monotonic()-started)
  results.append(row);(D/'queue_results.json').write_text(json.dumps(results,indent=2))
  print(json.dumps(row),flush=True)
  if proc.returncode:raise RuntimeError(f'{name} failed; inspect its saved log before resuming')
 try:
  session=R/'outputs/api_server_runs/session_20261003-235623_ref2va'
  captures=[str(session/c/'stage1') for c in ['identity_ref_opening','identity_ref_continuation','identity_ref_new_angle']]
  run('ref_native_decode',[str(R/'stage1-env/bin/python'),str(R/'decode_h3_identity_baseline.py'),
   '--captures',*captures,'--output',str(D/'ref_native')],D/'ref_native/native_decode.json')
  run('prompt_encode',[str(R/'stage2-env/bin/python'),str(R/'build_identity_prompt_caches.py')])
  run('specific_refiner_trial',[str(R/'stage2-env/bin/torchrun'),'--standalone','--nproc-per-node=1',
   str(R/'refine_identity_capture.py')],D/'specific_refiner/low_noise_result.json')
  for method in ('ingredients','msr'):
   run(method+'_trial',[str(R/'stage2-env/bin/python'),str(R/'run_ltx_identity_trial.py'),
    '--method',method],D/method/'result.json')
  run('optimized_workflows',[str(R/'stage2-env/bin/torchrun'),'--standalone','--nproc-per-node=1',
   str(R/'refine_identity_workflows.py')],D/'optimized_workflows/comparison.json')
 finally:
  fcntl.flock(lock,fcntl.LOCK_UN);lock.close()
  if args.restore_server:
   with (D/'restored_fl_server.log').open('ab') as log:
    server=subprocess.Popen([str(R/'start_sol_server.sh')],stdout=log,stderr=log,stdin=subprocess.DEVNULL,
     env=dict(env,SOL_TASK='fl2va',SOL_PATHS_FILE=str(R/'paths.json')),start_new_session=True)
   (D/'restored_fl_server.pid').write_text(str(server.pid))
   print(json.dumps(dict(status='VIDEO_SERVICE_RESTARTING',pid=server.pid)),flush=True)

if __name__=='__main__':main()
