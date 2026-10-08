#!/usr/bin/env python3
"""Register an unchanged local copy of a self-hosted Qwen output and metadata."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('name', help='Output stem, e.g. s15_qwen21_v1')
    args = parser.parse_args()
    q = Path(__file__).resolve().parent
    root = q.parent
    metadata = json.loads((q / 'outputs' / (args.name + '.json')).read_text())
    image = q / 'outputs' / (args.name + '.png')
    assert hashlib.sha256(image.read_bytes()).hexdigest() == metadata['sha256']
    references = metadata['workspace_reference_files']
    assert [hashlib.sha256((root / f).read_bytes()).hexdigest() for f in references] == metadata['reference_sha256']
    row = dict(kind='shot', id=metadata['id'], title=metadata['title'],
        frame_file='storyboard_v2/frames/' + image.name,
        prompt_file=f"storyboard_v2/prompts/{args.name}.txt",
        source=str(image), remote_source=metadata['source'], references=references,
        generation_wall_s=metadata['seconds'], status='generated_pending_manual_review',
        tool='self-hosted Qwen Image 2.1', model=metadata['model'], provider=metadata['provider'],
        steps=metadata['steps'], seed=metadata['seed'], backend=metadata['backend'],
        precision=metadata['precision'], lora=metadata['lora'],
        metadata_file='qwen21/outputs/' + args.name + '.json')
    assert (root / row['prompt_file']).read_text().strip() == metadata['prompt']
    subprocess.run([sys.executable, str(root / 'storyboard_v2/register_output.py'),
                    json.dumps(row, ensure_ascii=False)], check=True)


if __name__ == '__main__':
    main()
