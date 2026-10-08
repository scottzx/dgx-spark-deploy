"""Official LatentSync 1.6, shared pipeline, original LTX video + Serena audio."""
import os
from pathlib import Path
import sys
import time
from bench_common import ROOT, MODELS, gpu_lock, jobs, link, cpu_onnx, trusted_torch_load, receipt

lock = gpu_lock()
source = ROOT/'sources/LatentSync'
os.chdir(source)
sys.path[:0] = [str(ROOT/'compat'), str(ROOT/'deps/common'), str(ROOT/'deps/latentsync'), str(source)]
import torch
from omegaconf import OmegaConf
from diffusers import AutoencoderKL, DDIMScheduler
from latentsync.models.unet import UNet3DConditionModel
from latentsync.pipelines.lipsync_pipeline import LipsyncPipeline
from latentsync.whisper.audio2feature import Audio2Feature
cpu_onnx()
trusted_torch_load()
link(MODELS/'latentsync', source/'checkpoints')
link(MODELS/'liveportrait/insightface/models/buffalo_l', source/'checkpoints/auxiliary/models/buffalo_l')
config = OmegaConf.load(source/'configs/unet/stage2_512.yaml')
dtype = torch.float16
started = time.perf_counter()
scheduler = DDIMScheduler.from_pretrained(source/'configs')
audio_encoder = Audio2Feature(model_path=str(MODELS/'latentsync/whisper/tiny.pt'), device='cuda',
                              num_frames=config.data.num_frames, audio_feat_length=config.data.audio_feat_length)
vae = AutoencoderKL.from_pretrained('/home/admin/models_cache/digital_human/musetalk/sd-vae', torch_dtype=dtype)
vae.config.scaling_factor = 0.18215
vae.config.shift_factor = 0
unet, _ = UNet3DConditionModel.from_pretrained(OmegaConf.to_container(config.model),
                                             str(MODELS/'latentsync/latentsync_unet.pt'), device='cpu')
pipeline = LipsyncPipeline(vae=vae, audio_encoder=audio_encoder, unet=unet.to(dtype), scheduler=scheduler).to('cuda')
torch.cuda.synchronize()
loaded = time.perf_counter()-started
print({'stage':'loaded','engine':'latentsync','seconds':loaded}, flush=True)
for job in jobs():
    case = Path(job['directory'])
    out = ROOT/'outputs/latentsync'/job['product']; out.mkdir(parents=True, exist_ok=True)
    torch.manual_seed(job['seed']); torch.cuda.reset_peak_memory_stats()
    started = time.perf_counter()
    native = out/'native.mp4'
    pipeline(video_path=str(case/'driver.mp4'), audio_path=str(case/'audio_16k.wav'), video_out_path=str(native),
             num_frames=config.data.num_frames, num_inference_steps=20, guidance_scale=1.5,
             weight_dtype=dtype, width=config.data.resolution, height=config.data.resolution,
             mask_image_path=config.data.mask_image_path, temp_dir=str(out/'temp'))
    receipt('latentsync', job, source, out, native, loaded, started,
            {'scope':'Official video-to-video lip synchronization. Pickup/return body actions come from the original LTX video.',
             'steps':20, 'guidance_scale':1.5, 'model_generates_product_actions':False,
             'original_LTX_actions_preserved':True,
             'compatibility':['OpenCV/FFmpeg CPU decord adapter', 'CPU ONNX face detection, four threads',
                              'Existing local sd-vae-ft-mse weights', 'Diffusers 0.32.2 in isolated dependency directory']})
