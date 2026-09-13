#!/usr/bin/env python3
"""Fetch pinned Sol-H3-Spark sources/weights; run on the Spark host."""
import argparse
import concurrent.futures
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import urllib.parse
import urllib.request

ROOT = Path('/home/admin/sol-spark-runtime')
PACKAGE = Path('/home/admin/sol-h3-spark/models/minimax_h3/Sol-H3-Spark')
sys.path.insert(0, str(PACKAGE))


def sources():
    manifest = json.loads((PACKAGE / 'configs/dependencies.json').read_text())
    def fetch(entry):
        target = ROOT / 'sources' / entry['directory']
        target.mkdir(parents=True, exist_ok=True)
        def git(*args, capture=False):
            return subprocess.run(['git', '-C', str(target), *args], check=True,
                                  text=True, capture_output=capture)
        if not (target / '.git').exists():
            git('init')
            git('remote', 'add', 'origin', entry['repository'])
        head = subprocess.run(['git', '-C', str(target), 'rev-parse', 'HEAD'],
                              capture_output=True, text=True).stdout.strip()
        if head != entry['revision']:
            if head and head != 'HEAD':
                raise ValueError(f'Preserving unexpected checkout: {target}')
            wanted = {
                'fastvideo_root': ['fastvideo', 'fastvideo-kernel', 'examples/inference/basic'],
                'fa4_source_root': ['flash_attn'],
                'comfy_root': ['comfy', 'comfy_extras', 'comfy_api', 'comfy_execution', 'app', 'utils', 'api_server'],
                'h3_upscaler_root': ['nodes'],
            }.get(entry['key'])
            if wanted:
                git('sparse-checkout', 'init', '--cone')
                git('sparse-checkout', 'set', *wanted)
            git('config', 'http.version', 'HTTP/1.1')
            present = subprocess.run(['git', '-C', str(target), 'cat-file', '-t', entry['revision']],
                                     capture_output=True, text=True)
            if present.returncode or present.stdout.strip() != 'commit':
                git('fetch', '--depth', '1', '--filter=blob:none', 'origin', entry['revision'])
            git('checkout', '--detach', entry['revision'])
        return entry['key'] + ' ready ' + entry['revision']
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        for result in pool.map(fetch, manifest['sources']):
            print(result, flush=True)


def weights(include_gated=False):
    from download_checkpoints import selected_entries, checkpoint_paths, sha256
    from huggingface_hub import HfApi, hf_hub_download, snapshot_download
    import fnmatch
    manifest = json.loads((PACKAGE / 'configs/checkpoints.json').read_text())
    output = ROOT / 'checkpoints'
    output.mkdir(exist_ok=True)
    entries = list(selected_entries(manifest, task='t2va', include_offline=True))
    if not include_gated:
        entries = [e for e in entries if not e.get('gated')]
    def fetch(entry):
        target = output / entry['directory']
        target.mkdir(exist_ok=True)
        kwargs = dict(repo_id=entry['repo_id'], revision=entry['revision'], local_dir=target)
        if entry['key'] == 'h3_model':
            info = HfApi().model_info(entry['repo_id'], revision=entry['revision'], files_metadata=True)
            reused = []
            for item in info.siblings:
                name = item.rfilename
                if not any(fnmatch.fnmatch(name, p) for p in entry['allow_patterns']):
                    continue
                old = Path('/home/admin/models_cache/MiniMax-H3') / name
                new = target / name
                if old.is_file() and item.lfs and old.stat().st_size == item.size:
                    expected = item.lfs.sha256
                    if sha256(old) == expected:
                        new.parent.mkdir(parents=True, exist_ok=True)
                        if not new.exists():
                            os.link(old, new)
                        reused.append(name)
                        print('verified/reused', name, flush=True)
            snapshot_download(**kwargs, allow_patterns=entry['allow_patterns'],
                              ignore_patterns=reused, max_workers=2)
        elif entry['kind'] == 'snapshot':
            snapshot_download(**kwargs, allow_patterns=entry['allow_patterns'], max_workers=2)
            for item in entry.get('verify_files', []):
                if sha256(target / item['filename']) != item['sha256']:
                    raise ValueError('Hash mismatch: ' + entry['key'])
        else:
            file = target / entry['filename']
            if not file.exists() or file.stat().st_size != entry['bytes'] or sha256(file) != entry['sha256']:
                file = Path(hf_hub_download(**kwargs, filename=entry['filename']))
            if file.stat().st_size != entry['bytes'] or sha256(file) != entry['sha256']:
                raise ValueError('Hash mismatch: ' + entry['key'])
        receipt = ROOT / 'receipts'
        receipt.mkdir(exist_ok=True)
        (receipt / (entry['key'] + '.json')).write_text(json.dumps(entry, indent=2) + '\n')
        return entry['key'] + ' verified'
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        for result in pool.map(fetch, entries):
            print(result, flush=True)
    (output / 'checkpoint-paths.json').write_text(json.dumps(checkpoint_paths(output), indent=2) + '\n')


def modelscope(file_bandwidth='3M'):
    """Use publicly accessible matching ModelScope files, verifying full hashes."""
    from download_checkpoints import selected_entries, checkpoint_paths, sha256
    manifest = json.loads((PACKAGE / 'configs/checkpoints.json').read_text())
    output = ROOT / 'checkpoints'
    entries = [e for e in selected_entries(manifest, task='t2va', include_offline=True)
               if e['key'] != 'h3_model']
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    def fetch(entry):
        url = 'https://modelscope.cn/api/v1/models/' + entry['repo_id'] + '/repo/files?Revision=master&Recursive=true'
        with opener.open(url, timeout=30) as response:
            metadata = json.load(response)
        indexed = {f['Path']: f for f in metadata['Data']['Files'] if f['Type'] == 'blob'}
        names = [entry['filename']] if entry['kind'] == 'file' else entry['allow_patterns']
        for name in names:
            item = indexed[name]
            expected = entry if entry['kind'] == 'file' else next(
                (f for f in entry.get('verify_files', []) if f['filename'] == name), None)
            if expected and (item['Sha256'] != expected['sha256'] or item['Size'] != expected['bytes']):
                raise ValueError('Mirror metadata does not match NVIDIA: ' + name)
            target = output / entry['directory'] / name
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists() and sha256(target) == item['Sha256']:
                print('Already verified:', name, flush=True)
                continue
            partial = target.with_suffix(target.suffix + '.ms-part')
            download = ('https://modelscope.cn/models/' + entry['repo_id'] + '/resolve/'
                        + item['Revision'] + '/' + urllib.parse.quote(name, safe='/'))
            print('Downloading ModelScope:', name, item['Size'], flush=True)
            aria = ROOT / 'aria2/usr/bin/aria2c'
            env = os.environ.copy()
            for key in list(env):
                if key.lower().endswith('_proxy'):
                    env.pop(key)
            if aria.exists():
                env['LD_LIBRARY_PATH'] = str(ROOT / 'aria2/usr/lib/aarch64-linux-gnu')
                command = [str(aria), '--continue=true', '--auto-file-renaming=false',
                           '--file-allocation=none', '--max-connection-per-server=8', '--split=8',
                           '--min-split-size=64M', '--max-tries=10', '--retry-wait=3',
                           '--max-overall-download-limit=' + file_bandwidth, '--show-console-readout=false',
                           '--summary-interval=60', '--console-log-level=warn',
                           '--dir=' + str(partial.parent), '--out=' + partial.name, download]
            else:
                command = ['curl', '--noproxy', '*', '-fL', '--limit-rate', file_bandwidth,
                           '--retry', '10', '--retry-delay', '3',
                           '--connect-timeout', '20', '-C', '-', '-o', str(partial), download]
            with (target.parent / (target.name + '.download.log')).open('a') as log:
                subprocess.run(command, check=True, env=env, stdout=log, stderr=log)
            if partial.stat().st_size != item['Size'] or sha256(partial) != item['Sha256']:
                raise ValueError('Downloaded file failed hash verification: ' + name)
            partial.replace(target)
            print('SHA256 verified:', name, flush=True)
        receipt = ROOT / 'receipts'
        receipt.mkdir(exist_ok=True)
        (receipt / (entry['key'] + '.json')).write_text(json.dumps(
            {'nvidia_manifest': entry, 'provider': 'modelscope', 'files': [indexed[n] for n in names]}, indent=2) + '\n')
        return entry['key'] + ' verified from ModelScope'
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        for result in pool.map(fetch, entries):
            print(result, flush=True)
    (output / 'checkpoint-paths.json').write_text(json.dumps(checkpoint_paths(output), indent=2) + '\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['sources', 'weights', 'modelscope'])
    parser.add_argument('--include-gated', action='store_true')
    parser.add_argument('--file-bandwidth', default='3M',
                        help='ModelScope per-file download limit; default 3M for three workers')
    args = parser.parse_args()
    if args.action == 'sources':
        sources()
    elif args.action == 'modelscope':
        modelscope(args.file_bandwidth)
    else:
        weights(args.include_gated)
