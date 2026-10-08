#!/usr/bin/env python3
"""Run three installed local avatar routes on three shared handheld SKU inputs."""
import json
import os
from pathlib import Path
import subprocess
import time

root=Path('/home/admin/digital-human-runtime')
inputs=root/'inputs/handheld'
env=dict(os.environ,PYTHONUNBUFFERED='1',PATH='/home/admin/.local/bin:'+os.environ['PATH'],
         CPATH='/home/admin/sol-spark-runtime/sysroot/usr/include/python3.12:/home/admin/sol-spark-runtime/sysroot/usr/include')
py=str(root/'avatar-env/bin/python')
products=['original','diet','zero']
prompt=('A professional woman in a red blouse speaks naturally to the camera while physically holding one beverage can in both hands. '
        'She gently lifts the can a few centimeters to present it and then holds it steady, with subtle head movement and a small friendly expression. '
        'Her fingers stay wrapped around the same can, one palm supports its base, label faces camera. '
        'Preserve the reference can colors, shape, lettering, her facial identity, and realistic hand-object contact. Locked camera, no cuts, no extra products.')
negative=('distorted face, distorted hands, extra fingers, hand passing through can, floating can, duplicate can, '
          'can disappearing, changing can shape, changing label, blurred logo, exaggerated arm gestures, fast rotation, camera movement')
records=[]
for route,script in [('A','run_musetalk.py'),('B','run_flashhead.py'),('C','run_echomimic.py')]:
    for product in products:
        label=f'handheld_{route}_{product}'
        out=root/'outputs'/label
        if (out/'metrics.json').exists() and (out/'raw.mp4').exists():
            print(f'preserving completed {label}',flush=True);continue
        args=[py,str(root/script),'--image',str(inputs/f'{product}.png'),'--audio',str(inputs/f'{product}_16k.wav'),'--label',label]
        args+=['--original-audio',str(inputs/f'{product}.wav')]
        if route=='C':args+=['--frames-per-shot','97','--prompt',prompt,'--negative-prompt',negative]
        t0=time.perf_counter()
        print(f'start {label}',flush=True)
        log=root/'logs'/f'{label}.log'
        with log.open('w') as stream:
            result=subprocess.run(args,env=env,stdout=stream,stderr=subprocess.STDOUT)
        record={'route':route,'product':product,'label':label,'exit_code':result.returncode,'wall_seconds':time.perf_counter()-t0,'command':args,'log':str(log)}
        records.append(record)
        (root/'outputs/handheld_progress.json').write_text(json.dumps(records,ensure_ascii=False,indent=2)+'\n')
        print(json.dumps(record,ensure_ascii=False),flush=True)
        if result.returncode:
            print(log.read_text()[-4000:],flush=True)
            raise SystemExit(result.returncode)
(root/'outputs/handheld_suite.json').write_text(json.dumps({'prompt_C':prompt,'negative_prompt_C':negative,'runs':records},ensure_ascii=False,indent=2)+'\n')
