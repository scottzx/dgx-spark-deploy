from pathlib import Path
import os,subprocess,json,time
r=Path('/home/admin/sol-spark-runtime'); uv=str(Path('/home/admin/.local/bin/uv'))
env=os.environ.copy(); env['UV_HTTP_TIMEOUT']='120'; env['UV_LOCK_TIMEOUT']='3600'
def run(stage,args):
 print(time.strftime('%F %T'),stage,args,flush=True)
 subprocess.run([uv,'pip','install','--python',str(r/(stage+'-env/bin/python')),'--index-url','https://mirrors.aliyun.com/pypi/simple',*args],check=True,env=env)
common=['safetensors==0.8.0','cuda-python==13.3.1','nvidia-cudnn-cu13==9.20.0.48','imageio==2.37.4','imageio-ffmpeg==0.6.0','setuptools','wheel','ninja','cmake','packaging','scipy','sentencepiece','protobuf','psutil','pyyaml','tqdm','cloudpickle','ftfy','loguru','omegaconf','einops']
run('stage1',common+['torch==2.12.0','torchvision==0.27.0','diffusers==0.40.0','transformers==5.15.1','accelerate==1.0.1','nvidia-cudnn-frontend==1.27.0','nvidia-cutlass-dsl==4.8.0.dev0','apache-tvm-ffi==0.1.13.post3','huggingface-hub==1.29.0','av==18.1.0','scikit-build-core','fastapi','uvicorn','aiofiles','aiohttp','requests','six','h5py','timm','peft','opencv-python','ray>=2.49.1'])
run('stage1',['--no-deps','torchaudio==2.11.0'])
run('stage1',['--no-deps','--editable',str(r/'sources/FastVideo')])
run('stage2',common+['torch==2.13.0','torchvision==0.28.0','transformers==5.14.1','accelerate==1.14.0','nvidia-cutlass-dsl==4.7.0','huggingface-hub==1.27.0','av==18.0.0','openimageio'])
run('stage2',['--no-deps','torchaudio==2.11.0'])
for pkg in ['ltx-core','ltx-pipelines']:
 run('stage2',['--no-deps','--editable',str(r/'sources/LTX-2/packages'/pkg)])
print('RUNTIME_DEPENDENCIES_INSTALLED',flush=True)
