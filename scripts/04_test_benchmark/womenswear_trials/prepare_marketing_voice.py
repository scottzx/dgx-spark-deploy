"""Generate level-matched marketing auditions without changing existing videos."""
import argparse
import datetime
import fcntl
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

os.environ['HF_HUB_OFFLINE'] = '1'
os.environ['TRANSFORMERS_OFFLINE'] = '1'
os.environ['PATH'] = '/home/admin/.local/bin:' + os.environ.get('PATH', '')
import numpy as np
import soundfile as sf
import torch
from qwen_tts import Qwen3TTSModel

ROOT = Path('/home/admin/womenswear-avatar-tests/marketing_voice_v1')
MODELS = Path('/home/admin/models_cache/audio_models')
TEXT = ('姐妹们，今天这三件女装，咱们一件一件看！先看这件白色衬衫，简洁利落，通勤很好搭。'
        '再看粉色开衫，温柔百搭，叠穿也好看。最后这件黑色连衣裙，线条简洁，日常穿搭也很合适。'
        '喜欢哪一件，我们再看看细节！')
MARKETING_TEXT = TEXT
SHORTS = [('shirt', '白色衬衫，简洁利落，通勤好搭。'),
          ('cardigan', '粉色开衫，温柔百搭，适合叠穿。'),
          ('dress', '黑色连衣裙，线条简洁，日常好搭。')]
PROFILES = [
    ('baseline', '原柔和风格对照', 'Serena',
     '温暖柔和、自然亲切的成年女声，音调稍低，用平稳的日常说话方式介绍商品，声音圆润放松，'
     '语速适中略紧凑，轻声清晰，不喊、不尖锐、不夸张，不用气声耳语，句尾平稳。'),
    ('vivian_guide', 'A · 热情专业导购', 'Vivian',
     '像有经验的女装直播导购面对镜头介绍产品，热情、自信、亲切，有感染力。声音中音区饱满，'
     '有扎实的气息支撑和清楚的咬字，亮而圆润。产品名和搭配卖点有明确重音，语气有起伏，'
     '短停顿清楚，节奏利落，句尾干净有力。普通话标准。避免尖细嗓音、刺耳高音、喊叫和气声。'),
    ('vivian_live', 'B · 强节奏直播', 'Vivian',
     '兴奋、积极、有激情的成年女装带货主播，正在热情招呼直播间的观众。声音饱满、有力量，'
     '中音区清晰明亮，气息充足，节奏紧凑，有明显的轻重和语气起伏。商品名清楚突出，'
     '卖点自然加重，像面对面推荐喜欢的衣服，收尾带行动号召。避免尖叫、喊麦、尖细高音，'
     '不要机械播报、不要气声。普通话标准，语速较快但每个字都清楚。'),
    ('serena_full', 'C · 成熟饱满导购', 'Serena',
     '成熟自信、热情有感染力的成年女性服装导购，声音圆润饱满，音调中低，有胸腔共鸣与扎实'
     '气息，能量充足，像热情介绍自己很喜欢的产品。字头清晰，产品名和卖点有明确重音，'
     '语气起伏自然，节奏利落，句尾肯定有力。不要轻声平读、不要耳语或软绵绵，不要刺耳、'
     '尖细、喊叫或刻意装甜。标准普通话，语速适中偏快。'),
    ('design_full', 'D · 新设计带货女声', None,
     '一位约三十岁的中国女性女装直播主播，标准普通话，女中音，音色厚实圆润、通透饱满，'
     '胸腔共鸣明显，气息稳健充足。性格热情爽朗，自信有感染力，兴奋地向观众推荐女装，'
     '声音有力量但不喊，语气抑扬顿挫，商品名和搭配卖点明确加重，短停顿有节奏，'
     '语速利落稍快，句尾积极肯定，最后一句像热情邀请观众看细节。不要高尖嗓音、刺耳、'
     '娃娃音、气声、耳语或机械念稿。')]

parser = argparse.ArgumentParser()
parser.add_argument('mode', choices=['custom', 'design'])
parser.add_argument('--set', dest='voice_set', choices=['marketing', 'natural'], default='marketing')
args = parser.parse_args()
if args.voice_set == 'natural':
    assert args.mode == 'custom'
    ROOT = Path('/home/admin/womenswear-avatar-tests/natural_voice_v2')
    TEXT = ('我们先看这件白衬衫，款式比较简单，上班的时候可以配长裤。'
            '接着是这件粉色开衫，搭在衬衫外面也挺合适。'
            '最后这件黑色连衣裙，整体的线条很简洁，平时出门穿也好搭。'
            '这三件你比较喜欢哪一件，我再拿近一点给你看。')
    SHORTS = [('shirt', '这件白衬衫款式比较简单，配长裤就挺好看。'),
              ('cardigan', '这件粉色开衫，搭在衬衫外面也挺合适。'),
              ('dress', '这件黑色连衣裙，平时出门穿也挺好搭。')]
    PROFILES = [('serena_default', '1 · 日常女声', 'Serena', ''),
                ('serena_chat', '2 · 随口介绍', 'Serena', '像和身边的人聊天一样自然地说，语速正常，语气放松。'),
                ('vivian_default', '3 · 明亮女声', 'Vivian', '')]
ROOT.mkdir(parents=True, exist_ok=True)
lock = Path('/home/admin/avatar-company-tests/gpu.lock').open('w')
fcntl.flock(lock, fcntl.LOCK_EX)

model_name = 'Qwen3-TTS-12Hz-1.7B-' + ('CustomVoice' if args.mode == 'custom' else 'VoiceDesign')
t0 = time.perf_counter()
model = Qwen3TTSModel.from_pretrained(str(MODELS/model_name), device_map='cuda:0',
                                    dtype=torch.bfloat16, attn_implementation='sdpa')
torch.cuda.synchronize()
load_seconds = time.perf_counter()-t0

def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()

def level_match(source, target):
    # Same mild presence EQ and constant loudness matching for all profiles.
    # Natural timing and pitch are preserved; auditions are not squeezed into 8 seconds.
    measured = subprocess.run(['ffmpeg', '-hide_banner', '-i', str(source), '-af',
        'highpass=f=65,equalizer=f=3500:t=q:w=0.8:g=-2,loudnorm=I=-23:TP=-3:LRA=11:print_format=json',
        '-f', 'null', '-'], capture_output=True, text=True, check=True)
    s=measured.stderr; stats=json.loads(s[s.rfind('{'):s.rfind('}')+1])
    gain=min(-23-float(stats['input_i']), -3-float(stats['input_tp']))
    subprocess.run(['ffmpeg','-v','error','-y','-i',str(source),'-af',
        f'highpass=f=65,equalizer=f=3500:t=q:w=0.8:g=-2,volume={gain:.6f}dB',
        '-ar','24000','-c:a','pcm_s16le',str(target)],check=True)
    return {'target_lufs':-23,'constant_gain_db':gain,'pre_gain_measurement':stats,
            'pitch_changed':False,'speed_changed':False,
            'equalizer':'highpass 65Hz; 3500Hz -2dB Q0.8'}

for index, (key, label, speaker, instruction) in enumerate(PROFILES):
    if (speaker is not None) != (args.mode == 'custom'):
        continue
    folder=ROOT/key;folder.mkdir(exist_ok=True)
    if (folder/'receipt.json').exists():
        continue
    clips=[]
    sentences=[('audition',TEXT)]
    if args.voice_set == 'natural':
        sentences.append(('audition_original_text', MARKETING_TEXT))
    sentences += SHORTS if speaker else []
    for j,(name,text) in enumerate(sentences):
        started=time.perf_counter()
        seed=2026100840+j if args.voice_set == 'natural' else 2026100800+index*100+j
        torch.manual_seed(seed)
        raw=folder/f'{name}_raw.wav';out=folder/f'{name}.wav'
        reused=raw.exists()
        if reused:
            wave,rate=sf.read(raw,dtype='float32')
        else:
            kwargs=dict(text=text,language='Chinese',instruct=instruction,max_new_tokens=2048)
            if speaker: wavs,rate=model.generate_custom_voice(speaker=speaker,**kwargs)
            else: wavs,rate=model.generate_voice_design(**kwargs)
            torch.cuda.synchronize();wave=np.asarray(wavs[0],dtype=np.float32)
            sf.write(raw,wave,rate)
        assert rate==24000 and np.isfinite(wave).all() and len(wave)>rate*.5
        processing=level_match(raw,out)
        record={'key':name,'text':text,'sample_rate':rate,'duration_seconds':len(wave)/rate,
                'seed':seed,'raw_sha256':sha(raw),'sha256':sha(out),
                'reused_existing_raw':reused,
                'generation_and_processing_seconds':time.perf_counter()-started,
                'processing':processing,'fits_existing_3_44_second_window':len(wave)/rate<=3.44}
        clips.append(record);print(json.dumps({'profile':key,'clip':name,'seconds':record['duration_seconds']},ensure_ascii=False),flush=True)
    receipt={'key':key,'label':label,'model':model_name,'speaker':speaker,'instruction':instruction,
             'shared_model_load_seconds':load_seconds,'clips':clips,
             'generated_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
             'scope':'Audio audition only; existing lip-synchronized videos are unchanged.'}
    (folder/'receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'completed_profile':key},ensure_ascii=False),flush=True)
print(json.dumps({'mode':args.mode,'complete':True}),flush=True)
