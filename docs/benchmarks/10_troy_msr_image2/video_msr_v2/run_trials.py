#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Task-scoped native MSR video batch and graceful resident-service restoration.

MSR conditioning is imported from the verified benchmark adapter; its math follows
liconstudio/ComfyUI-LTX2.5-MSR revision 03061c18f8a79d26f3c63931dd8e28f5e5d872a6.
"""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import urllib.request

RUNTIME = Path('/home/admin/sol-spark-runtime')
PACKAGE = Path('/home/admin/sol-h3-spark/models/minimax_h3/Sol-H3-Spark')
FFMPEG = '/home/admin/.local/bin/ffmpeg'
FFPROBE = '/home/admin/.local/bin/ffprobe'
ROOT = Path(__file__).resolve().parent
sys.path[:0] = [str(PACKAGE), str(RUNTIME)]

def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix+'.partial')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n')
    temporary.replace(path)

def emit(**value):
    value['time_unix'] = time.time()
    print(json.dumps(value, ensure_ascii=False), flush=True)
    save(ROOT/'progress.json', value)

def sha(path):
    with Path(path).open('rb') as source:
        return hashlib.file_digest(source, 'sha256').hexdigest()

def health():
    try:
        with urllib.request.urlopen('http://127.0.0.1:8090/health', timeout=3) as response:
            return json.load(response)
    except Exception:
        return None

def paths_and_imports():
    paths = json.loads((RUNTIME/'paths.json').read_text())
    sys.path[:0] = [str(Path(paths['ltx_root'])/'packages'/p/'src') for p in ('ltx-core','ltx-pipelines','ltx-kernels')]
    sys.path.insert(0, str(RUNTIME/'dependencies/offline-context'))
    return paths

def validate_manifest(story):
    assert story['remote_root'] == str(ROOT)
    assert len(story['shots']) == 24 and story['frames'] == 2880
    assert story['steps'] == 8 and story['fps'] == 24
    for shot in story['shots']:
        payload={k:v for k,v in shot.items() if k!='input_fingerprint'}
        assert hashlib.sha256(json.dumps(payload,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()==shot['input_fingerprint']
        assert 1 <= len(shot['slots']) <= 5
        assert hashlib.sha256(shot['prompt'].encode()).hexdigest() == shot['prompt_sha256']
        for slot in shot['slots']:
            assert sha(ROOT/slot['file']) == slot['sha256'], slot

def media(path, frames, size):
    data = json.loads(subprocess.check_output([FFPROBE,'-v','error','-count_frames',
        '-show_streams','-show_format','-of','json',str(path)]))
    video = next(s for s in data['streams'] if s['codec_type'] == 'video')
    audio = next(s for s in data['streams'] if s['codec_type'] == 'audio')
    assert int(video['nb_read_frames']) == frames, data
    assert [video['width'],video['height']] == size and video['r_frame_rate'] == '24/1', data
    assert audio['channels'] == 2
    subprocess.run([FFMPEG,'-v','error','-xerror','-i',str(path),'-f','null','-'],check=True,capture_output=True)
    return dict(frames=frames,width=size[0],height=size[1],fps=24,duration_s=frames/24,
                container_duration_s=float(data['format']['duration']),audio_sample_rate=int(audio['sample_rate']),
                channels=2,full_decode=True,sha256=sha(path),bytes=path.stat().st_size)

def caches(story):
    paths = paths_and_imports()
    import torch
    from runtime import cache_builder
    from runtime.prompt_cache import load_cache
    rows = []
    for shot in {x['case_id']:x for x in story['shots']}.values():
        output = ROOT/'prompt_caches'/(shot['case_id']+'.pt')
        emit(status='ENCODING_PROMPT',shot=shot['id'],total=4)
        if output.exists():
            cache = load_cache(output,prompt=shot['prompt'],torch_module=torch)
            row = cache.receipt()
        else:
            cache_builder.FIXED_PROMPT = shot['prompt']
            row = cache_builder.build_cache(paths,output)
        rows.append(row)
    save(ROOT/'prompt_caches/report.json',dict(status='PASS',caches=rows,manifest_fingerprint=story['fingerprint']))

def render(story):
    paths = paths_and_imports()
    import torch
    from safetensors import safe_open
    from safetensors.torch import load_file,save_file
    from ltx_core.allocator_trim_strategy import AllocatorTrimStrategy
    from ltx_core.components.noisers import GaussianNoiser
    from ltx_core.loader import LoraPathStrengthAndSDOps,LTXV_LORA_COMFY_RENAMING_MAP
    from ltx_core.loader.registry import ModelRegistry
    from ltx_core.model.video_vae import get_video_chunks_number
    from ltx_pipelines.utils.blocks import ImageConditioner,DiffusionStage,VideoDecoder,AudioDecoder
    from ltx_pipelines.utils.constants import DISTILLED_SIGMAS
    from ltx_pipelines.utils.denoisers import SimpleDenoiser
    from ltx_pipelines.utils.media_io import encode_video
    from ltx_pipelines.utils.samplers import euler_denoising_loop
    from ltx_pipelines.utils.types import ModalitySpec
    from runtime.prompt_cache import load_cache
    from run_ltx_identity_trial import MSRCondition,reorder,resize_reference,slot_embedding
    original = RUNTIME/'identity_tests_20261003/weights/LTX-2.5-Licon-MSR-V2.safetensors'
    receipt = json.loads(original.with_name(original.name+'.receipt.json').read_text())
    assert sha(original) == receipt['sha256'] == '7cf982168d4f77f44b02943fb458f937f90c89335dcf7cf71b2f425e78bab713'
    with safe_open(original,framework='pt',device='cpu') as source:
        metadata = source.metadata() or {}
    state, normal = {}, {}
    for key,value in load_file(original).items():
        stripped = key.removeprefix('diffusion_model.')
        if stripped.startswith('reference_slot_embedding.'):
            state[stripped.removeprefix('reference_slot_embedding.')] = value
        elif not stripped.startswith('reference_audio_slot_embedding.'):
            normal[key] = value
    # Reuse and verify the previously derived checkpoint without modifying it.
    lora = RUNTIME/'troy_image2_msr_20261005/image_only_lora.safetensors'
    if not lora.exists():
        save_file(normal,str(lora),metadata=metadata)
    else:
        with safe_open(lora,framework='pt',device='cpu') as f:
            assert set(f.keys()) == set(normal)
            for key,value in normal.items():
                assert torch.equal(f.get_tensor(key),value), key
    del normal
    save(ROOT/'weights.json',dict(original=str(original),original_receipt=receipt,
        image_only_lora=str(lora),image_only_sha256=sha(lora),adapter_source=str(RUNTIME/'run_ltx_identity_trial.py'),
        adapter_sha256=sha(RUNTIME/'run_ltx_identity_trial.py'),strength=1.0))
    downscale = int(float(metadata.get('reference_downscale_factor','1')))
    assert downscale >= 1 and 768%downscale == 0 and 448%downscale == 0
    device,dtype = torch.device('cuda:0'),torch.bfloat16
    registry = ModelRegistry(cache_models=False,cache_weights=False)
    encoder = ImageConditioner(paths['output_video_vae'],dtype,device,registry=registry)
    loras = tuple(LoraPathStrengthAndSDOps(str(p),1.,LTXV_LORA_COMFY_RENAMING_MAP) for p in (paths['refiner_lora'],lora))
    stage = DiffusionStage.from_checkpoint(paths['transformer'],dtype,device,loras=loras,
        registry=registry,alloc_trim_strategy=AllocatorTrimStrategy.TRIM)
    # Resident execution is enabled only after a same-input latent regression probe.
    from contextlib import nullcontext
    from ltx_pipelines.utils.helpers import combined_image_conditionings
    from ltx_pipelines.utils.args import ImageConditioningInput
    native_context = stage._transformer_ctx
    resident_model = None
    def resident_context(**kw):
        nonlocal resident_model
        if resident_model is None:
            resident_model = stage._build_transformer(**kw)
        return nullcontext(resident_model)
    rows = []
    probe_done = (ROOT/'resident_regression.json').exists()
    use_resident = probe_done and json.loads((ROOT/'resident_regression.json').read_text()).get('bitwise_equal',False)
    if use_resident:
        stage._transformer_ctx = resident_context
    for index,shot in enumerate(story['shots'],1):
        destination = ROOT/'clips'/shot['id']
        destination.mkdir(parents=True,exist_ok=True)
        result_file = destination/'result.json'
        if result_file.exists():
            row = json.loads(result_file.read_text())
            assert row['input_fingerprint'] == shot['input_fingerprint']
            assert sha(destination/'delivered.mp4') == row['media']['sha256']
            rows.append(row)
            continue
        emit(status='GENERATING',shot=shot['id'],title=shot['title'],index=index,completed=len(rows),total=24)
        started = time.monotonic()
        torch.cuda.reset_peak_memory_stats()
        phases,audit = {},[]
        cache = load_cache(ROOT/'prompt_caches'/(shot['case_id']+'.pt'),prompt=shot['prompt'],torch_module=torch)
        vc,ac = cache.contexts(shot['prompt'],device)
        def prepare(enc):
            conditions = []
            for i,slot in enumerate(shot['slots']):
                pixels = resize_reference(str(ROOT/slot['file']),768//downscale,448//downscale,
                                          background=slot['kind'] != 'character')
                pixels = pixels[None,:,None].repeat(1,1,33,1,1).to(device=device,dtype=dtype)
                latent = enc(pixels)
                latent = latent+slot_embedding(i+1,state,device,dtype).view(1,-1,1,1,1)
                offset = i-len(shot['slots'])
                conditions.append(MSRCondition(latent,offset,downscale))
                audit.append(dict(**slot,offset=offset,latent_shape=list(latent.shape),
                    preprocessing='pad full portrait' if slot['kind']=='character' else 'fit wide reference'))
            temporal = [ImageConditioningInput(path=str(ROOT/t['file']),frame_idx=t['frame_index'],strength=t['strength'],crf=0) for t in shot['temporal']]
            conditions.extend(combined_image_conditionings(temporal,448,768,enc,dtype,device))
            for t in shot['temporal']:
                audit.append(dict(**t,kind='temporal_anchor',conditioning='replace latent0' if t['frame_index']==0 else 'append guiding tokens at pixel frame120'))
            return conditions
        def loop(**kw):
            torch.cuda.synchronize(); t0 = time.monotonic()
            s = kw['video_state']; n = 16*14*24
            msr_tokens = len(shot['slots'])*5*14*24
            end_tokens = 14*24 if shot['method']=='msr_first_last' else 0
            assert s.latent.shape[1] == n+msr_tokens+end_tokens
            assert s.attention_mask is None
            if shot['temporal']:
                assert (s.denoise_mask[:,:14*24]==0).all(), 'First frame must be clean'
            if end_tokens:
                assert (s.denoise_mask[:,-end_tokens:]==0).all(), 'End guides must be clean'
                assert torch.allclose(s.positions[:,0,-end_tokens:,0],torch.full_like(s.positions[:,0,-end_tokens:,0],5.)), 'End guides at5s'
            # Preserve the verified v1 adapter: each 33-frame reference begins
            # at a distinct negative offset; later VAE temporal cells retain spacing.
            for i in range(len(shot['slots'])):
                first=n+i*5*14*24
                expected=(i-len(shot['slots']))/24.
                assert torch.allclose(s.positions[:,0,first:first+14*24,0],torch.full_like(s.positions[:,0,first:first+14*24,0],expected)), 'MSR slot start offset'

            perm = torch.cat((torch.arange(n,s.latent.shape[1],device=device),torch.arange(n,device=device)))
            kw['video_state'] = reorder(s,perm)
            video,audio = euler_denoising_loop(**kw)
            video = reorder(video,torch.argsort(perm))
            torch.cuda.synchronize(); phases['denoising_loop_s'] = time.monotonic()-t0
            return video,audio
        with torch.inference_mode():
            t0 = time.monotonic(); conditions = encoder(prepare)
            torch.cuda.synchronize(); phases['reference_encode_block_s'] = time.monotonic()-t0
            generator = torch.Generator(device=device).manual_seed(shot['seed'])
            t0 = time.monotonic()
            kwargs=dict(denoiser=SimpleDenoiser(vc,ac),sigmas=DISTILLED_SIGMAS.to(device),
                width=768,height=448,frames=121,fps=24.,
                video=ModalitySpec(context=vc,conditionings=conditions),audio=ModalitySpec(context=ac),loop=loop)
            if not probe_done:
                video0,audio0=stage(noiser=GaussianNoiser(torch.Generator(device=device).manual_seed(shot['seed'])),**kwargs)
                video0,audio0=video0.latent.cpu(),audio0.latent.cpu()
                torch.save(dict(video=video0,audio=audio0),ROOT/'conservative_probe.pt')
                stage._transformer_ctx=resident_context
                video,audio=stage(noiser=GaussianNoiser(torch.Generator(device=device).manual_seed(shot['seed'])),**kwargs)
                equal=torch.equal(video.latent.cpu(),video0) and torch.equal(audio.latent.cpu(),audio0)
                save(ROOT/'resident_regression.json',dict(bitwise_equal=equal,probe_id=shot['id'],input_fingerprint=shot['input_fingerprint'],video_max_abs_delta=float((video.latent.cpu()-video0).abs().max()),audio_max_abs_delta=float((audio.latent.cpu()-audio0).abs().max()),ltx_revision='d151147788a9284cca791edc6ce898007e727fe6',policy='same pre-encoded conditions, prompt context, seed, sigmas and weights; retain built transformer only after numerical validation'))
                probe_done=True;use_resident=equal
                if not equal:
                    resident_model=None;stage._transformer_ctx=native_context
                    del video,audio;torch.cuda.empty_cache()
                    video,audio=stage(noiser=GaussianNoiser(generator),**kwargs)
                del video0,audio0
            else:
                video,audio=stage(noiser=GaussianNoiser(generator),**kwargs)
            torch.cuda.synchronize(); phases['diffusion_block_s'] = time.monotonic()-t0
            torch.save(dict(video=video.latent.cpu(),audio=audio.latent.cpu()),destination/'generated_latents.pt')
            t0 = time.monotonic()
            chunks = VideoDecoder(paths['output_video_vae'],dtype,device,registry=registry)(video.latent,None,generator,dtype=dtype)
            sound = AudioDecoder(paths['audio_vae'],dtype,device,registry=registry)(audio.latent)
            raw = destination/'raw.mp4'
            encode_video(video=chunks,fps=24.,audio=sound,output_path=str(raw),
                video_chunks_number=get_video_chunks_number(121,None),crf=19,preset='fast')
            torch.cuda.synchronize(); phases['decode_and_encode_block_s'] = time.monotonic()-t0
        generation_s = time.monotonic()-started
        peak = torch.cuda.max_memory_allocated()
        delivered = destination/'delivered.mp4'
        temporary = destination/'delivered.partial.mp4'
        subprocess.run([FFMPEG,'-y','-v','error','-i',str(raw),
            '-vf','trim=end_frame=120,setpts=PTS-STARTPTS,crop=768:432:0:8',
            '-af','atrim=end=5,asetpts=PTS-STARTPTS','-frames:v','120',
            '-c:v','libx264','-preset','fast','-crf','19','-pix_fmt','yuv420p',
            '-c:a','aac','-ar','32000','-ac','2','-b:a','192k','-movflags','+faststart',str(temporary)],
            check=True,capture_output=True)
        checked = media(temporary,120,[768,432]); temporary.replace(delivered)
        row = dict(status='PASS',id=shot['id'],title=shot['title'],seed=shot['seed'],
            manifest_fingerprint=story['fingerprint'],input_fingerprint=shot['input_fingerprint'],method=shot['method'],resident_transformer=use_resident,case_id=shot['case_id'],steps=8,
            output=str(raw),raw_sha256=sha(raw),delivered_output=str(delivered),delivered_frames=120,
            media=checked,generation_s=generation_s,phases_s=phases,conditions=audit,
            prompt_sha256=shot['prompt_sha256'],prompt_cache_fingerprint=cache.receipt()['fingerprint'],
            peak_torch_allocated_bytes=peak,transition='independent',audio_reference=False,
            quality_status='not_yet_manually_reviewed',native_size=[768,448],delivery_crop=[0,8,768,432])
        save(result_file,row); rows.append(row)
        emit(status='SHOT_COMPLETE',shot=shot['id'],title=shot['title'],completed=len(rows),total=24,generation_s=generation_s)
        del video,audio,conditions,vc,ac
        torch.cuda.empty_cache()
    save(ROOT/'result.json',dict(status='TECHNICAL_PASS',manifest_fingerprint=story['fingerprint'],clips=rows,resident_transformer=use_resident,quality_selection='pending manual review'))
    emit(status='TRIALS_COMPLETE',completed=24,total=24)

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--phase',choices=['caches','render'],required=True)
    args=parser.parse_args()
    story=json.loads((ROOT/'manifest.json').read_text())
    validate_manifest(story)
    for shot in story['shots']:
        for t in shot['temporal']:
            assert sha(ROOT/t['file'])==t['sha256']
    {'caches':caches,'render':render}[args.phase](story)
if __name__=='__main__':main()
