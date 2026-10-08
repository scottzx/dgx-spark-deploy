"""ARM64 CPU decoding adapter. Frames are genuinely decoded using OpenCV, audio using FFmpeg."""
import subprocess
import sys
import types
import cv2
import numpy as np

_bridge = 'native'

class NDArray:
    def __init__(self, value): self.value = np.asarray(value)
    def asnumpy(self): return self.value
    def __getitem__(self, key): return NDArray(self.value[key])
    @property
    def shape(self): return self.value.shape

def _out(value):
    if _bridge == 'torch':
        import torch
        return torch.from_numpy(np.asarray(value))
    return NDArray(value)

def cpu(index=0): return index

class VideoReader:
    def __init__(self, uri, ctx=None, width=-1, height=-1, num_threads=0, fault_tol=-1, **kwargs):
        cap = cv2.VideoCapture(str(uri))
        self.fps = cap.get(cv2.CAP_PROP_FPS)
        self.frames = []
        while True:
            ok, frame = cap.read()
            if not ok: break
            frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            if width > 0 and height > 0: frame = cv2.resize(frame, (width, height))
            self.frames.append(frame)
        cap.release()
        if not self.frames or self.fps <= 0: raise RuntimeError(f'Cannot decode video: {uri}')
        self._num_frame = len(self.frames)
        self.position = 0
    def __len__(self): return len(self.frames)
    def __getitem__(self, key): return _out(self.frames[key])
    def get_batch(self, indices): return _out(np.stack([self.frames[int(i)] for i in indices]))
    def get_avg_fps(self): return self.fps
    def get_frame_timestamp(self, index): return np.array([index/self.fps, (index+1)/self.fps])
    def seek(self, index): self.position = index
    def seek_accurate(self, index): self.seek(index)
    def next(self):
        value = self[self.position]
        self.position += 1
        return value

class AudioReader:
    def __init__(self, uri, ctx=None, sample_rate=16000, mono=True, **kwargs):
        self.sample_rate = sample_rate
        result = subprocess.run(['ffmpeg', '-v', 'error', '-i', str(uri), '-f', 'f32le', '-ac', '1', '-ar', str(sample_rate), '-'], capture_output=True, check=True)
        self.data = np.frombuffer(result.stdout, dtype=np.float32).copy()[None, :]
        self._num_samples = self.data.shape[1]
    def __getitem__(self, key): return NDArray(self.data[:, key])
    def __len__(self): return self._num_samples
    def _time_to_sample(self, t): return int(t*self.sample_rate)
    def add_padding(self): pass

def set_bridge(name):
    global _bridge
    _bridge = name

bridge = types.ModuleType('decord.bridge')
bridge.set_bridge = set_bridge
bridge.bridge_out = lambda value: value
ndarray = types.ModuleType('decord.ndarray')
ndarray.cpu = cpu
ndarray.array = NDArray
for name, module in [('bridge', bridge), ('ndarray', ndarray)]: sys.modules['decord.' + name] = module
for name, symbol in [('video_reader', VideoReader), ('audio_reader', AudioReader)]:
    module = types.ModuleType('decord.' + name)
    setattr(module, symbol.__name__, symbol)
    sys.modules['decord.' + name] = module
