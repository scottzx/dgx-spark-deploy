#!/usr/bin/env python3
"""Build a review-bound candidate registry; never promote technical PASS alone."""
import hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parent
m=json.loads((ROOT/'manifest.json').read_text());q=json.loads((ROOT/'quality_review.json').read_text());by={x['id']:x for x in q['clips']}
rows=[];ready=[]
for job in m['shots']:
 path=ROOT/'clips'/job['id']/'result.json'
 if not path.exists():continue
 result=json.loads(path.read_text());review=by.get(job['id'],dict(quality_status='unreviewed',accepted_for_production=False))
 assert result['input_fingerprint']==job['input_fingerprint']
 output=ROOT/'clips'/job['id']/'delivered.mp4';actual=hashlib.sha256(output.read_bytes()).hexdigest();assert actual==result['media']['sha256']
 if job['id'] in by:
  assert review['input_fingerprint']==job['input_fingerprint'],'Review refers to different inputs'
  assert review['output_sha256']==actual,'Review refers to different output'
 if review.get('accepted_for_production'):
  assert review['quality_status']=='pass_at_samples' and not review.get('hard_violations') and not review.get('unmet_criteria')
  assert job['case_id']!='S16','Known invalid mechanical keyframes cannot be auto-approved'
  ready.append(job['id'])
 rows.append(dict(id=job['id'],case_id=job['case_id'],input_fingerprint=job['input_fingerprint'],output_sha256=actual,file=str(output.relative_to(ROOT)),technical_status=result['status'],quality=review,production_ready=job['id'] in ready))
intervals=q.get('editable_intervals',[])
for interval in intervals:
 assert interval['id'] in by
 assert not interval['status'].startswith('candidate_pending'),'Editorial interval has not been checked'
 assert 0<=interval['start_frame']<interval['end_frame_exclusive']<=120
 assert interval['duration_s']==(interval['end_frame_exclusive']-interval['start_frame'])/24
 interval['source_sha256']=next(x['output_sha256'] for x in rows if x['id']==interval['id'])
(ROOT/'candidate_registry.json').write_text(json.dumps(dict(manifest_fingerprint=m['fingerprint'],clips=rows,production_ready=ready,editable_intervals=intervals,scope='all creative decisions based on sampled frames; audio and between-sample final inspection pending'),ensure_ascii=False,indent=2)+'\n')
print(json.dumps(dict(registry=len(rows),production_ready=len(ready),editable_intervals=len(intervals))))
