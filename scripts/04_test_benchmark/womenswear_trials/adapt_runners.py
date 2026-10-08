"""Copy proven official runners into this isolated test with exact portrait dimensions."""
import argparse
import json
from pathlib import Path
import shutil

parser=argparse.ArgumentParser()
parser.add_argument('--source',type=Path,default=Path('/home/admin/avatar-company-tests'))
parser.add_argument('--destination',type=Path,default=Path('/home/admin/womenswear-avatar-tests'))
args=parser.parse_args()
args.destination.mkdir(parents=True,exist_ok=True)
common=(args.source/'bench_common.py').read_text()
common=common.replace("ROOT = Path('/home/admin/avatar-company-tests')",
                      "ROOT = Path(os.environ.get('AVATAR_BENCH_ROOT', '/home/admin/avatar-company-tests'))")
(args.destination/'bench_common.py').write_text(common)
shutil.copy2(args.source/'flash_sdpa.py',args.destination/'flash_sdpa.py')
for name in ['run_infinitetalk.py','run_longcat.py','run_latentsync.py']:
    source=(args.source/name).read_text()
    needle="out.mkdir(parents=True, exist_ok=True)\n"
    addition="    if (out/'metrics.json').exists() and (out/'video.mp4').exists():\n        continue\n"
    if addition not in source:
        assert source.count(needle)==1,name
        source=source.replace(needle,needle+addition)
    if name=='run_infinitetalk.py':
        source=source.replace('import generate_infinitetalk as demo\n',
             'import generate_infinitetalk as demo\n'
             'from wan.utils import multitalk_utils\n'
             '# Exact 3:4 bucket prevents a silent crop to a nearby aspect ratio.\n'
             "multitalk_utils.ASPECT_RATIO_627[str(4/3)] = ([768,576],1)\n")
        source=source.replace("'steps_per_chunk':8, 'motion_frame':9,", 
                              "'steps_per_chunk':8, 'motion_frame':9, 'requested_size':[576,768], 'aspect_ratio':'3:4',")
    elif name=='run_longcat.py':
        source=source.replace("disappearing products, floating products'",
                              "duplicated garments, materializing clothes, floating clothes, fabric fused with skin'")
        source=source.replace('torch.cuda.synchronize(); loaded = time.perf_counter()-started\n',
             '# Same supported spatial multiples as official bucketing, exact 3:4.\n'
             'pipe.get_condition_shape = lambda condition, resolution, scale_factor_spatial=32: (768,576)\n'
             'torch.cuda.synchronize(); loaded = time.perf_counter()-started\n')
        source=source.replace("'steps_per_chunk':8, 'chunks':3,", 
                              "'steps_per_chunk':8, 'chunks':3, 'requested_size':[576,768], 'aspect_ratio':'3:4',")
    (args.destination/name).write_text(source)
(args.destination/'runner_adaptations.json').write_text(json.dumps({
    'source':str(args.source),'destination':str(args.destination),'aspect_ratio':'3:4',
    'native_target_size':[576,768],
    'changes':['Isolated benchmark root, shared existing model weights and dependencies',
               'Completed cases skipped on repair/resume',
               'InfiniteTalk exact 3:4 bucket; LongCat exact 3:4 condition shape',
               'Candidate model results preserved; no manual garment repair, post-crop or reverse playback. Official LatentSync face masking retained.'],
    'route_constraints':{'ltx':'six image keyframe conditions',
                         'infinitetalk':'original streaming LTX sparse references at frames0/72/144',
                         'longcat':'LTX first frame plus same full timed text prompt and Serena audio',
                         'latentsync':'complete LTX motion plus same Serena audio'}
},ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'portrait_runners_ready':True,'size':[576,768]}),flush=True)
