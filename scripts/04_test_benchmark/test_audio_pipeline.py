#!/usr/bin/env python3
"""
DGX Spark: 端到端语音流水线测试 (ASR 语音理解 + Qwen3-TTS 情感角色配音)
与 Sol-H3-Spark 微短剧流水线直接协同，产出用于微短剧音画解耦混音的高保真 WAV 音频。
"""

import os
import sys
from pathlib import Path
import soundfile as sf

CACHE_ROOT = Path(os.environ.get("MODEL_DIR", Path.home() / "models_cache" / "audio_models"))
OUTPUT_DIR = Path(__file__).resolve().parent.parent.parent / "outputs" / "audio_test"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def test_qwen3_tts_generation():
    """测试 Qwen3-TTS 1.7B 自定义音色与自然语言情绪指令生成"""
    print("\n" + "=" * 60)
    print("🔊 [TTS 测试] Qwen3-TTS-12Hz-1.7B-CustomVoice 生成测试")
    print("=" * 60)

    try:
        from qwen_tts import Qwen3TTSModel
    except ImportError:
        print("提示: 未安装 qwen-tts 包，请先执行: pip install -U qwen-tts")
        return

    model_path = CACHE_ROOT / "Qwen3-TTS-12Hz-1.7B-CustomVoice"
    target = str(model_path) if model_path.exists() else "Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice"
    
    print(f"正在加载 Qwen3-TTS 模型 ({target})...")
    model = Qwen3TTSModel.from_pretrained(target, device="cuda")

    # 测试短剧对白用例：父女泳池互动（对应 Sol-H3-Spark 泳池场景）
    test_cases = [
        {
            "id": "daughter_laugh",
            "text": "爸爸！你看我抓到了什么，水里有一条金色的小鱼！",
            "speaker": "Vivian",
            "instruct": "用7岁活泼小女孩兴奋雀跃的声音，带一点清脆的笑声快速说出来",
        },
        {
            "id": "father_warm",
            "text": "小心点别滑倒了，快游过来让爸爸看看！",
            "speaker": "Ryan",
            "instruct": "用35岁温柔父亲宠溺而关切的语调，声音温和低沉",
        }
    ]

    for item in test_cases:
        print(f"\n--> 正在生成镜头对白 [{item['id']}]: \"{item['text']}\"")
        print(f"    情绪指令: \"{item['instruct']}\"")
        wavs, sr = model.generate_custom_voice(
            text=item["text"],
            language="Chinese",
            speaker=item["speaker"],
            instruct=item["instruct"],
        )
        out_wav = OUTPUT_DIR / f"{item['id']}.wav"
        sf.write(str(out_wav), wavs, sr)
        print(f"    ✅ 已保存高质量对白音频: {out_wav} (采样率: {sr}Hz)")


def test_sensevoice_asr():
    """测试 SenseVoice 极速语音识别与情绪/事件检测"""
    print("\n" + "=" * 60)
    print("👂 [ASR 测试] SenseVoice-Small 极速情感与富音频识别")
    print("=" * 60)

    try:
        from funasr import AutoModel
    except ImportError:
        print("提示: 未安装 funasr 包，请先执行: pip install -U funasr")
        return

    model_path = CACHE_ROOT / "SenseVoiceSmall"
    target = str(model_path) if model_path.exists() else "iic/SenseVoiceSmall"

    print(f"正在加载 SenseVoice 模型 ({target})...")
    model = AutoModel(model=target, trust_remote_code=True, device="cuda:0")

    # 选取刚生成的 TTS 音频进行回环校验
    sample_wav = OUTPUT_DIR / "daughter_laugh.wav"
    if sample_wav.exists():
        print(f"--> 正在对刚生成的音频进行回环转写与情绪分析: {sample_wav}")
        res = model.generate(input=str(sample_wav), cache={}, language="auto", use_itn=True)
        print("    ✅ 转写与情绪识别结果:")
        print(f"    {res}")
    else:
        print("提示: 尚未生成示例音频，跳过回环识别。")


def main():
    print("=" * 60)
    print("🚀 DGX Spark: 音画解耦语音子系统测试")
    print("=" * 60)
    test_qwen3_tts_generation()
    test_sensevoice_asr()
    print("\n" + "=" * 60)
    print("🎉 音频流水线测试完成！输出目录:", OUTPUT_DIR)
    print("=" * 60)


if __name__ == "__main__":
    main()
