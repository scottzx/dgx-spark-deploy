#!/usr/bin/env python3
"""Freeze one shared Qwen first frame and a 2-model, 2-prompt, 3-seed trial."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parent
REMOTE = '/home/admin/sol-spark-runtime/troy_combat_prompt_ab_20261006'

def sha(p):
    with Path(p).open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()

def fingerprint(x):
    return hashlib.sha256(json.dumps(x, sort_keys=True, separators=(',', ':')).encode()).hexdigest()

def main():
    source = ROOT.parent/'video_msr_v2/keyframes/S15_start.png'
    original = ROOT/'inputs/qwen_original.png'
    first = ROOT/'inputs/first.png'
    shutil.copy2(source, original)
    # Technical resampling only; no new semantic image generation or image edit.
    subprocess.run(['ffmpeg','-y','-v','error','-i',str(original),'-vf',
                    'scale=672:384:force_original_aspect_ratio=increase,crop=672:384',
                    '-frames:v','1',str(first)], check=True)
    scene = ('Live-action, cinematic 1970s Shaw Brothers historical Troy. A static full-body medium-wide shot '
             'continues from the provided first frame, in front of a closed wooden double gate at night, '
             'lit by warm amber torches and cool moonlight. Foreground left is Odysseus with short dark wavy hair, '
             'trimmed beard, indigo cloak, a sword in his right hand and an empty left hand. Foreground right is '
             'the Trojan guard with a pointed bronze helmet, ochre tunic and rust cloak, a spear in his right hand '
             'and a round shield in his left hand. The same four background soldiers remain behind the foreground '
             'duel as two opposed pairs striking and blocking. The six people retain their identities, equipment '
             'and original weapon hands; the gate remains closed. ')
    actions = {
        'old': ('The guard thrusts once; Odysseus parries the spear upward with his sword. '
                'The guard recoils half a step to the right.'),
        'new': ('The foreground duel begins immediately at normal real-time speed. The guard plants his lead foot '
                'and lunges, driving the spear toward Odysseus\' chest. Odysseus steps diagonally aside and strikes '
                'the spear shaft upward with his sword, visibly diverting the spear point past his shoulder. '
                'After the brief contact the weapons separate: the guard pulls his spear back while Odysseus '
                'steps forward and delivers a diagonal sword cut toward the guard\'s upper body. The guard raises '
                'his left shield into the sword path; the blade hits the shield, the shield and his shoulder jolt '
                'back together, and his rear foot steps back to catch his weight. Odysseus withdraws the sword '
                'from the shield as the guard lowers the shield slightly and drives a second spear thrust. '
                'Odysseus again slips sideways and knocks the shaft away. Their knees, hips and feet drive '
                'each attack and recovery, and they keep moving after each brief contact.')
    }
    sound = ('Torch crackle under synchronized metal-on-wood clashes, spear-shaft knocks, armor rattles, '
             'quick scraping footsteps and strained breathing. No dialogue or singing.')
    prompts = {}
    for model in ('ltx','h3'):
        for variant, action in actions.items():
            visual = scene+action+' No blood, visible wounds or captions.'
            if model == 'h3':
                # This fixed image-alignment line is the official I2VA format.
                prompt = ('For the target video, at 0.00 seconds into the target video, <Picture 1> (from [Shot 1]) '
                          'is fully referenced.\n\nintegrated_multimodal_description: [Shot 1] '+visual+
                          '\n\noverall_soundscape: '+sound+'\n\nnon_diegetic_music: N/A')
            else:
                prompt = visual+' '+sound+' No background music.'
            key = model+'_'+variant
            prompts[key] = prompt
            (ROOT/'prompts'/f'{key}.txt').write_text(prompt+'\n')
    jobs = []
    # Pair prompts within seed; alternate order to reduce first-call order bias.
    for model in ('h3','ltx'):
        for n, seed in enumerate((2026100601,2026100602,2026100603)):
            for variant in (('old','new') if n%2==0 else ('new','old')):
                job = dict(id=f'combat_ab_{model}_{variant}_{seed}',model=model,variant=variant,
                           seed=seed,prompt=prompts[model+'_'+variant],
                           first_frame='inputs/first.png',first_frame_sha256=sha(first),duration_s=5,
                           delivered_frames=120,fps=24,size=[672,384],conditioning='first_frame_only',
                           inference='local W8A8 FastH3-VSA FL2VA' if model=='h3' else 'local BF16 LTX-2.5 dev + distilled LoRA, 8-step',
                           steps_profile=5 if model=='h3' else 8,
                           msr=False,combat_lora=False,last_frame=False)
                job['input_fingerprint'] = fingerprint(job)
                jobs.append(job)
    manifest = dict(version=1,remote_root=REMOTE,jobs=jobs,prompts=prompts,
                    original_first_frame=str(source),original_sha256=sha(original),
                    first_frame_sha256=sha(first),resampling='center fit/crop to672x384',
                    scope='Within each model only foreground choreography text changes; model-native formatting is fixed. Both use the same first frame, size, duration and delivery. No MSR, last frame or combat LoRA.',
                    limits=['H3 is the installed W8A8/VSA accelerated recipe, not official full BF16 H3.',
                            'LTX uses the installed 8-step distilled recipe. Cross-model conclusions are deployment-specific.',
                            'Shared seed numbers do not imply identical random noise across architectures.',
                            'The frame contains six actors; quality scoring focuses on the foreground duel.',
                            'Old means the original foreground action wording, wrapped with the shared scene/native format; it is not a replay of the entire old MSR prompt.'])
    manifest['fingerprint'] = fingerprint(manifest)
    (ROOT/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(dict(jobs=len(jobs),fingerprint=manifest['fingerprint'],first_frame_sha256=sha(first))))

if __name__=='__main__':main()
