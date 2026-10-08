"""Follow the current Spark batch and refresh the review on completed receipts."""
import json
import datetime
from pathlib import Path
import shlex
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parents[2]
DEST = PROJECT/'docs/benchmarks/14_company_avatar_comparison/results'
PRIMARY = {'joyhallo','joyvasa','infinitetalk','longcat','liveportrait','latentsync','avatarforever'}
REMOTE = '''
import json
import os
import re
from pathlib import Path
root=Path('/home/admin/avatar-company-tests')
live=set()
for proc in Path('/proc').iterdir():
    if not proc.name.isdigit(): continue
    try:
        cwd=os.readlink(proc/'cwd')
        if not (cwd==str(root) or cwd.startswith(str(root)+'/')): continue
        args=(proc/'cmdline').read_bytes().decode(errors='replace').split('\\0')
    except (OSError,PermissionError): continue
    for name in ['longcat','infinitetalk','joyhallo','avatarforever']:
        if 'run_'+name+'.py' in args: live.add(name)
    if 'run_portrait_models.py' in args and 'joyvasa' in args: live.add('joyvasa')
logs={}
for name in ['longcat','infinitetalk','joyhallo','avatarforever','joyvasa']:
    path=root/'logs'/('run_'+name+'.log')
    value=path.read_text(errors='replace') if path.exists() else ''
    lines=value.replace('\\r','\\n').splitlines()
    logs[name]={'last':lines[-1] if lines else 'Waiting for GPU',
                'alive':name in live,'started':path.exists(),'empty':not value.strip(),
                'failed':any(l.startswith('Traceback (most recent call last):') or
                             l.startswith('[rank0]: Traceback (most recent call last):') for l in lines)}
    if name=='joyhallo':
        chunks=re.findall(r"'chunk': (\\d+)",value)
        if chunks: logs[name].update(current_chunk=int(chunks[-1]),total_chunks=13)
print(json.dumps({'completed':sorted(str(p.relative_to(root/'outputs')) for p in (root/'outputs').glob('*/*/metrics.json')),'logs':logs}))
'''
previous_done = set(str(p.relative_to(DEST)) for p in DEST.glob('*/*/metrics.json') if p.parent.parent.name in PRIMARY)
previous_logs = {}
while True:
    result = subprocess.run(['ssh','-o','ConnectTimeout=15','admin@100.115.178.96',
                             'python3 -c '+shlex.quote(REMOTE)],capture_output=True,text=True)
    if result.returncode:
        print('Status read failed:',result.stderr.strip(),flush=True)
        time.sleep(45)
        continue
    status=json.loads(result.stdout)
    done={p for p in status['completed'] if p.split('/')[0] in PRIMARY}
    progress={}
    for name in ['joyhallo','joyvasa','infinitetalk','longcat','liveportrait','latentsync','avatarforever']:
        count=sum(p.startswith(name+'/') for p in done)
        details=status['logs'].get(name,{})
        dead=details.get('started') and not details.get('alive') and count<3
        state=('complete' if count==3 else 'failed' if details.get('failed') or dead else
               'queued' if details.get('empty',True) else 'running')
        progress[name]={'completed':count,'state':state,'last':details.get('last','')}
        for key in ['current_chunk','total_chunks']:
            if key in details: progress[name][key]=details[key]
    (DEST.parent/'progress.json').write_text(json.dumps({'updated_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
                                                        'completed_cases':len(done),'total_cases':21,'models':progress},ensure_ascii=False,indent=2)+'\n')
    if done != previous_done:
        subprocess.run(['ssh','admin@100.115.178.96',
                        '/home/admin/digital-human-runtime/avatar-env/bin/python /home/admin/avatar-company-tests/normalize_tails.py'],check=True)
        subprocess.run(['rsync','-a','--include=/*/','--include=/*/*/',
                        '--include=/*/*/video.mp4','--include=/*/*/metrics.json','--include=/*/*/original_mux_receipt.json','--exclude=*',
                        'admin@100.115.178.96:/home/admin/avatar-company-tests/outputs/',str(DEST)+'/'],check=True)
        for script in ['inspect_boundaries.py','build_review.py','verify_audio.py','build_report.py']:
            subprocess.run([sys.executable,str(HERE/script)],check=True)
        print('New results:',', '.join(sorted(done-previous_done)),flush=True)
        previous_done=done
    for name,details in status['logs'].items():
        if details['last'] != previous_logs.get(name):
            value=details['last']
            if value.startswith('{'):
                # Full measured receipts are retained in per-case files.
                value=value[:300]
            print(name+': '+value,flush=True)
            previous_logs[name]=details['last']
    if any(s['state']=='failed' for s in progress.values()):
        print('A runner needs repair; review refreshed without substituting its output.',flush=True)
        sys.exit(1)
    if len(done)==21:
        print('All 21 cases completed.',flush=True)
        break
    time.sleep(45)
