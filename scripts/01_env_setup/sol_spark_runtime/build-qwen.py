import subprocess,time
from pathlib import Path
r=Path('/home/admin/sol-spark-runtime')
base='nvcr.io/nvidia/pytorch:25.11-py3@sha256:417cbf33f87b5378849df37983552cd1f8bc8b62fe1ceabe004de816a55dff21'
for attempt in range(240):
 if subprocess.run(['docker','image','inspect',base],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode==0:break
 time.sleep(30)
else:raise RuntimeError('NGC base not ready within 2 hours')
print('NGC base ready; building Qwen image',flush=True)
subprocess.run(['docker','build','--progress=plain','-f',str(r/'Dockerfile.qwen.local'),'-t','sol-h3-spark-qwen',str(r/'sources')],check=True)
print('QWEN_IMAGE_BUILT',flush=True)
