"""Exercise the official portrait preprocessing on CPU before GPU inference."""
import json
import os
from pathlib import Path
import sys

os.environ['CUDA_VISIBLE_DEVICES'] = ''
from bench_common import ROOT, MODELS, jobs, cpu_onnx, link, sha

source = ROOT/'sources/JoyHallo-src'
os.chdir(source)
sys.path[:0] = [str(ROOT/'compat'), str(ROOT/'deps/common'), str(source)]
import torch
import numpy as np
from PIL import Image
from joyhallo.datasets.image_processor import ImageProcessor

torch.set_num_threads(4)
cpu_onnx()
link(MODELS/'hallo_base/face_analysis', source/'pretrained_models/face_analysis')
processor = ImageProcessor((512,512), str(MODELS/'hallo_base/face_analysis'))
records = []
for job in jobs():
    image = Image.open(Path(job['directory'])/'first_frame.png').convert('RGB')
    faces = processor.face_analysis.get(np.asarray(image)[:,:,::-1].copy())
    if not faces:
        raise RuntimeError('No face in shared '+job['product']+' input')
    face = max(faces, key=lambda f:(f.bbox[2]-f.bbox[0])*(f.bbox[3]-f.bbox[1]))
    x1,y1,x2,y2 = map(float,face.bbox)
    side = max(x2-x1,y2-y1)/0.55
    cx,cy = (x1+x2)/2,(y1+y2)/2
    left = max(0,min(image.width-side,cx-side/2))
    top = max(0,min(image.height-side,cy-side/2))
    crop = tuple(round(v) for v in (left,top,left+side,top+side))
    out = ROOT/'preflight/joyhallo'/job['product']
    out.mkdir(parents=True, exist_ok=True)
    (out/'cache').mkdir(exist_ok=True)
    portrait = out/'portrait_reference.png'
    image.crop(crop).resize((512,512)).save(portrait)
    pixels, region, embedding, full, face_masks, lips = processor.preprocess(str(portrait),str(out/'cache'),1.2)
    masks = full+face_masks+lips
    if not all(torch.isfinite(m).all() for m in masks):
        raise RuntimeError('Nonfinite portrait mask')
    records.append({'product':job['product'],'crop':crop,'portrait_sha256':sha(portrait),
                    'pixel_shape':list(pixels.shape),'face_region_shape':list(region.shape),
                    'embedding_shape':list(embedding.shape),'embedding_norm':float(np.linalg.norm(embedding)),
                    'mask_shapes':[list(m.shape) for m in masks],
                    'mask_ranges':[[float(m.min()),float(m.max())] for m in masks],
                    'cuda_initialized':torch.cuda.is_initialized()})
    print('Official CPU portrait preprocessing passed: '+job['product'],flush=True)
processor.close()
(ROOT/'preflight_joyhallo_image.json').write_text(json.dumps(records,indent=2)+'\n')
