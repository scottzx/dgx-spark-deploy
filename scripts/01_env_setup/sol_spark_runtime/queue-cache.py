import subprocess,time,os
from pathlib import Path
r=Path('/home/admin/sol-spark-runtime');p=Path('/home/admin/sol-h3-spark/models/minimax_h3/Sol-H3-Spark')
for i in range(360):
 if all((r/'receipts'/(key+'.json')).is_file() for key in ['offline_gemma','offline_connector']):break
 time.sleep(30)
else:raise RuntimeError('Offline weights not ready in 3 hours')
env=os.environ.copy()
env.update(PYTHONPATH=str(r/'dependencies/offline-context')+':'+str(p),CPATH=str(r/'sysroot/usr/include/python3.12')+':'+str(r/'sysroot/usr/include'),CUDA_HOME='/usr/local/cuda',CUDA_VISIBLE_DEVICES='0',OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1',HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',PYTHONNOUSERSITE='1')
print('INT8 files verified; generating fixed prompt cache',flush=True)
subprocess.run(['flock',str(r/'inference.lock'),str(r/'stage2-env/bin/python'),'-m','runtime.cache_builder','--paths',str(r/'component-paths.json'),'--output',str(r/'fixed-prompt.pt')],check=True,env=env,cwd=p)
print('FIXED_PROMPT_CACHE_CREATED',flush=True)
