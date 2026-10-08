#!/usr/bin/env python3
"""Fetch pinned manifests in resumable ranges and verify actual model hashes."""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
from pathlib import Path
import shutil
import time
from urllib.parse import quote
from urllib.request import Request, urlopen

def digest(p):
    h = hashlib.sha256()
    with p.open('rb') as f:
        while b := f.read(8*1024*1024): h.update(b)
    return h.hexdigest()

parser = argparse.ArgumentParser()
parser.add_argument('--manifest', type=Path, required=True)
parser.add_argument('--root', type=Path, required=True)
parser.add_argument('--workers', type=int, default=12)
args = parser.parse_args()
rows = json.loads(args.manifest.read_text())
chunk = 32*1024*1024
jobs, pending = [], {}
for i, r in enumerate(rows):
    target = args.root/r['target']
    assert target.resolve().is_relative_to(args.root.resolve())
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() and target.stat().st_size == r['size'] and (not r['sha256'] or digest(target)==r['sha256']):
        print('REUSE',r['target'],flush=True); continue
    if r.get('provider') == 'modelscope':
        url = f"https://modelscope.cn/models/{r['repo']}/resolve/{r['revision']}/{quote(r['name'])}"
    else:
        url = f"https://huggingface.co/{r['repo']}/resolve/{r['revision']}/{quote(r['name'])}"
    parts = args.root/'.parts'/r['target']
    parts.mkdir(parents=True, exist_ok=True)
    count = (r['size']+chunk-1)//chunk
    pending[i] = dict(row=r,target=target,parts=parts,left=count)
    for start in range(0,r['size'],chunk):
        jobs.append((i,url,start,min(start+chunk,r['size'])-1,r['size'],parts/str(start)))

def fetch(job):
    i,url,start,end,total,path=job
    expected=end-start+1
    if path.exists() and path.stat().st_size==expected:return i,expected
    tmp=path.with_suffix('.partial')
    for attempt in range(5):
        try:
            offset=tmp.stat().st_size if tmp.exists() else 0
            while offset<expected:
                first=start+offset;last=min(first+8*1024*1024-1,end)
                req=Request(url,headers={'Range':f'bytes={first}-{last}','User-Agent':'avatar-local-benchmark/1.0'})
                with urlopen(req,timeout=60) as resp:
                    cr=resp.headers.get('Content-Range')
                    if cr and cr != f'bytes {first}-{last}/{total}':raise ValueError(f'bad range {cr}')
                    if not cr and (first!=0 or last+1!=total):raise ValueError('Range unsupported')
                    with tmp.open('ab') as f:shutil.copyfileobj(resp,f,1024*1024)
                offset=tmp.stat().st_size
                if offset!=last-start+1:raise ValueError('Incomplete transfer')
            assert offset==expected
            tmp.replace(path);return i,expected
        except Exception as e:
            print('RETRY',attempt+1,url,str(e),flush=True)
            if attempt==4:raise
            time.sleep(min(2**attempt,8))

started=time.monotonic();received=0;receipts=[]
with ThreadPoolExecutor(args.workers) as pool:
    futures=[pool.submit(fetch,j) for j in jobs]
    for j,f in enumerate(as_completed(futures),1):
        i,n=f.result();received+=n;state=pending[i];state['left']-=1
        if state['left']==0:
            target=state['target'];tmp=target.with_suffix(target.suffix+'.assembling');r=state['row']
            with tmp.open('wb') as out:
                for start in range(0,r['size'],chunk):
                    with (state['parts']/str(start)).open('rb') as part:shutil.copyfileobj(part,out,8*1024*1024)
            h=digest(tmp)
            assert tmp.stat().st_size==r['size']
            if r['sha256']:assert h==r['sha256'],target
            tmp.replace(target);shutil.rmtree(state['parts'])
            receipts.append({'target':r['target'],'sha256':h,'size':r['size'],'repo':r['repo'],'revision':r['revision']})
            print('VERIFIED',r['target'],h,flush=True)
        if j%8==0 or j==len(futures):print(f'PROGRESS {j}/{len(jobs)} {received/1e9:.2f} GB {received/1e6/(time.monotonic()-started):.1f} MB/s',flush=True)
(args.root/('download-receipt-'+args.manifest.stem+'.json')).write_text(json.dumps(receipts,indent=2)+'\n')
print('COMPLETE',len(receipts),'new verified files',flush=True)
