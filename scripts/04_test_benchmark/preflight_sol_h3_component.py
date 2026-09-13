#!/usr/bin/env python3
"""Run an official Qwen or H3 worker before full Sol-H3-Spark acceptance."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('component', choices=['qwen', 'stage1'])
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--conditioning', type=Path)
    args = parser.parse_args()
    if args.component == 'stage1' and args.conditioning is None:
        parser.error('stage1 requires --conditioning from the Qwen preflight')
    runtime = Path('/home/admin/sol-spark-runtime')
    package = Path('/home/admin/sol-h3-spark/models/minimax_h3/Sol-H3-Spark')
    sys.path.insert(0, str(package))
    from runtime.config import load_recipe
    from runtime.pipeline import Worker

    os.environ.update(
        SOL_H3_SPARK_RUNTIME_ROOT=str(runtime),
        SOL_H3_SPARK_QWEN_IMAGE='sol-h3-spark-qwen',
        CUDA_HOME='/usr/local/cuda', CUDA_VISIBLE_DEVICES='0',
        CPATH=f'{runtime}/sysroot/usr/include/python3.12:{runtime}/sysroot/usr/include',
    )
    os.environ['PATH'] = f'/home/admin/.local/bin:/usr/local/cuda/bin:{os.environ["PATH"]}'
    paths = json.loads((runtime / 'component-paths.json').read_text())
    lock_handle = (runtime / 'inference.lock').open('a')
    fcntl.flock(lock_handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    root = args.output_dir.resolve()
    root.mkdir(parents=True, exist_ok=False)
    case = {'case_id': 'component_preflight', 'task': 't2va', 'seed': 42,
            'prompt': 'A golden retriever walks slowly through a sunny green park. '
                      'A steady cinematic camera follows the dog, natural light, '
                      'clear detailed fur, gentle breeze and birds singing.'}
    worker = None
    try:
        worker = Worker(args.component, root / 'worker', paths, load_recipe())
        if args.component == 'qwen':
            result = worker.call(case=case, output_root=str(root / 'conditioning'))
        else:
            result = worker.call(case=case, conditioning_path=str(args.conditioning.resolve(strict=True)),
                                 outputdir=str(root / 'draft'))
        (root / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
        print(json.dumps(result, indent=2), flush=True)
    finally:
        if worker is not None:
            worker.close()
        lock_handle.close()


if __name__ == '__main__':
    main()
