"""Official LongCat-Video-Avatar 1.5, three independent product action cases."""
import datetime
import os
from pathlib import Path
import sys
import time
from bench_common import ROOT, MODELS, gpu_lock, jobs, receipt, save_frames

lock = gpu_lock()
source = ROOT/'sources/LongCat-Video'; os.chdir(source)
sys.path[:0] = [str(ROOT/'compat'), str(ROOT/'deps/common'), str(source)]
import torch
import torch.distributed as dist
import numpy as np
import soundfile as sf
from PIL import Image
from flash_sdpa import install
install()
from transformers import AutoTokenizer, UMT5EncoderModel
from longcat_video.pipeline_longcat_video_avatar import LongCatVideoAvatarPipeline
from longcat_video.modules.scheduling_flow_match_euler_discrete import FlowMatchEulerDiscreteScheduler
from longcat_video.modules.autoencoder_kl_wan import AutoencoderKLWan
from longcat_video.modules.avatar.longcat_video_dit_avatar import LongCatVideoAvatarTransformer3DModel
from longcat_video.context_parallel import context_parallel_util
from longcat_video.audio_process import get_audio_encoder, get_audio_feature_extractor

torch.cuda.set_device(0)
dist.init_process_group('nccl', init_method='tcp://127.0.0.1:29587', rank=0, world_size=1,
                        timeout=datetime.timedelta(hours=4))
context_parallel_util.init_context_parallel(context_parallel_size=1, global_rank=0, world_size=1)
checkpoint = MODELS/'longcat'
foundation = MODELS/'longcat_base'
started = time.perf_counter()
tokenizer = AutoTokenizer.from_pretrained(foundation, subfolder='tokenizer')
text_encoder = UMT5EncoderModel.from_pretrained(foundation, subfolder='text_encoder', torch_dtype=torch.bfloat16)
vae = AutoencoderKLWan.from_pretrained(foundation, subfolder='vae', torch_dtype=torch.bfloat16)
scheduler = FlowMatchEulerDiscreteScheduler.from_pretrained(checkpoint, subfolder='scheduler')
dit = LongCatVideoAvatarTransformer3DModel.from_pretrained(checkpoint, subfolder='base_model',
                                                         cp_split_hw=[1,1], torch_dtype=torch.bfloat16)
dit.load_lora(str(checkpoint/'lora/dmd_lora.safetensors'), 'dmd', multiplier=1.0,
              lora_network_dim=128, lora_network_alpha=64)
dit.enable_loras(['dmd'])
audio_encoder = get_audio_encoder(str(checkpoint/'whisper-large-v3'), 'avatar-v1.5').to('cuda')
audio_feature_extractor = get_audio_feature_extractor(str(checkpoint/'whisper-large-v3'), 'avatar-v1.5')
pipe = LongCatVideoAvatarPipeline(tokenizer=tokenizer, text_encoder=text_encoder, vae=vae,
                                 scheduler=scheduler, dit=dit, audio_encoder=audio_encoder,
                                 audio_feature_extractor=audio_feature_extractor, model_type='avatar-v1.5').to('cuda')
torch.cuda.synchronize(); loaded = time.perf_counter()-started
print({'stage':'loaded','engine':'longcat','seconds':loaded}, flush=True)
negative = 'close-up, static image, subtitles, blurred details, extra fingers, deformed hands, fused fingers, disfigured face, disappearing products, floating products'
for job in jobs():
    case = Path(job['directory']); out = ROOT/'outputs/longcat'/job['product']; out.mkdir(parents=True, exist_ok=True)
    generator = torch.Generator(device='cuda').manual_seed(job['seed'])
    torch.cuda.reset_peak_memory_stats(); started = time.perf_counter()
    speech, sr = sf.read(case/'audio_16k.wav', dtype='float32')
    assert sr == 16000 and speech.ndim == 1
    speech = np.pad(speech, (0, max(0, round(253/25*sr)-len(speech))))
    # Input is isolated synthesized speech; no music/vocal separation is needed.
    full_audio_emb = pipe.get_audio_embedding(speech, fps=25, device=0, sample_rate=sr, model_type='avatar-v1.5')
    if not torch.isfinite(full_audio_emb).all(): raise RuntimeError('Nonfinite audio embedding')
    offsets = torch.arange(5)-2
    def audio_chunk(start):
        idx = torch.clamp(torch.arange(start,start+93)[:,None]+offsets[None], 0, full_audio_emb.shape[0]-1)
        return full_audio_emb[idx][None].to('cuda')
    with torch.inference_mode():
        output, latent = pipe.generate_ai2v(image=Image.open(case/'first_frame.png').convert('RGB'),
                                            prompt=job['prompt'], negative_prompt=negative, resolution='480p',
                                            num_frames=93, num_inference_steps=8, text_guidance_scale=1.0,
                                            audio_guidance_scale=1.0, output_type='both', generator=generator,
                                            audio_emb=audio_chunk(0), use_distill=True)
        current = [Image.fromarray((frame*255).astype(np.uint8)) for frame in output[0]]
        all_frames = list(current); ref_latent = latent[:,:,:1].clone()
        for segment in (1,2):
            width, height = current[0].size
            print({'engine':'longcat','product':job['product'],'segment':segment+1}, flush=True)
            output, latent = pipe.generate_avc(video=current, video_latent=latent, prompt=job['prompt'],
                                               negative_prompt=negative, height=height, width=width,
                                               num_frames=93, num_cond_frames=13, num_inference_steps=8,
                                               text_guidance_scale=1.0, audio_guidance_scale=1.0,
                                               generator=generator, output_type='both', use_kv_cache=True,
                                               offload_kv_cache=False, enhance_hf=False, audio_emb=audio_chunk(segment*80),
                                               ref_latent=ref_latent, ref_img_index=10, mask_frame_range=3,
                                               use_distill=True)
            current = [Image.fromarray((frame*255).astype(np.uint8)) for frame in output[0]]
            all_frames.extend(current[13:])
    native = out/'native.mp4'; native_frames = save_frames(all_frames, native)
    receipt('longcat', job, source, out, native, loaded, started,
            {'scope':'Official image+audio+text generation and two continuation chunks; all hands/products/actions are generated by LongCat.',
             'steps_per_chunk':8, 'chunks':3, 'native_frames':native_frames, 'model_generates_product_actions':True,
             'original_LTX_actions_preserved':False,
             'compatibility':['Single GPU context parallel world size 1', 'FlashAttention-2 interface uses equivalent dense PyTorch SDPA',
                              'Clean Serena speech used directly without vocal separation'],
             'action_quality':'Not yet visually accepted; inspect pickup, product contact and return.'})
dist.destroy_process_group()
