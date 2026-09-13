from pathlib import Path
import subprocess,os,time
r=Path('/home/admin/sol-spark-runtime')
for i in range(240):
 if 'RUNTIME_DEPENDENCIES_INSTALLED' in (r/'runtime-install.log').read_text() and 'READY '+str(r/'sources/ltx-cutlass') in (r/'cutlass-source.log').read_text():break
 time.sleep(30)
else:raise RuntimeError('Build prerequisites not ready in 2 hours')
env=os.environ.copy();env.update(CUDA_HOME='/usr/local/cuda',CUDACXX='/usr/local/cuda/bin/nvcc',TORCH_CUDA_ARCH_LIST='12.1',MAX_JOBS='4',CMAKE_BUILD_PARALLEL_LEVEL='4',UV_LOCK_TIMEOUT='3600')
for stage,source in [('stage1',r/'sources/FastVideo/fastvideo-kernel'),('stage2',r/'sources/LTX-2/packages/ltx-kernels')]:
 env['CPATH']=str(r/'sysroot/usr/include/python3.12')+':'+str(r/'sysroot/usr/include')
 env['PATH']=str(r/(stage+'-env/bin'))+':/usr/local/cuda/bin:'+os.environ['PATH']
 if stage=='stage1':
  env['CMAKE_ARGS']='-DPython_INCLUDE_DIR=/home/admin/sol-spark-runtime/sysroot/usr/include/python3.12 -DPython_EXECUTABLE=/home/admin/sol-spark-runtime/stage1-env/bin/python -DFASTVIDEO_KERNEL_BUILD_TK=OFF -DFASTVIDEO_KERNEL_BUILD_ATTN_QAT_INFER=OFF -DFASTVIDEO_KERNEL_BUILD_ULYSSES_A2A=OFF'
 else:
  env.pop('CMAKE_ARGS',None);env['CUTLASS_DIR']=str(r/'sources/ltx-cutlass')
 print('BUILD',stage,source,flush=True)
 subprocess.run(['/home/admin/.local/bin/uv','pip','install','--python',str(r/(stage+'-env/bin/python')),'--no-deps','--no-build-isolation','--verbose',str(source)],check=True,env=env)
 print('BUILT',stage,flush=True)
print('KERNELS_BUILT',flush=True)
