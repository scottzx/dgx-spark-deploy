"""Collect completed receipts and refresh the comparison throughout the durable run."""
import argparse
import datetime
import json
from pathlib import Path
import shlex
import subprocess
import sys
import time

HERE=Path(__file__).resolve().parent
parser=argparse.ArgumentParser()
parser.add_argument('--root',type=Path,default=HERE.parents[2]/'docs/benchmarks/15_womenswear_avatar_comparison')
parser.add_argument('--remote-root',default='/home/admin/womenswear-avatar-tests')
args=parser.parse_args()
DEST=args.root.resolve()
REMOTE_ROOT=args.remote_root
REMOTE='''
import json,re,os
from pathlib import Path
r=Path('/home/admin/womenswear-avatar-tests')
s=json.loads((r/'queue_status.json').read_text())
stage=s.get('current_stage','')
p=r/'logs'/(stage+'.log')
lines=p.read_text(errors='replace').replace('\\r','\\n').splitlines() if p.exists() else []
step=[x for x in lines[-40:] if re.search(r'\\d+/\\d+.*it/s|\\d+/\\d+.*s/it',x)]
s['detail']=(step[-1].strip()[:170] if step else '')
s['log_tail']='\\n'.join(lines[-5:])[-1300:]
s['outputs']=sorted(str(p.parent.relative_to(r/'outputs')) for p in (r/'outputs').glob('*/*/metrics.json'))
s['ltx_outputs']=sorted(p.parent.name for p in (r/'ltx').glob('*/metrics.json'))
s['voice_ready']=(r/'voices/voice.json').exists()
s['inputs_ready']=(r/'inputs/manifest.json').exists()
try:os.kill(s['pid'],0)
except ProcessLookupError:
    if s['state']=='running':s['state']='failed';s['detail']='Queue process exited before completion'
print(json.dumps(s))
'''
REMOTE=REMOTE.replace("Path('/home/admin/womenswear-avatar-tests')",'Path('+repr(REMOTE_ROOT)+')')
DEST.mkdir(parents=True,exist_ok=True)
known={str(p.parent.relative_to(DEST/'results')) for p in (DEST/'results').glob('*/*/metrics.json')}
known_ltx={p.parent.name for p in (DEST/'ltx').glob('*/metrics.json')}
inputs_ready=(DEST/'inputs/manifest.json').exists()
voice_ready=(DEST/'voices/voice.json').exists()
def copy(path,destination,include=None):
    destination.mkdir(parents=True,exist_ok=True)
    cmd=['rsync','-a']
    if include:
        for name in include:cmd.append('--include='+name)
        cmd.append('--exclude=*')
    subprocess.run(cmd+['admin@100.115.178.96:'+REMOTE_ROOT+'/'+path+'/',str(destination)+'/'],check=True)
def build():subprocess.run([sys.executable,str(HERE/'build_review.py'),'--root',str(DEST)],check=True)
build()
while True:
    result=subprocess.run(['ssh','-o','BatchMode=yes','-o','ConnectTimeout=15','admin@100.115.178.96',
                           'python3 -c '+shlex.quote(REMOTE)],capture_output=True,text=True)
    if result.returncode:
        print('Status read temporarily unavailable: '+result.stderr.strip()[:160],flush=True)
        time.sleep(35);continue
    s=json.loads(result.stdout)
    s['collected_at_utc']=datetime.datetime.now(datetime.timezone.utc).isoformat()
    (DEST/'progress.json').write_text(json.dumps(s,ensure_ascii=False,indent=2)+'\n')
    changed=False
    if s['voice_ready'] and not voice_ready:
        copy('voices',DEST/'voices');voice_ready=True;changed=True
    if s['inputs_ready'] and not inputs_ready:
        copy('inputs',DEST/'inputs');inputs_ready=True;changed=True
    for key in set(s['ltx_outputs'])-known_ltx:
        copy('ltx/'+key,DEST/'ltx'/key,['motion.mp4','metrics.json']);known_ltx.add(key);changed=True
    for key in set(s['outputs'])-known:
        copy('outputs/'+key,DEST/'results'/key,['video.mp4','native.mp4','metrics.json']);known.add(key);changed=True
    if changed:build()
    print(json.dumps({'stage':s.get('current_stage'),'state':s['state'],'completed':len(known),
                      'ltx_actions':len(known_ltx),'detail':s.get('detail','')},ensure_ascii=False),flush=True)
    if s['state']=='failed':
        print(s['log_tail'],flush=True);raise SystemExit(1)
    if s['state']=='complete' and len(known)==9:
        copy('logs',DEST/'logs',['*.done.json','queue.log'])
        subprocess.run(['rsync','-a','admin@100.115.178.96:'+REMOTE_ROOT+'/runner_adaptations.json',
                         str(DEST/'runner_adaptations.json')],check=True)
        build();print('All nine portrait garment candidates collected and verified.',flush=True);break
    time.sleep(35)
