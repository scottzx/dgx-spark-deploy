"""Official JoyHallo networks and inference chunks, without training scaffolding."""
import os
import json
from pathlib import Path
import sys
import time
from bench_common import ROOT, MODELS, gpu_lock, jobs, cpu_onnx, trusted_torch_load, link, receipt, save_frames, sha

lock = gpu_lock()
source = ROOT/'sources/JoyHallo-src'; os.chdir(source)
sys.path[:0] = [str(ROOT/'compat'), str(ROOT/'deps/common'), str(source)]
from flash_sdpa import install
install(with_xformers=True)
import torch
import numpy as np
from PIL import Image
from omegaconf import OmegaConf
from diffusers import AutoencoderKL, DDIMScheduler
from joyhallo.models.unet_2d_condition import UNet2DConditionModel
from joyhallo.models.unet_3d import UNet3DConditionModel
from joyhallo.models.face_locator import FaceLocator
from joyhallo.models.image_proj import ImageProjModel
from joyhallo.models.audio_proj import AudioProjModel
from joyhallo.models.wav2vec import Wav2VecModel
from joyhallo.animate.face_animate import FaceAnimatePipeline
from joyhallo.datasets.image_processor import ImageProcessor
from joyhallo.datasets.audio_processor import AudioProcessor
cpu_onnx(); trusted_torch_load()
link(MODELS/'hallo_base/face_analysis', source/'pretrained_models/face_analysis')
original_wav2vec_loader = Wav2VecModel.from_pretrained
@classmethod
def eager_wav2vec(cls, *args, **kwargs):
    kwargs['attn_implementation'] = 'eager'
    return original_wav2vec_loader(*args, **kwargs)
Wav2VecModel.from_pretrained = eager_wav2vec

config = OmegaConf.load(source/'configs/inference/inference.yaml')
dtype = torch.float16
started = time.perf_counter()
vae = AutoencoderKL.from_pretrained(MODELS/'hallo_base/sd-vae-ft-mse').to('cuda', dtype=dtype)
reference_unet = UNet2DConditionModel.from_pretrained(MODELS/'hallo_base/stable-diffusion-v1-5', subfolder='unet').to('cuda', dtype=dtype)
denoising_unet = UNet3DConditionModel.from_pretrained_2d(str(MODELS/'hallo_base/stable-diffusion-v1-5'),
                                                       str(MODELS/'hallo_base/motion_module/mm_sd_v15_v2.ckpt'),
                                                       subfolder='unet', unet_additional_kwargs=OmegaConf.to_container(config.unet_additional_kwargs),
                                                       use_landmark=False).to('cuda', dtype=dtype)
imageproj = ImageProjModel(cross_attention_dim=denoising_unet.config.cross_attention_dim,
                           clip_embeddings_dim=512, clip_extra_context_tokens=4).to('cuda', dtype=dtype)
face_locator = FaceLocator(conditioning_embedding_channels=320).to('cuda', dtype=dtype)
audioproj = AudioProjModel(seq_len=5, blocks=12, channels=768, intermediate_dim=512,
                           output_dim=768, context_tokens=32).to('cuda', dtype=dtype)
# The same parameter names as the official Net; its training-only forward and
# optimizer/dataloader scaffolding are unnecessary for FaceAnimatePipeline.
net = torch.nn.Module()
for name, module in dict(reference_unet=reference_unet, denoising_unet=denoising_unet,
                          imageproj=imageproj, face_locator=face_locator, audioproj=audioproj).items():
    net.add_module(name, module)
net.load_state_dict(torch.load(MODELS/'joyhallo/net.pth', map_location='cpu'), strict=True)
net.eval().requires_grad_(False); vae.eval().requires_grad_(False)
kwargs = OmegaConf.to_container(config.noise_scheduler_kwargs)
if config.enable_zero_snr:
    kwargs.update(rescale_betas_zero_snr=True, timestep_spacing='trailing', prediction_type='v_prediction')
pipe = FaceAnimatePipeline(vae=vae, reference_unet=reference_unet, denoising_unet=denoising_unet,
                           face_locator=face_locator, image_proj=imageproj, scheduler=DDIMScheduler(**kwargs)).to('cuda')
image_processor = ImageProcessor((512,512), str(MODELS/'hallo_base/face_analysis'))
audio_processor = AudioProcessor(16000,25, '/home/admin/models_cache/digital_human/chinese-wav2vec2-base',
                                  False, audio_separator_model_name=None, device='cuda')
torch.cuda.synchronize(); loaded = time.perf_counter()-started
print({'stage':'loaded','engine':'joyhallo','seconds':loaded}, flush=True)

for job in jobs():
    case = Path(job['directory']); out = ROOT/'outputs/joyhallo'/job['product']; out.mkdir(parents=True, exist_ok=True)
    generator = torch.Generator(device='cuda').manual_seed(job['seed'])
    torch.cuda.reset_peak_memory_stats(); started = time.perf_counter()
    # Official recommended portrait framing: retain the same source identity,
    # crop around its detected face. This does not test product/body actions.
    image = Image.open(case/'first_frame.png').convert('RGB')
    faces = image_processor.face_analysis.get(np.asarray(image)[:,:,::-1].copy())
    if not faces: raise RuntimeError('No face detected in the benchmark reference')
    face = max(faces, key=lambda f:(f.bbox[2]-f.bbox[0])*(f.bbox[3]-f.bbox[1]))
    x1,y1,x2,y2 = map(float,face.bbox)
    side = max(x2-x1,y2-y1)/0.55; cx,cy = (x1+x2)/2,(y1+y2)/2
    left = max(0,min(image.width-side,cx-side/2)); top = max(0,min(image.height-side,cy-side/2))
    crop = (round(left),round(top),round(left+side),round(top+side))
    portrait = out/'portrait_reference.png'; image.crop(crop).resize((512,512)).save(portrait)
    (out/'cache').mkdir(exist_ok=True)
    pixels, region, embedding, full_masks, face_masks, lip_masks = image_processor.preprocess(
        str(portrait), str(out/'cache'), config.face_expand_ratio)
    audio_emb, audio_length = audio_processor.preprocess(str(case/'audio_16k.wav'),16)
    indices = torch.clamp(torch.arange(audio_emb.shape[0])[:,None] + torch.arange(-2,3)[None], 0, audio_emb.shape[0]-1)
    audio_emb = audio_emb[indices]
    pixels = pixels.unsqueeze(0)
    region = region.unsqueeze(0)
    embedding = torch.as_tensor(embedding.reshape(1,-1))
    full_masks = [m.repeat(16,1) for m in full_masks]
    face_masks = [m.repeat(16,1) for m in face_masks]
    lip_masks = [m.repeat(16,1) for m in lip_masks]
    outputs = []
    with torch.inference_mode():
        for chunk in range(audio_emb.shape[0]//16):
            if outputs:
                motion = outputs[-1][0].permute(1,0,2,3)[-2:]*2.0-1.0
                motion = motion.to(device=pixels.device, dtype=pixels.dtype)
            else:
                motion = pixels.repeat(2,1,1,1)
            reference = torch.cat([pixels,motion],dim=0).unsqueeze(0)
            audio = audioproj(audio_emb[chunk*16:(chunk+1)*16][None].to('cuda',dtype=dtype))
            print({'engine':'joyhallo','product':job['product'],'chunk':chunk+1},flush=True)
            result = pipe(ref_image=reference, audio_tensor=audio, face_emb=embedding, face_mask=region,
                           pixel_values_full_mask=full_masks, pixel_values_face_mask=face_masks,
                           pixel_values_lip_mask=lip_masks, width=512,height=512,video_length=16,
                           num_inference_steps=40,guidance_scale=3.5,generator=generator)
            outputs.append(result.videos)
    frames = torch.cat(outputs,dim=2)[0,:,:audio_length].permute(1,2,3,0).float().cpu().numpy()
    frame_bytes = np.clip(frames*255,0,255).astype(np.uint8)
    # Keep the actual decoded frames before encoding, so a codec failure can
    # be repaired on CPU without repeating the diffusion run.
    np.save(out/'decoded_frames.npy',frame_bytes)
    checkpoint = {'engine':'joyhallo','product':job['product'],'shared_model_load_seconds':loaded,
                  'render_seconds_before_encoding':time.perf_counter()-started,
                  'peak_cuda_allocated_gib':torch.cuda.max_memory_allocated()/2**30,
                  'portrait_crop_xyxy':crop,'portrait_reference_sha256':sha(portrait),
                  'decoded_frames_shape':list(frame_bytes.shape),'decoded_frames_sha256':sha(out/'decoded_frames.npy')}
    (out/'generation_checkpoint.json').write_text(json.dumps(checkpoint,indent=2)+'\n')
    native = out/'native.mp4'; native_frames = save_frames(frame_bytes,native)
    receipt('joyhallo',job,source,out,native,loaded,started,
            {'scope':'Official audio-driven portrait model, face cropped from the original generated reference. Does not generate product actions.',
             'portrait_crop_xyxy':crop, 'portrait_reference_sha256':sha(portrait), 'native_frames':native_frames,
             'steps_per_chunk':40,'guidance_scale':3.5,'model_generates_product_actions':False,
             'original_LTX_actions_preserved':False,
             'compatibility':['CPU ONNX face detection/embedding', 'MediaPipe 1.1.0 ARM64 official wheel',
                              'Wav2Vec2 eager attention', 'Published inference without training optimizer/dataloader',
                              'Clean speech without source separation', 'PyTorch SDPA attention adapter where required']})
