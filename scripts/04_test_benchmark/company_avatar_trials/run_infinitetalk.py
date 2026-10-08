"""Run the official InfiniteTalk demo V2V path with shared official models."""
import collections
import inspect
import json
import os
from pathlib import Path
import sys
import time
import types
from bench_common import ROOT, MODELS, gpu_lock, jobs, receipt, trusted_torch_load

lock = gpu_lock()
source = ROOT/'sources/InfiniteTalk'; os.chdir(source)
sys.path[:0] = [str(ROOT/'compat'), str(ROOT/'deps/common'), str(source)]
os.environ['XDIT_LOGGING_LEVEL'] = 'ERROR'
if not hasattr(inspect, 'ArgSpec'):
    inspect.ArgSpec = collections.namedtuple('ArgSpec', 'args varargs keywords defaults')
from flash_sdpa import install
install(with_xformers=True)
# The repository imports its optional demo TTS eagerly. This run uses already
# synthesized Serena audio; invoking the disabled demo TTS raises an error.
kokoro = types.ModuleType('kokoro')
class DisabledTTS:
    def __init__(self, *args, **kwargs):
        raise RuntimeError('Demo TTS is disabled; benchmark must use the original Serena audio')
kokoro.KPipeline = DisabledTTS
sys.modules['kokoro'] = kokoro
import torch
import generate_infinitetalk as demo
trusted_torch_load()

original_pipeline = demo.wan.InfiniteTalkPipeline
original_audio = demo.custom_init
cache = {}
load_time = 0.0
def shared_pipeline(*args, **kwargs):
    global load_time
    if 'pipeline' not in cache:
        started = time.perf_counter()
        cache['pipeline'] = original_pipeline(*args, **kwargs)
        torch.cuda.synchronize(); load_time += time.perf_counter()-started
    return cache['pipeline']
def shared_audio(*args, **kwargs):
    global load_time
    if 'audio' not in cache:
        started = time.perf_counter()
        device, wav2vec = args
        encoder = demo.Wav2Vec2Model.from_pretrained(wav2vec, local_files_only=True,
                                                    attn_implementation='eager').to(device)
        encoder.feature_extractor._freeze_parameters()
        extractor = demo.Wav2Vec2FeatureExtractor.from_pretrained(wav2vec, local_files_only=True)
        cache['audio'] = (extractor, encoder)
        load_time += time.perf_counter()-started
    return cache['audio']
demo.wan.InfiniteTalkPipeline = shared_pipeline
demo.custom_init = shared_audio

for job in jobs():
    case = Path(job['directory']); out = ROOT/'outputs/infinitetalk'/job['product']; out.mkdir(parents=True, exist_ok=True)
    input_path = out/'input.json'
    input_path.write_text(json.dumps({'prompt':job['prompt'], 'cond_video':str(case/'driver.mp4'),
                                      'cond_audio':{'person1':str(case/'audio_16k.wav')}}, ensure_ascii=False))
    sys.argv = ['generate_infinitetalk.py', '--ckpt_dir', str(MODELS/'wan21'),
                '--infinitetalk_dir', str(MODELS/'infinitetalk/single/infinitetalk.safetensors'),
                '--wav2vec_dir', '/home/admin/models_cache/digital_human/chinese-wav2vec2-base',
                '--input_json', str(input_path), '--save_file', str(out/'native'),
                '--audio_save_dir', str(out/'audio_features'), '--mode', 'streaming',
                '--size', 'infinitetalk-480', '--sample_steps', '8', '--motion_frame', '9',
                '--lora_dir', str(MODELS/'infinitetalk/loras/fusionx.safetensors'), '--lora_scale', '1.0',
                '--frame_num', '81', '--max_frame_num', '201', '--sample_text_guide_scale', '1',
                '--sample_audio_guide_scale', '2', '--sample_shift', '2', '--offload_model', 'True', '--base_seed', str(job['seed'])]
    options = demo._parse_args()
    torch.cuda.reset_peak_memory_stats(); started = time.perf_counter(); previous_load = load_time
    with torch.inference_mode(): demo.generate(options)
    # Remove measured initialization from the first case's render measurement.
    render_start = started + (load_time-previous_load)
    receipt('infinitetalk', job, source, out, out/'native.mp4', load_time, render_start,
            {'scope':'Official video-to-video InfiniteTalk. The LTX clip guides the action; InfiniteTalk regenerates the speaking video.',
             'steps_per_chunk':8, 'motion_frame':9, 'model_generates_product_actions':True,
             'variant':'Official documented FusionX LoRA accelerated inference, eight steps, scale 1.0',
             'original_LTX_actions_preserved':False,
             'compatibility':['FlashAttention-2 and single-device xFormers dense attention use PyTorch SDPA',
                              'inspect.ArgSpec restored for Python 3.12', 'Wav2Vec2 eager attention restores original attention-output behavior',
                              'Optional demo TTS disabled; same original Serena audio'],
             'action_quality':'Not yet visually accepted; inspect pickup, product contact and return.'})
