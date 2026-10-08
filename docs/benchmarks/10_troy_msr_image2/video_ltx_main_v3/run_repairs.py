#!/usr/bin/env python3
"""Run the two LTX replacement shots without changing the frozen base batch."""
import argparse,json
from pathlib import Path
import run_offline as engine
ROOT=Path(__file__).resolve().parent/'repairs'
def main():
    p=argparse.ArgumentParser();p.add_argument('--phase',choices=['caches','ltx'],required=True);a=p.parse_args()
    m=json.loads((ROOT/'manifest.json').read_text());assert m['remote_root']==str(ROOT) and len(m['jobs'])==2
    for j in m['jobs']:
        assert engine.sha(ROOT/j['first_frame'])==j['first_frame_sha256']
        assert engine.hashlib.sha256(j['prompt'].encode()).hexdigest()==j['prompt_sha256']
    engine.ROOT=ROOT
    original=engine.emit
    def emit(**x):
        if 'total' in x:x['total']=2
        original(**x)
    engine.emit=emit
    {'caches':engine.caches,'ltx':engine.ltx}[a.phase](m)
if __name__=='__main__':main()
