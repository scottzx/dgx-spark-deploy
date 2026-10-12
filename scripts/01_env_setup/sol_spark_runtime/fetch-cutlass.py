import subprocess,os,time
from pathlib import Path
r=Path('/home/admin/sol-spark-runtime')
env=os.environ.copy();env.update(https_proxy='http://127.0.0.1:17890',http_proxy='http://127.0.0.1:17890')
items=[(r/'sources/FastVideo/fastvideo-kernel/include/cutlass','e67e63c331d6e4b729047c95cf6b92c8454cba89'),(r/'sources/ltx-cutlass','afa1772203677c5118fcd82537a9c8fefbcc7008')]
for dest,rev in items:
 def git(*args):subprocess.run(['git','-C',str(dest),*args],check=True,env=env,timeout=1200)
 dest.mkdir(parents=True,exist_ok=True)
 if not (dest/'.git').exists():
  git('init');git('remote','add','origin','https://github.com/NVIDIA/cutlass.git')
 git('config','http.version','HTTP/1.1')
 git('sparse-checkout','init','--cone');git('sparse-checkout','set','include','tools/util/include')
 for attempt in range(4):
  try:
   git('fetch','--depth','1','--filter=blob:none','origin',rev);git('checkout','--detach',rev)
   print('READY',dest,rev,flush=True);break
  except Exception as e:
   print('retry',e,flush=True);time.sleep(5)
 else:raise RuntimeError('CUTLASS download failed')
