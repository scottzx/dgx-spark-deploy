#!/usr/bin/env python3
"""Run pinned H3 captures, controlled refiners and native reference story trials.

Run phases on Spark. The queue pauses its own video server, owns inference.lock
for offline GPU work, and restores FL2VA in finally. Qwen text is not started.
MSR helpers retain the Apache-2.0 provenance of run_ltx_identity_trial.py.
"""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time
import urllib.request

R = Path('/home/admin/sol-spark-runtime')
D = R/'troy_climax_20261004'
PACKAGE = Path('/home/admin/sol-h3-spark/models/minimax_h3/Sol-H3-Spark')
FFMPEG = '/home/admin/.local/bin/ffmpeg'
FFPROBE = '/home/admin/.local/bin/ffprobe'
sys.path.insert(0, str(PACKAGE))


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix+'.partial')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n')
    temporary.replace(path)


def emit(**row):
    print(json.dumps(row, ensure_ascii=False), flush=True)


def api(path, payload=None, timeout=1800):
    req = urllib.request.Request('http://127.0.0.1:8090'+path,
        data=json.dumps(payload).encode() if payload is not None else None,
        headers={'Content-Type':'application/json'})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return json.load(response)


def media(path, frames=None):
    data = json.loads(subprocess.check_output([FFPROBE, '-v','error','-count_frames',
        '-show_streams','-of','json',str(path)]))
    v = next(x for x in data['streams'] if x['codec_type']=='video')
    a = next(x for x in data['streams'] if x['codec_type']=='audio')
    count = int(v['nb_read_frames'])
    assert v['r_frame_rate']=='24/1' and a['channels']==2, data
    if frames is not None: assert count==frames, (count, frames, path)
    subprocess.run([FFMPEG,'-v','error','-xerror','-i',str(path),'-f','null','-'],check=True)
    return dict(frames=count, width=v['width'], height=v['height'], fps=24,
        duration_s=count/24, sample_rate=int(a['sample_rate']), channels=2, full_decode=True)


def deliver(source, destination, frames, start=0):
    destination.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run([FFMPEG,'-y','-v','error','-i',str(source),
        '-vf',f'trim=start_frame={start}:end_frame={start+frames},setpts=PTS-STARTPTS',
        '-af',f'atrim=start={start/24}:end={(start+frames)/24},asetpts=PTS-STARTPTS',
        '-frames:v',str(frames),'-c:v','libx264','-crf','19','-pix_fmt','yuv420p',
        '-c:a','aac','-ar','32000','-ac','2',str(destination)],check=True)
    return media(destination, frames)


def assemble(method, rows, story):
    from runtime.workflows import concatenate_clips
    output = D/method/'film.mp4'
    concatenate_clips([r['delivered_output'] for r in rows],
        [r['delivered_frames'] for r in rows], output)
    report = dict(status='PASS', method=method, clips=rows, output=str(output),
        media=media(output, story['frames']), comparison_scope=story['comparison_scope'])
    save(D/method/'comparison.json', report)
    emit(status='FILM_COMPLETE', method=method, output=str(output), frames=story['frames'])
    return report


def h3(story):
    if (D/'h3/comparison.json').exists():
        emit(status='REUSED', phase='h3'); return
    deadline = time.monotonic()+1800
    while True:
        try:
            status = api('/api/status', timeout=5)
            if status['status']=='READY': break
        except (OSError, RuntimeError): pass
        if time.monotonic()>deadline: raise TimeoutError('Ref2VA server did not become READY')
        time.sleep(10)
    assert status['task']=='ref2va', status
    save(D/'h3/status_before.json', status)
    # Do not resume a partial chain after a server restart: previous_clip_id is session-scoped.
    rows = []
    for i, shot in enumerate(story['shots']):
        case = dict(case_id=shot['case_id'], prompt=shot['h3_prompt'],
            references=[dict(type='image',path=p) for p in shot['references']],
            seed=shot['seed'], duration_s=5, mode='final', transition=shot['transition'])
        if shot['transition']=='continue':
            case.update(previous_clip_id=story['shots'][i-1]['case_id'],
                context_frames=22, audio_context_frames=24)
        save(D/'h3'/(shot['case_id']+'_request.json'), case)
        emit(status='GENERATING', method='h3_capture', shot=shot['title'])
        started = time.monotonic()
        row = api('/api/generate', case)
        row['client_wall_s'] = time.monotonic()-started
        assert row['delivered_frames']==shot['delivered_frames'], row
        if shot['transition']=='continue':
            assert row['continuation']['frozen_prefix_verified'], row
        row['media'] = media(row['video_path'], shot['delivered_frames'])
        save(D/'h3'/(shot['case_id']+'_response.json'), row)
        rows.append(row)
        save(D/'h3/progress.json', dict(status='RUNNING', clips=rows))
        emit(status='SHOT_COMPLETE', method='h3_capture', shot=shot['title'], e2e_s=row['e2e_s'])
    save(D/'h3/comparison.json', dict(status='PASS', clips=rows))


def ltx_paths():
    paths = json.loads((R/'paths.json').read_text())
    sys.path[:0] = [str(Path(paths['ltx_root'])/'packages'/p/'src')
                   for p in ['ltx-core','ltx-pipelines','ltx-kernels']]
    return paths


def caches():
    paths = ltx_paths()
    sys.path.insert(0, str(R/'dependencies/offline-context'))
    from runtime import cache_builder
    rows = []
    for name, prompt in json.loads((D/'ltx_prompts.json').read_text()).items():
        output = D/'prompt_caches'/(name+'.pt')
        if output.exists() and output.with_suffix('.json').exists():
            rows.append(json.loads(output.with_suffix('.json').read_text())); continue
        cache_builder.FIXED_PROMPT = prompt
        emit(status='ENCODING_PROMPT', prompt=name)
        rows.append(cache_builder.build_cache(paths, output))
    save(D/'prompt_caches/comparison.json', dict(status='PASS', caches=rows))


def refiner(story):
    import torch
    from runtime.stage2 import Session
    from runtime.prompt_cache import FIXED_PROMPT, load_cache
    paths = ltx_paths()
    first = story['shots'][0]
    paths['prompt_cache'] = str(D/'prompt_caches'/(first['prompt_keys']['specific']+'.pt'))
    started = time.monotonic()
    session = Session(paths, str(D/'refiner_session'),
                      dict(compile=False, fixed_prompt=first['ltx_prompt']))
    initialization_s = time.monotonic()-started
    rows = {'generic':[], 'specific':[]}
    try:
        captures = json.loads((D/'h3/comparison.json').read_text())['clips']
        for i, (shot, capture_row) in enumerate(zip(story['shots'], captures)):
            # Alternate processing order to reduce systematic first-call bias.
            for method in (['generic','specific'] if i%2==0 else ['specific','generic']):
                destination = D/method/shot['case_id']
                result_file = destination/'result.json'
                if result_file.exists():
                    rows[method].append(json.loads(result_file.read_text())); continue
                prompt = FIXED_PROMPT if method=='generic' else shot['ltx_prompt']
                cache = R/'fixed-prompt.pt' if method=='generic' else D/'prompt_caches'/(
                    shot['prompt_keys']['specific']+'.pt')
                session.fixed_prompt = prompt
                session.prompt_cache = load_cache(cache, prompt=prompt, torch_module=torch)
                torch.cuda.reset_peak_memory_stats()
                emit(status='GENERATING', method=method, shot=shot['title'])
                session.prepare(shot['case_id'], str(destination))
                row = session.run(capture_row['capture_dir'], str(destination), shot['case_id'])
                trim = int(row['capture'].get('continuation',{}).get('trim_frames',0))
                assert 121-trim==shot['delivered_frames'], (trim, shot)
                delivered = destination/'delivered.mp4'
                row.update(delivered_output=str(delivered), delivered_frames=shot['delivered_frames'],
                    trim_frames=trim, peak_torch_allocated_bytes=torch.cuda.max_memory_allocated(),
                    media=deliver(row['output'], delivered, shot['delivered_frames'], trim),
                    compile=False, same_session_pair=True)
                save(result_file, row)
                rows[method].append(row)
                emit(status='SHOT_COMPLETE', method=method, shot=shot['title'],
                     stage2_s=row['stage2_request_s'])
    finally:
        session.close()
    for method in rows:
        report = assemble(method, rows[method], story)
        report['shared_model_initialization_s'] = initialization_s
        report['generation_s'] = sum(r['stage2_request_s'] for r in rows[method])
        report['h3_text_and_stage1_s'] = sum(r['qwen_s']+r['stage1_s'] for r in captures)
        report['estimated_pipeline_compute_s'] = report['h3_text_and_stage1_s']+report['generation_s']
        report['timing_note'] = ('Estimated pipeline compute sums separately measured H3 and controlled '
            'Stage2; excludes service boot, offline prompt encoding, validation and assembly. '
            'Generic/specific share one uncompiled resident refiner; order alternates by shot.')
        save(D/method/'comparison.json', report)


def native(story, method):
    paths = ltx_paths()
    import torch
    from safetensors import safe_open
    from safetensors.torch import load_file, save_file
    from ltx_core.allocator_trim_strategy import AllocatorTrimStrategy
    from ltx_core.components.noisers import GaussianNoiser
    from ltx_core.loader import LoraPathStrengthAndSDOps, LTXV_LORA_COMFY_RENAMING_MAP
    from ltx_core.loader.registry import ModelRegistry
    from ltx_core.model.video_vae import get_video_chunks_number
    from ltx_pipelines.utils.blocks import ImageConditioner, DiffusionStage, VideoDecoder, AudioDecoder
    from ltx_pipelines.utils.constants import DISTILLED_SIGMAS
    from ltx_pipelines.utils.denoisers import SimpleDenoiser
    from ltx_pipelines.utils.media_io import encode_video
    from ltx_pipelines.utils.samplers import euler_denoising_loop
    from ltx_pipelines.utils.types import ModalitySpec
    from ltx_core.conditioning.types.reference_video_cond import VideoConditionByReferenceLatent
    from runtime.prompt_cache import load_cache
    from run_ltx_identity_trial import MSRCondition, reorder, resize_reference, slot_embedding
    output_root = D/method
    output_root.mkdir(parents=True, exist_ok=True)
    preparation_started = time.monotonic()
    filenames = dict(ingredients='ltx-2.5-22b-ic-lora-ingredients-0.9.safetensors',
                     msr='LTX-2.5-Licon-MSR-V2.safetensors')
    lora = R/'identity_tests_20261003/weights'/filenames[method]
    receipt = json.loads(lora.with_name(lora.name+'.receipt.json').read_text())
    with lora.open('rb') as source:
        assert hashlib.file_digest(source,'sha256').hexdigest()==receipt['sha256']
    with safe_open(lora,framework='pt',device='cpu') as f:
        metadata = f.metadata() or {}
    slot_state = None
    if method=='msr':
        slot_state, normal = {}, {}
        for key, value in load_file(lora).items():
            stripped = key.removeprefix('diffusion_model.')
            if stripped.startswith('reference_slot_embedding.'):
                slot_state[stripped.removeprefix('reference_slot_embedding.')] = value
            elif not stripped.startswith('reference_audio_slot_embedding.'):
                normal[key] = value
        lora = output_root/'image_only_lora.safetensors'
        if not lora.exists(): save_file(normal, str(lora), metadata=metadata)
        del normal
    downscale = int(float(metadata.get('reference_downscale_factor','1')))
    assert downscale>=1 and 768%downscale==0 and 448%downscale==0
    device, dtype = torch.device('cuda:0'), torch.bfloat16
    registry = ModelRegistry(cache_models=False, cache_weights=False)
    encoder = ImageConditioner(paths['output_video_vae'], dtype, device, registry=registry)
    loras = tuple(LoraPathStrengthAndSDOps(str(path),strength,LTXV_LORA_COMFY_RENAMING_MAP)
        for path,strength in [(paths['refiner_lora'],1.),(lora,1.)])
    stage = DiffusionStage.from_checkpoint(paths['transformer'], dtype, device, loras=loras,
        registry=registry, alloc_trim_strategy=AllocatorTrimStrategy.TRIM)
    preparation_s = time.monotonic()-preparation_started
    prompts = json.loads((D/'ltx_prompts.json').read_text())
    rows = []
    for shot in story['shots']:
        destination = output_root/shot['case_id']
        result_file = destination/'result.json'
        if result_file.exists():
            rows.append(json.loads(result_file.read_text())); continue
        destination.mkdir(parents=True, exist_ok=True)
        started = time.monotonic()
        torch.cuda.reset_peak_memory_stats()
        phase_times, audit = {}, []
        prompt = prompts[shot['prompt_keys'][method]]
        cache = load_cache(D/'prompt_caches'/(shot['prompt_keys'][method]+'.pt'),
                          prompt=prompt, torch_module=torch)
        video_context, audio_context = cache.contexts(prompt, device)
        def prepare(enc):
            conditions = []
            if method=='ingredients':
                pixels = resize_reference(shot['ingredients_sheet'],768,448)
                pixels = pixels[None,:,None].repeat(1,1,121,1,1).to(device=device,dtype=dtype)
                latent = enc(pixels)
                conditions.append(VideoConditionByReferenceLatent(latent,downscale_factor=1))
                audit.append(dict(type='static_sheet',latent_shape=list(latent.shape)))
            else:
                for i, path in enumerate(shot['references']):
                    background = Path(path).name not in ['red_identity.png','blue_identity.png','equipment.png']
                    pixels = resize_reference(path,768//downscale,448//downscale,background=background)
                    pixels = pixels[None,:,None].repeat(1,1,33,1,1).to(device=device,dtype=dtype)
                    latent = enc(pixels)
                    embedding = slot_embedding(i+1,slot_state,device,dtype)
                    latent = latent+embedding.view(1,-1,1,1,1)
                    offset = i-len(shot['references'])
                    conditions.append(MSRCondition(latent,offset,downscale))
                    audit.append(dict(type='image_slot',slot=i+1,offset=offset,
                                      latent_shape=list(latent.shape),source=path))
            return conditions
        def loop(**kw):
            torch.cuda.synchronize(); t0 = time.monotonic()
            if method=='msr':
                state = kw['video_state']; n = 16*14*24
                assert state.latent.shape[1]>n
                perm = torch.cat((torch.arange(n,state.latent.shape[1],device=device),
                                  torch.arange(n,device=device)))
                kw['video_state'] = reorder(state,perm)
            video, audio = euler_denoising_loop(**kw)
            if method=='msr': video = reorder(video,torch.argsort(perm))
            torch.cuda.synchronize(); phase_times['denoising_loop_s'] = time.monotonic()-t0
            return video, audio
        emit(status='GENERATING',method=method,shot=shot['title'])
        with torch.inference_mode():
            t0 = time.monotonic(); conditions = encoder(prepare)
            torch.cuda.synchronize(); phase_times['reference_encode_block_s'] = time.monotonic()-t0
            generator = torch.Generator(device=device).manual_seed(shot['seed'])
            t0 = time.monotonic()
            video, audio = stage(denoiser=SimpleDenoiser(video_context,audio_context),
                sigmas=DISTILLED_SIGMAS.to(device),noiser=GaussianNoiser(generator),
                width=768,height=448,frames=121,fps=24.,
                video=ModalitySpec(context=video_context,conditionings=conditions),
                audio=ModalitySpec(context=audio_context),loop=loop)
            torch.cuda.synchronize(); phase_times['diffusion_block_s'] = time.monotonic()-t0
            torch.save(dict(video=video.latent.cpu(),audio=audio.latent.cpu()),
                       destination/'generated_latents.pt')
            t0 = time.monotonic()
            chunks = VideoDecoder(paths['output_video_vae'],dtype,device,registry=registry)(
                video.latent,None,generator,dtype=dtype)
            sound = AudioDecoder(paths['audio_vae'],dtype,device,registry=registry)(audio.latent)
            raw = destination/'raw.mp4'
            encode_video(video=chunks,fps=24.,audio=sound,output_path=str(raw),
                         video_chunks_number=get_video_chunks_number(121,None),crf=19,preset='fast')
            torch.cuda.synchronize(); phase_times['decode_and_encode_block_s'] = time.monotonic()-t0
        generation_s = time.monotonic()-started
        peak = torch.cuda.max_memory_allocated()
        delivered = destination/'delivered.mp4'
        row = dict(status='PASS',case_id=shot['case_id'],method=method,seed=shot['seed'],
            output=str(raw),delivered_output=str(delivered),delivered_frames=shot['delivered_frames'],
            generation_s=generation_s,phases_s=phase_times,conditions=audit,
            prompt_key=shot['prompt_keys'][method],prompt_fingerprint=cache.receipt()['fingerprint'],
            reference_sources=shot['references'],ingredients_sheet=shot['ingredients_sheet'],
            peak_torch_allocated_bytes=peak,steps=8,width=768,height=448,
            media=deliver(raw,delivered,shot['delivered_frames']),
            transition='independent', timeline_trim='shorten ending to common story duration',
            timing_boundary='prompt cache load through raw MP4, including per-block model loading',
            native_port=method=='msr',audio_reference=False)
        save(result_file,row); rows.append(row)
        emit(status='SHOT_COMPLETE',method=method,shot=shot['title'],generation_s=generation_s)
        del video,audio,conditions,video_context,audio_context
        torch.cuda.empty_cache()
    report = assemble(method,rows,story)
    report.update(method_preparation_s=preparation_s,weight_receipt=receipt,
        generation_s=sum(r['generation_s'] for r in rows),
        timing_note='Per-block official model lifecycle; weights reload for each block. '
                    'Offline text preparation, validation and final assembly excluded.')
    save(output_root/'comparison.json',report)


def stop_server(pid):
    command = Path(f'/proc/{pid}/cmdline')
    if not command.exists(): return
    assert str(R/'sol_api_server.py') in command.read_text(), 'PID is not Sol video server'
    os.kill(pid,signal.SIGTERM)
    for _ in range(180):
        if not command.exists(): return
        time.sleep(1)
    raise TimeoutError('Video server did not shut down')


def queue(story):
    env = dict(os.environ,SOL_H3_SPARK_RUNTIME_ROOT=str(R),CUDA_VISIBLE_DEVICES='0',
        CUDA_HOME='/usr/local/cuda',CPATH=str(R/'sysroot/usr/include/python3.12')+':'+str(R/'sysroot/usr/include'),
        PATH='/home/admin/.local/bin:/usr/local/cuda/bin:'+os.environ.get('PATH',''),
        OMP_NUM_THREADS='1',HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',
        TORCHINDUCTOR_COMPILE_THREADS='1',PYTHONPATH=str(R),PYTHONUNBUFFERED='1')
    script = str(R/'run_troy_climax.py')
    rows = []
    lock = None
    try:
        h3(story)
        stop_server(int((D/'ref_server.pid').read_text()))
        lock = (R/'inference.lock').open('a'); fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        captures = [r['capture_dir'] for r in json.loads((D/'h3/comparison.json').read_text())['clips']]
        commands = [
            ('native_h3',[str(R/'stage1-env/bin/python'),str(R/'decode_h3_identity_baseline.py'),
                '--captures',*captures,'--output',str(D/'h3_native')]),
            ('caches',[str(R/'stage2-env/bin/python'),script,'--phase','caches']),
            ('refiners',[str(R/'stage2-env/bin/torchrun'),'--standalone','--nproc-per-node=1',
                script,'--phase','refiners']),
            ('ingredients',[str(R/'stage2-env/bin/python'),script,'--phase','ingredients']),
            ('msr',[str(R/'stage2-env/bin/python'),script,'--phase','msr']),
        ]
        for name, command in commands:
            emit(status='PHASE_START',phase=name); started = time.monotonic()
            with (D/(name+'.log')).open('ab') as log:
                proc = subprocess.run(command,env=env,stdout=log,stderr=log)
            row = dict(phase=name,exit_code=proc.returncode,elapsed_s=time.monotonic()-started)
            rows.append(row); save(D/'queue_results.json',rows); emit(**row)
            if proc.returncode: raise RuntimeError(f'{name} failed; inspect saved log')
        save(D/'completed.json',dict(status='PASS',phases=rows))
    finally:
        if lock is not None:
            fcntl.flock(lock,fcntl.LOCK_UN); lock.close()
        # Only restore once this queue's Ref2VA server has yielded ownership.
        pid = int((D/'ref_server.pid').read_text())
        if not Path(f'/proc/{pid}/cmdline').exists():
            with (D/'restored_fl_server.log').open('ab') as log:
                server = subprocess.Popen([str(R/'start_sol_server.sh')],env=dict(env,
                    SOL_TASK='fl2va',SOL_PATHS_FILE=str(R/'paths.json')),stdin=subprocess.DEVNULL,
                    stdout=log,stderr=log,start_new_session=True)
            (D/'restored_fl_server.pid').write_text(str(server.pid))
            emit(status='FL_VIDEO_SERVER_RESTARTING',pid=server.pid)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--phase',choices=['queue','h3','caches','refiners','ingredients','msr'],required=True)
    args = parser.parse_args()
    story = json.loads((D/'story.json').read_text())
    if args.phase=='queue': queue(story)
    elif args.phase=='h3': h3(story)
    elif args.phase=='caches': caches()
    elif args.phase=='refiners': refiner(story)
    else: native(story,args.phase)


if __name__=='__main__':
    main()
