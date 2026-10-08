"""Official AvatarForever model with the published autoregressive cache route."""
import os
import argparse
from pathlib import Path
import sys
import time
from bench_common import ROOT, MODELS, gpu_lock, jobs, receipt

parser=argparse.ArgumentParser()
parser.add_argument('--products',nargs='+',choices=['original','diet','zero'],default=['original','diet','zero'])
parser.add_argument('--variant',choices=['baseline','no-cache','official-speaking'],default='baseline')
run_args=parser.parse_args()
engine={'baseline':'avatarforever','no-cache':'avatarforever_nocache','official-speaking':'avatarforever_speaking'}[run_args.variant]
lock = gpu_lock()
source = ROOT/'sources/avatarforever'; os.chdir(source)
sys.path[:0] = [str(ROOT/'compat'), str(ROOT/'deps/common'), str(source),
                str(source/'packages/ltx-core/src'), str(source/'packages/ltx-pipelines/src')]
import torch
import inference as demo
from ltx_pipelines import ARA2VidDistilledPipeline
from ltx_pipelines.utils.media_io import encode_video
from ltx_core.model.video_vae import get_video_chunks_number
from util import build_first_frame_images, build_tiling_config, encode_first_frame_channel_condition

started = time.perf_counter()
pipeline = ARA2VidDistilledPipeline(distilled_checkpoint_path=str(MODELS/'avatarforever/avatarforever-ltx-2.3-22b.safetensors'),
                                   spatial_upsampler_path=None, gemma_root=str(MODELS/'gemma3'), loras=[])
constructor_seconds = time.perf_counter()-started
print({'stage':'constructed','engine':'avatarforever','seconds':constructor_seconds,
        'note':'Model builders may load lazily; render measurements include any lazy loading.'}, flush=True)
for job in jobs():
    if job['product'] not in run_args.products: continue
    prompt=demo.DEFAULT_PROMPT if run_args.variant=='official-speaking' else job['prompt']
    feature_cache=run_args.variant=='baseline'
    case = Path(job['directory']); out = ROOT/'outputs'/engine/job['product']; out.mkdir(parents=True, exist_ok=True)
    options = demo.build_arg_parser().parse_args([
        '--distilled-checkpoint-path', str(MODELS/'avatarforever/avatarforever-ltx-2.3-22b.safetensors'),
        '--gemma-root', str(MODELS/'gemma3'), '--audio-path', str(case/'audio.wav'),
        '--prompt', prompt, '--seed', str(job['seed']), '--height', '512', '--width', '768',
        '--num-frames', '201', '--frame-rate', '25', '--first-frame-condition-image-path', str(case/'first_frame.png'),
        '--ar-history-feature-cache' if feature_cache else '--no-ar-history-feature-cache',
        '--output-path', str(out/'native.mp4')])
    torch.cuda.reset_peak_memory_stats(); started = time.perf_counter()
    with torch.inference_mode():
        images = build_first_frame_images(options.first_frame_condition_image_path,
                                         strength=options.first_frame_image_strength, crf=options.first_frame_image_crf)
        latent = encode_first_frame_channel_condition(pipeline, image_path=options.first_frame_condition_image_path,
                                                       enabled=True, height=512, width=768,
                                                       crf=options.first_frame_image_crf)
        tiling = build_tiling_config(options)
        video, audio = pipeline(prompt=prompt, seed=job['seed'], height=512, width=768, num_frames=201,
                                frame_rate=25.0, images=images, audio_path=str(case/'audio.wav'),
                                audio_start_time=0.0, audio_max_duration=8.04, tiling_config=tiling,
                                enhance_prompt=False, stage_mode='one-stage', stage1_sigmas=options.stage1_sigmas,
                                ar_video_chunk_size=4, ar_history_chunk_count=1, ar_sink_first_chunk=True,
                                ar_relative_positions=True, ar_history_feature_cache=feature_cache,
                                ar_first_frame_prefix_condition=False, ar_first_frame_condition_position='prepend',
                                first_frame_channel_condition_latent=latent,
                                first_frame_channel_condition_init='zero', first_frame_channel_condition_mode='gated',
                                ar_first_frame_channel_condition_from_first_chunk=latent is None,
                                ar_channel_condition_current_chunk_only=True, fast_infer=False)
        encode_video(video=video, fps=25.0, audio=audio, output_path=str(out/'native.mp4'),
                      video_chunks_number=get_video_chunks_number(201, tiling), crf=12, preset='fast')
    receipt(engine, job, source, out, out/'native.mp4', constructor_seconds, started,
            {'scope':f'Official AvatarForever first-frame + audio + text generation; history feature cache={feature_cache}, prompt variant={run_args.variant}.',
             'model_loading_is_lazy':True, 'timing_includes_lazy_model_loads':True, 'fast_infer':False,
             'variant':run_args.variant,'prompt':prompt,'ar_history_feature_cache':feature_cache,
             'product_action_requested':run_args.variant!='official-speaking',
             'model_generates_product_actions':True, 'original_LTX_actions_preserved':False,
             'compatibility':['Existing GB10 PyTorch 2.14.1 / CUDA 13 instead of repository Torch 2.7 environment'],
             'action_quality':'Not yet visually accepted; inspect pickup, product contact and return.'})
