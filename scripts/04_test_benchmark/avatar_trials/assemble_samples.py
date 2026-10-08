#!/usr/bin/env python3
"""Compose the same product layout and narration over each avatar sample."""
import argparse
import json
from pathlib import Path
import subprocess

import numpy as np
from PIL import Image, ImageDraw, ImageFont

REPO = Path(__file__).resolve().parents[3]
ROOT = REPO / 'docs/benchmarks/11_coca_cola_avatar'
ASSETS = ROOT / 'assets'
FFMPEG = '/opt/homebrew/bin/ffmpeg'
FONT = '/System/Library/Fonts/Hiragino Sans GB.ttc'
ROUTES = {
    'A': ('route_A_musetalk', 'LiveTalking · MuseTalk 1.5'),
    'B': ('route_B_flashhead', 'OpenAvatarChat · FlashHead Lite'),
    'C': ('route_C_echomimic', 'EchoMimicV3 Flash · 8 steps'),
}


def font(size):
    return ImageFont.truetype(FONT, size)


def centered(draw, text, y, size, fill, x=540):
    draw.text((x, y), text, font=font(size), fill=fill, anchor='mt')


def product_cutout(path):
    image = Image.open(path).convert('RGB')
    pixels = np.asarray(image)
    ys, xs = np.where(pixels.min(axis=2) < 225)
    box = (max(0, int(xs.min()) - 12), max(0, int(ys.min()) - 12),
           min(image.width, int(xs.max()) + 13), min(image.height, int(ys.max()) + 13))
    return image.crop(box)


def make_layout(route, label, destination):
    image = Image.new('RGB', (1080, 1920), '#F6F2EE')
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((60, 54, 330, 107), radius=18, fill='#D81924')
    centered(draw, '可口可乐 · 三款易拉罐', 65, 22, 'white', 195)
    draw.text((60, 132), '今天，你想选哪一罐？', font=font(59), fill='#241E1E')
    draw.text((62, 208), f'{route}  /  {label}', font=font(23), fill='#746B66')
    draw.rounded_rectangle((52, 244, 1028, 1220), radius=28, fill='#E2DAD4')
    products = [('original_gb.jpg', '原味', '经典可乐风味', '#D81924'),
                ('diet.jpg', '健怡', '无糖 · 口感更轻盈', '#64686B'),
                ('zero.jpg', '零度', '无糖 · 接近原味风味', '#171719')]
    for i, (filename, name, tag, color) in enumerate(products):
        x = 60 + i * 328
        draw.rounded_rectangle((x, 1260, x + 304, 1690), radius=24, fill='white')
        packshot = product_cutout(ASSETS / filename)
        packshot.thumbnail((264, 290), Image.Resampling.LANCZOS)
        image.paste(packshot, (x + (304 - packshot.width) // 2,
                              1280 + (290 - packshot.height) // 2))
        centered(draw, name, 1594, 37, color, x + 152)
        centered(draw, tag, 1650, 21, '#716864', x + 152)
    centered(draw, 'AI 数字人演示  ·  官网英美版参考包装', 1870, 22, '#817670')
    image.save(destination)


def ass_time(seconds):
    cs = round(seconds * 100)
    return f'{cs // 360000}:{cs // 6000 % 60:02d}:{cs // 100 % 60:02d}.{cs % 100:02d}'


def split_caption(text, max_chars=19):
    if len(text) <= max_chars:
        return text
    middle = len(text) // 2
    candidates = [i + 1 for i, c in enumerate(text[:-1]) if c in '，。？、']
    cut = min(candidates, key=lambda x: abs(x - middle)) if candidates else middle
    return text[:cut] + r'\N' + text[cut:]


def make_subtitles(destination):
    narration = json.loads((ASSETS / 'narration.json').read_text())
    content = '''[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Hiragino Sans GB,43,&H00FFFFFF,&H00FFFFFF,&H80251E1E,&H80251E1E,0,0,0,0,100,100,0,0,3,14,0,2,70,70,119,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
'''
    for segment in narration['segments']:
        content += (f"Dialogue: 0,{ass_time(segment['start_seconds'])},"
                    f"{ass_time(segment['end_seconds'])},Default,,0,0,0,,"
                    f"{split_caption(segment['text'])}\n")
    destination.write_text(content)


def assemble(route):
    directory, label = ROUTES[route]
    sample = ROOT / directory
    layout = sample / 'layout.png'
    make_layout(route, label, layout)
    make_subtitles(sample / 'narration.ass')
    destination = sample / 'coca_cola_vertical.mp4'
    subprocess.run([FFMPEG, '-v', 'error', '-y', '-loop', '1', '-framerate', '25',
                    '-i', str(layout), '-i', str(sample / 'raw.mp4'),
                    '-i', str(ASSETS / 'narration.wav'), '-filter_complex',
                    '[1:v]scale=960:960:flags=lanczos,setsar=1[avatar];'
                    '[0:v][avatar]overlay=60:252:shortest=1,'
                    'subtitles=narration.ass[v]', '-map', '[v]', '-map', '2:a:0',
                    '-t', '26.44', '-c:v', 'libx264', '-preset', 'fast', '-crf', '19',
                    '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-b:a', '192k',
                    '-movflags', '+faststart', str(destination)], cwd=sample, check=True)
    subprocess.run([FFMPEG, '-v', 'error', '-y', '-ss', '11', '-i', str(destination),
                    '-frames:v', '1', str(sample / 'poster.jpg')], check=True)
    print(destination, flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('routes', nargs='*', choices=list(ROUTES), default=list(ROUTES))
    args = parser.parse_args()
    for route in args.routes:
        assemble(route)
