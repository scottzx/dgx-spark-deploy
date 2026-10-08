#!/usr/bin/env python3
"""Capture six native H3 trials through the already running local FL2VA service."""
import hashlib,json,time,urllib.request
from pathlib import Path
ROOT=Path(__file__).resolve().parent
def save(p,x):
 p.parent.mkdir(parents=True,exist_ok=True);t=p.with_suffix('.partial.json');t.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n');t.replace(p)
def api(path,payload=None,timeout=1800):
 req=urllib.request.Request('http://127.0.0.1:8090'+path,data=json.dumps(payload).encode() if payload is not None else None,headers={'Content-Type':'application/json'})
 with urllib.request.urlopen(req,timeout=timeout) as r:return json.load(r)
def main():
 m=json.loads((ROOT/'manifest.json').read_text());assert str(ROOT)==m['remote_root']
 before=api('/health',timeout=5);assert before['status']=='READY' and before['task']=='fl2va',before
 save(ROOT/'h3_service_before.json',before);rows=[]
 for j in [x for x in m['jobs'] if x['model']=='h3']:
  d=ROOT/'clips'/j['id'];result=d/'capture_response.json'
  if result.exists():
   row=json.loads(result.read_text());assert row['input_fingerprint']==j['input_fingerprint'];assert Path(row['capture_dir']).is_dir();rows.append(row);continue
  p=dict(case_id=j['id'],seed=j['seed'],duration_s=5,mode='draft',transition='independent',first_frame=str(ROOT/j['first_frame']),prompt=j['prompt'])
  save(d/'request.json',p);save(ROOT/'progress.json',dict(status='H3_GENERATING',job=j['id'],completed=len(rows),total=6))
  print(json.dumps(dict(status='H3_GENERATING',job=j['id'],completed=len(rows))),flush=True)
  t=time.monotonic();row=api('/api/generate',p);assert row['status']=='PASS' and row['mode']=='draft' and row['stage2_s']==0,row
  row.update(input_fingerprint=j['input_fingerprint'],manifest_fingerprint=m['fingerprint'],client_wall_s=time.monotonic()-t)
  capture=Path(row['capture_dir']);record=json.loads((capture/'capture.json').read_text())
  assert record['case_id']==j['id'] and record['prompt']==j['prompt'] and record['seed']==j['seed'],record
  save(d/'capture.json',record);save(result,row);rows.append(row)
  save(ROOT/'h3_capture_results.json',dict(status='RUNNING',clips=rows));print(json.dumps(dict(status='H3_CAPTURED',job=j['id'],wall_s=row['client_wall_s'])),flush=True)
 save(ROOT/'h3_capture_results.json',dict(status='PASS',clips=rows));save(ROOT/'progress.json',dict(status='H3_CAPTURES_COMPLETE',completed=len(rows),total=6))
if __name__=='__main__':main()
