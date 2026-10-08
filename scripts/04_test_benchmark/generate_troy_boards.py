#!/usr/bin/env python3
"""Create two coherent Trojan-Horse duel boards with the installed Qwen Turbo."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    locks = []
    for name in ('/home/admin/sol-spark-runtime/inference.lock',
                 '/home/admin/qwen-image-2.1-runtime/inference.lock'):
        lock = open(name, 'a')
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        locks.append(lock)
    os.environ.update(HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1')
    import torch
    from PIL import ImageStat
    from diffusers import QwenImage21Pipeline, FlowMatchEulerDiscreteScheduler
    args.output.mkdir(parents=True, exist_ok=False)
    started = time.monotonic()
    pipe = QwenImage21Pipeline.from_pretrained('/home/admin/models_cache/Qwen-Image-2.1',
        dtype=torch.bfloat16, local_files_only=True)
    pipe.load_lora_weights('/home/admin/qwen-image-2.1-runtime/turbo',
        weight_name='Qwen-Image-2.1-viggle-turbo-v0.2.1-6step-lora-r256.safetensors', local_files_only=True)
    pipe.scheduler = FlowMatchEulerDiscreteScheduler.from_config(dict(pipe.scheduler.config), shift_terminal=None)
    pipe.to('cuda')
    style = ('A single live-action cinema frame, an imagined 1970s Shaw Brothers swordplay film set in ancient Troy. '
        'Handcrafted studio courtyard set, theatrical hard amber key light, deep cyan night shadows, '
        'rich red and gold colors, anamorphic widescreen composition, subtle 35mm film grain. '
        'Exactly two adult Greek warriors: left, a bearded man with short dark hair, red cloak and bronze cuirass; '
        'right, a clean-shaven man with curly black hair, blue cloak and bronze cuirass. '
        'Both have leather sandals, round bronze shields and short bronze swords. '
        'A huge unmistakable wooden Trojan horse with four wooden legs stands behind them. '
        'Ancient stone walls, two flaming braziers, sand floor. No modern objects, no writing, no logos. '
        'Non-graphic choreographed duel, no wounds or blood. ')
    prompts = [style + 'Wide establishing shot, both warriors shown full body facing each other, '
        'swords raised but separated, clear silhouettes, believable hands, horse clearly visible. '
        'The red warrior is in the left foreground and the blue warrior is in the right midground.',
        'Use the reference frame to preserve the exact two warriors, costumes, wooden Trojan horse and set. '
        + style + 'A new low-angle medium-wide camera position from the other side of the courtyard, '
        'the red-cloaked warrior on the right parries the blue-cloaked warrior on the left. '
        'Both full bodies and swords visible. Dynamic readable stage combat pose.']
    records = []
    board = None
    for i, prompt in enumerate(prompts, 1):
        t0 = time.monotonic()
        options = dict(prompt=prompt, width=1344, height=768, num_inference_steps=6,
            sigmas=[1., .9375, .875, .75, .5, .25], true_cfg_scale=1.,
            generator=torch.Generator('cuda').manual_seed(2026100300+i))
        if board is not None:
            options['image'] = [board]
        board = pipe(**options).images[0].convert('RGB')
        if max(ImageStat.Stat(board).stddev) < 5:
            raise RuntimeError('Uniform board')
        path = args.output / f'board_{i:02d}.png'
        board.save(path)
        row = dict(path=str(path), prompt=prompt, seconds=time.monotonic()-t0)
        records.append(row)
        print(json.dumps(row), flush=True)
    (args.output / 'boards.json').write_text(json.dumps(dict(total_s=time.monotonic()-started, boards=records), indent=2))


if __name__ == '__main__':
    main()
