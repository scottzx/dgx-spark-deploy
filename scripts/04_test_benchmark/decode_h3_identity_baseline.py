#!/usr/bin/env python3
"""Decode identical captured H3 latents with the native full VAE for drift diagnosis."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import time

sys.path[:0] = ['/home/admin/sol-spark-runtime/sources/FastVideo',
    '/home/admin/sol-h3-spark/models/minimax_h3/Sol-H3-Spark']


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--captures',type=Path,nargs='+',required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    import numpy as np
    import torch
    from safetensors.torch import load_file
    from fastvideo.configs.models.vaes.minimax_h3_video import MiniMaxH3VideoVAEConfig
    from fastvideo.models.vaes.minimax_h3_video import AutoencoderKLMiniMaxH3
    from runtime.duration_profiles import get_profile
    from draft_preview import _write_wav
    root=Path('/home/admin/sol-spark-runtime/checkpoints/MiniMax-H3/vae')
    config=MiniMaxH3VideoVAEConfig()
    config.update_model_arch(json.loads((root/'config.json').read_text()))
    started=time.monotonic()
    vae=AutoencoderKLMiniMaxH3(config).eval().requires_grad_(False)
    weights={}
    for shard in sorted(root.glob('*.safetensors')):
        weights.update(load_file(shard))
    vae.load_state_dict(weights,strict=True)
    del weights
    vae.to('cuda')
    args.output.mkdir(parents=True,exist_ok=True)
    receipts=[]
    for capture in args.captures:
        record=json.loads((capture/'capture.json').read_text())
        payload=torch.load(capture/'stage1_direct_tensors.pt',map_location='cpu',weights_only=True)
        latent=payload['h3_normalized'].to('cuda',dtype=torch.float32)
        trim=int(record.get('continuation',{}).get('trim_frames',0))
        profile=get_profile(record['duration_s'])
        pixels=torch.empty(vae.decoded_pixel_shape(latent.shape),dtype=torch.float32,device='cpu')
        t0=time.monotonic()
        with torch.inference_mode(),torch.autocast('cuda',dtype=torch.float16):
            vae.decode_to_pixels(vae.denormalize_latents(latent),pixels)
        torch.cuda.synchronize()
        delivered=pixels[0,:,trim:profile['emit_frames']].clamp(0,1)
        frames,h,w=delivered.shape[1:]
        directory=args.output/record['case_id']
        directory.mkdir(parents=True,exist_ok=True)
        raw=directory/'native.rgb'
        raw.write_bytes((delivered.permute(1,2,3,0).numpy()*255).astype(np.uint8).tobytes())
        wav=directory/'native.wav'
        audio=payload['audio'][:,:,round(trim/24*32000):round(profile['emit_frames']/24*32000)]
        _write_wav(wav,audio)
        output=directory/'h3_native.mp4'
        subprocess.run(['/home/admin/.local/bin/ffmpeg','-y','-v','error','-f','rawvideo','-pix_fmt','rgb24',
            '-s',f'{w}x{h}','-r','24','-i',str(raw),'-i',str(wav),'-frames:v',str(frames),
            '-c:v','libx264','-crf','18','-pix_fmt','yuv420p','-c:a','aac','-ar','32000','-ac','2',str(output)],check=True)
        raw.unlink()
        wav.unlink()
        receipts.append(dict(status='PASS',capture_dir=str(capture),output=str(output),frames=frames,
            height=h,width=w,decoder='native_full_H3_VAE',decode_s=time.monotonic()-t0,
            latent_precision='same BF16 handoff as LTX',trim_frames=trim))
        print(json.dumps(receipts[-1]),flush=True)
        del pixels,delivered,latent,payload
    result=dict(status='PASS',elapsed_s=time.monotonic()-started,clips=receipts)
    (args.output/'native_decode.json').write_text(json.dumps(result,indent=2)+'\n')


if __name__=='__main__': main()
