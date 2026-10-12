from pathlib import Path
import sys,json,subprocess,os
r=Path('/home/admin/sol-spark-runtime');p=Path('/home/admin/sol-h3-spark/models/minimax_h3/Sol-H3-Spark');sys.path.insert(0,str(p))
from runtime.pipeline import worker_environment
paths=json.loads((r/'component-paths.json').read_text())
env=worker_environment('stage1',paths)
env['CPATH']=str(r/'sysroot/usr/include/python3.12')+':'+str(r/'sysroot/usr/include')
env['CUDA_HOME']='/usr/local/cuda'
code="""import torch,importlib.metadata as m
from flash_attn.cute.interface import flash_attn_func
import cutlass
print('torch',torch.__version__,'cutlass',cutlass.__file__, 'tvm',m.version('apache-tvm-ffi'),flush=True)
torch.manual_seed(42)
q,k,v=[torch.randn(1,128,4,128,device='cuda',dtype=torch.bfloat16) for _ in range(3)]
out=flash_attn_func(q,k,v,causal=False)
if isinstance(out,tuple):out=out[0]
ref=torch.nn.functional.scaled_dot_product_attention(q.transpose(1,2),k.transpose(1,2),v.transpose(1,2)).transpose(1,2)
torch.cuda.synchronize()
torch.testing.assert_close(out,ref,atol=0.02,rtol=0.02)
print('FA4 BF16 GPU comparison PASS',float((out-ref).abs().max()),flush=True)
"""
subprocess.run([paths['stage1_python'],'-c',code],check=True,env=env)
