import subprocess,time
from pathlib import Path
r=Path('/home/admin/sol-spark-runtime')
for i in range(5):
 p=subprocess.run(['docker','pull','nvcr.io/nvidia/pytorch:25.11-py3@sha256:417cbf33f87b5378849df37983552cd1f8bc8b62fe1ceabe004de816a55dff21'])
 if p.returncode==0:break
 print('Retrying NGC pull',i,flush=True);time.sleep(15)
else:raise RuntimeError('NGC pull failed after retries')
