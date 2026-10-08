#!/usr/bin/env python3
"""Install the reviewed overlay on Spark, preserving and checking local changes."""
import argparse
import datetime
import hashlib
import json
from pathlib import Path
import shutil


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--overlay', type=Path, required=True)
    parser.add_argument('--package', type=Path, default=Path('/home/admin/sol-h3-spark/models/minimax_h3/Sol-H3-Spark'))
    parser.add_argument('--runtime', type=Path, default=Path('/home/admin/sol-spark-runtime'))
    args = parser.parse_args()
    manifest = json.loads((args.overlay/'overlay_manifest.json').read_text())
    targets = {}
    for name, row in manifest.items():
        source = args.overlay/name
        if digest(source) != row['after_sha256']:
            raise SystemExit(f'Overlay hash mismatch: {name}')
        target = (args.runtime if name == 'sol_api_server.py' else args.package)/name
        actual = digest(target)
        if actual not in (row['before_sha256'], row['after_sha256'], *row.get('compatible_before_sha256', [])):
            raise SystemExit(f'Server file differs from the reviewed baseline: {target}')
        targets[name] = target
    stamp = datetime.datetime.now().strftime('%Y%m%d-%H%M%S')
    backup = args.runtime/'backups'/f'workflows_{stamp}'
    backup.mkdir(parents=True, exist_ok=False)
    for name, target in targets.items():
        if digest(target) == manifest[name]['after_sha256']:
            continue
        if target.is_file():
            saved = backup/name
            saved.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(target, saved)
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_suffix(target.suffix+'.workflow-new')
        shutil.copy2(args.overlay/name, temporary)
        temporary.replace(target)
    (backup/'manifest.json').write_text(json.dumps(manifest, indent=2)+'\n')
    print(json.dumps(dict(status='PASS', backup=str(backup), files=list(targets))))


if __name__ == '__main__':
    main()
