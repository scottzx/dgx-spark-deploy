import os,subprocess
from pathlib import Path
r=Path('/home/admin/sol-spark-runtime');p=Path('/home/admin/sol-h3-spark/models/minimax_h3/Sol-H3-Spark')
env=os.environ.copy();env['UV_LOCK_TIMEOUT']='3600';env['UV_HTTP_TIMEOUT']='120'
for name,req in [('fa4','fa4-isolated.txt'),('offline-context','offline-context.txt')]:
 subprocess.run(['/home/admin/.local/bin/uv','pip','install','--python',str(r/'bootstrap-env/bin/python'),'--index-url','https://mirrors.aliyun.com/pypi/simple','--no-deps','--target',str(r/'dependencies'/name),'-r',str(r/'fa4-installable.txt') if name=='fa4' else str(p/'requirements'/req)],check=True,env=env)
print('ISOLATED_TARGETS_INSTALLED',flush=True)
