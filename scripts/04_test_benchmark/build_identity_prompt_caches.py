#!/usr/bin/env python3
"""Encode task-specific experimental prompts with the existing native INT8 encoder."""
import json
from pathlib import Path
import sys
sys.path.insert(0,'/home/admin/sol-h3-spark/models/minimax_h3/Sol-H3-Spark')
sys.path.insert(0,'/home/admin/sol-spark-runtime/dependencies/offline-context')
paths=json.loads(Path('/home/admin/sol-spark-runtime/paths.json').read_text())
sys.path[:0]=[str(Path(paths['ltx_root'])/'packages'/p/'src') for p in ('ltx-core','ltx-pipelines','ltx-kernels')]
from runtime import cache_builder
root=Path('/home/admin/sol-spark-runtime/identity_tests_20261003')
for name,prompt in json.loads((root/'ltx_prompts.json').read_text()).items():
 cache_builder.FIXED_PROMPT=prompt
 output=root/'prompt_caches'/(name+'.pt')
 if output.exists():
  print(json.dumps(dict(status='EXISTS',cache=str(output))),flush=True)
  continue
 print(json.dumps(cache_builder.build_cache(paths,output)),flush=True)
