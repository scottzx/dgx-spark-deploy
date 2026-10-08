#!/usr/bin/env python3
"""Check GB10 compiled masked attention against a dense numerical reference."""
import json
from pathlib import Path
import time
import torch
import torch.nn.functional as F
from torch.nn.attention.flex_attention import create_block_mask,flex_attention

root=Path('/home/admin/wan-animate2-runtime');started=time.perf_counter()
torch.manual_seed(20261007)
q=torch.randn(1,4,256,128,device='cuda',dtype=torch.bfloat16)
k=torch.randn_like(q);v=torch.randn_like(q)
def valid(b,h,query,key):return (key<128)|(query//64==key//64)
def score_mod(score,b,h,query,key):return score+torch.where(key<128,-.5,0.)
mask=create_block_mask(valid,1,4,256,256,device='cuda')
compiled=torch.compile(flex_attention,fullgraph=True)
actual=compiled(q,k,v,block_mask=mask,score_mod=score_mod)
query=torch.arange(256,device='cuda')[:,None];key=torch.arange(256,device='cuda')[None,:]
bias=torch.where((key<128)|(query//64==key//64),torch.where(key<128,-.5,0.),float('-inf'))
expected=F.scaled_dot_product_attention(q,k,v,attn_mask=bias.to(q.dtype))
torch.cuda.synchronize()
error=(actual.float()-expected.float()).abs()
assert torch.allclose(actual,expected,atol=.025,rtol=.05)
receipt={'gpu':torch.cuda.get_device_name(),'capability':list(torch.cuda.get_device_capability()),
         'torch':torch.__version__,'compiled_flex_attention_passed':True,
         'max_absolute_error':float(error.max()),'mean_absolute_error':float(error.mean()),
         'elapsed_seconds':time.perf_counter()-started,
         'scope':'Kernel compatibility and small masked-attention numerical comparison; full-model inference tested separately.'}
(root/'attention_preflight.json').write_text(json.dumps(receipt,indent=2)+'\n')
print(json.dumps(receipt),flush=True)
