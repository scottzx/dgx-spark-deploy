#!/usr/bin/env python3
"""Keep the small ARM64/single-GPU compatibility changes reviewable as a diff."""
import difflib
from pathlib import Path
root=Path('/home/admin/digital-human-runtime/sources')
changes=[]
def edit(relative,old,new):
    p=root/relative;before=p.read_text()
    if old not in before:
        if new in before:return
        raise ValueError(f'Expected source text missing in {p}')
    after=before.replace(old,new,1);p.write_text(after)
    changes.extend(difflib.unified_diff(before.splitlines(True),after.splitlines(True),fromfile=str(relative),tofile=str(relative)))
edit(Path('SoulX-FlashHead/flash_head/src/modules/flash_head_model.py'),
     'from xfuser.core.distributed import (\n    get_sequence_parallel_rank,\n    get_sequence_parallel_world_size,\n    get_sp_group,\n)\nfrom xfuser.core.long_ctx_attention import xFuserLongContextAttention',
     'try:\n    from xfuser.core.distributed import (get_sequence_parallel_rank, get_sequence_parallel_world_size, get_sp_group)\n    from xfuser.core.long_ctx_attention import xFuserLongContextAttention\nexcept ImportError:\n    # Single-GPU use_usp=False never calls these distributed branches.\n    get_sequence_parallel_rank = get_sequence_parallel_world_size = get_sp_group = None\n    xFuserLongContextAttention = None')
edit(Path('SoulX-FlashHead/flash_head/src/pipeline/flash_head_pipeline.py'),
     'from flash_head.utils.facecrop import process_image',
     '# Face cropping is optional; supplied reference has already been framed.')
edit(Path('SoulX-FlashHead/flash_head/src/pipeline/flash_head_pipeline.py'),
     'if use_face_crop:\n            try:',
     'if use_face_crop:\n            from flash_head.utils.facecrop import process_image\n            try:')
edit(Path('SoulX-FlashHead/flash_head/src/pipeline/flash_head_pipeline.py'),
     'COMPILE_MODEL = True\nCOMPILE_VAE = True',
     'COMPILE_MODEL = False\nCOMPILE_VAE = False  # Eager SDPA baseline; benchmark this configuration explicitly.')
edit(Path('echomimic_v3/infer_flash.py'),'import decord',' # decord is unused by this image + audio entry point')
receipt=root.parent/'compatibility.patch'
if changes:
    with receipt.open('a') as f:f.writelines(changes)
print('Compatibility changes saved to',receipt)
