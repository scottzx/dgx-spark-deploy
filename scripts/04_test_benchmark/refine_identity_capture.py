#!/usr/bin/env python3
"""Refine the identical old H3 latent with an identity-specific text context."""
import json
from pathlib import Path
import sys
sys.path.insert(0,'/home/admin/sol-h3-spark/models/minimax_h3/Sol-H3-Spark')
from runtime.stage2 import Session
root=Path('/home/admin/sol-spark-runtime/identity_tests_20261003')
paths=json.loads(Path('/home/admin/sol-spark-runtime/paths.json').read_text())
paths['prompt_cache']=str(root/'prompt_caches/specific_refiner.pt')
prompt=json.loads((root/'ltx_prompts.json').read_text())['specific_refiner']
capture=Path('/home/admin/sol-spark-runtime/outputs/api_server_runs/session_20261003-215619_fl2va/troy_20261003_220446_opening/stage1')
record=json.loads((capture/'capture.json').read_text())
out=root/'specific_refiner';out.mkdir(exist_ok=True)
session=Session(paths,str(out),dict(compile=False,fixed_prompt=prompt))
try:
 for name,sigmas in [('delivery',(0.909375,0.725,0.421875,0.)),
                     ('low_noise',(0.421875,0.3,0.15,0.))]:
  session.models.stage2_sigmas=sigmas
  session.models.sigmas=session.torch.tensor(sigmas,device=session.models.device,dtype=session.torch.float32)
  delivered=out/name
  session.prepare(record['request_id'],str(delivered))
  result=session.run(str(capture),str(delivered),record['request_id'])
  result['benchmark_recipe']=dict(sigmas=list(sigmas),updates=3,identity_specific_prompt=True,
   experimental_intermediate_sigmas=name=='low_noise')
  (out/(name+'_result.json')).write_text(json.dumps(result,indent=2))
  print(json.dumps(dict(status='PASS',variant=name,output=result['output'],elapsed_s=result['stage2_request_s'])),flush=True)
finally:session.close()
