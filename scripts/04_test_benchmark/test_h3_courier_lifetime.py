"""CUDA regression test for mapped H3 weights freed before compute finishes.

Run with the H3 venv on the GPU server. Optional argument selects the source
file, allowing the same test to verify the pre-fix backup fails.
"""
import ast
import queue
import sys
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

import torch

DEFAULT_SOURCE = '/home/admin/MiniMax-H3-MultiGPU-Lightning/sglang/python/sglang/multimodal_gen/runtime/managers/memory_managers/layerwise_offload.py'
source = Path(sys.argv[1] if len(sys.argv) > 1 else DEFAULT_SOURCE)
tree = ast.parse(source.read_text())
courier_node = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'MappedLayerCourier')
manager_node = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'LayerwiseOffloadManager')
collect_node = next(n for n in manager_node.body if isinstance(n, ast.FunctionDef) and n.name == '_collect_mapped_layer')
# Exercise the actual production methods without importing the entire server.
exec(compile(ast.Module(body=[courier_node, collect_node], type_ignores=[]), str(source), 'exec'))

class Harness:
    _collect_mapped_layer = _collect_mapped_layer

    def __init__(self, courier):
        self._mapped_courier = courier
        self._courier_inflight = set()
        self._gpu_layers = set()
        self.weight = torch.nn.Parameter(torch.empty(0), requires_grad=False)

    def get_target_with_name(self, name):
        return self.weight

    def _wrap_for_target(self, target, tensor):
        return tensor

def main():
    n, count = 262144, 12
    weights = {i: {'w': torch.full((n,), float(i + 1))} for i in range(count)}
    metadata = {i: {'w': {'shape': (n,), 'dtype': torch.float32}} for i in weights}
    courier = MappedLayerCourier(mapped_cpu_weights=weights, weight_metadata=metadata,
        device=torch.device('cuda:0'), pin_slots=True)
    manager = Harness(courier)
    outputs = []
    try:
        for i in range(count):
            courier.submit(i)
            manager._courier_inflight.add(i)
            manager._collect_mapped_layer(i)
            # Queue delayed compute, then mimic release_layer immediately
            # dropping the last Python reference to the source allocation.
            torch.cuda._sleep(50_000_000)
            outputs.append(manager.weight.sum())
            manager.weight.data = torch.empty(0, device='cuda')
        torch.cuda.synchronize()
        got = [v.item() / n for v in outputs]
        expected = list(range(1, count + 1))
        print({'source': str(source), 'expected': expected, 'actual': got}, flush=True)
        assert got == expected, 'CUDA weight allocation reused before queued compute completed'
        print('PASS: all 12 asynchronous weight transfers preserve their values', flush=True)
    finally:
        torch.cuda.synchronize()
        courier.close()

if __name__ == '__main__':
    main()
