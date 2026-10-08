"""FlashAttention-2 call interface backed by PyTorch SDPA on GB10 ARM64.

Dense attention, per-example variable lengths, scale, and causal masks are
preserved. This adapter does not claim the authors' optimized kernel speeds.
"""
import importlib.machinery
import sys
import types
import torch
from torch.nn import functional as F

def flash_attn_func(q, k, v, dropout_p=0.0, softmax_scale=None, causal=False,
                    window_size=(-1, -1), alibi_slopes=None, deterministic=False,
                    return_attn_probs=False, **kwargs):
    if window_size != (-1, -1) or alibi_slopes is not None or return_attn_probs:
        raise NotImplementedError('Benchmark adapter supports dense attention without ALiBi or probability output')
    return F.scaled_dot_product_attention(q.transpose(1, 2), k.transpose(1, 2), v.transpose(1, 2),
                                          dropout_p=dropout_p, scale=softmax_scale,
                                          is_causal=causal).transpose(1, 2).contiguous()

def flash_attn_varlen_func(q, k, v, cu_seqlens_q, cu_seqlens_k, max_seqlen_q, max_seqlen_k,
                           dropout_p=0.0, softmax_scale=None, causal=False, **kwargs):
    qs, ks = cu_seqlens_q.tolist(), cu_seqlens_k.tolist()
    chunks = []
    for i in range(len(qs)-1):
        chunks.append(flash_attn_func(q[qs[i]:qs[i+1]][None], k[ks[i]:ks[i+1]][None],
                                     v[ks[i]:ks[i+1]][None], dropout_p=dropout_p,
                                     softmax_scale=softmax_scale, causal=causal, **kwargs)[0])
    return torch.cat(chunks, dim=0)

def install(with_xformers=False):
    module = types.ModuleType('flash_attn')
    module.__spec__ = importlib.machinery.ModuleSpec('flash_attn', loader=None, is_package=True)
    module.__path__ = []
    module.__version__ = '2.7.4+sdpa.benchmark'
    module.flash_attn_func = flash_attn_func
    module.flash_attn_varlen_func = flash_attn_varlen_func
    sys.modules['flash_attn'] = module
    sys.modules['flash_attn.flash_attn_interface'] = module
    if with_xformers:
        # InfiniteTalk's single-person, single-GPU cross-attention has no bias.
        # Reject unsupported bias objects instead of silently dropping masks.
        xformers = types.ModuleType('xformers')
        xformers.__spec__ = importlib.machinery.ModuleSpec('xformers', loader=None, is_package=True)
        xformers.__path__ = []
        xformers.__version__ = '0.0.29+sdpa.benchmark'
        ops = types.ModuleType('xformers.ops')
        def memory_efficient_attention(query, key, value, attn_bias=None, p=0.0, scale=None, op=None):
            if attn_bias is not None:
                raise NotImplementedError('Single-GPU benchmark does not support xFormers bias objects')
            return flash_attn_func(query, key, value, dropout_p=p, softmax_scale=scale)
        ops.memory_efficient_attention = memory_efficient_attention
        xformers.ops = ops
        sys.modules['xformers'] = xformers
        sys.modules['xformers.ops'] = ops
