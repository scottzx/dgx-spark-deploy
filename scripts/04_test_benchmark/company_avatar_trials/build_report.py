"""Write a reproducible report from completed receipts and explicit visual observations."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]/'docs/benchmarks/14_company_avatar_comparison'
MODELS = [
    ('joyhallo', 'JoyHallo', 'https://github.com/jdh-algo/JoyHallo', '音频驱动裁切肖像；不测试商品动作'),
    ('joyvasa', 'JoyVASA', 'https://github.com/jdh-algo/JoyVASA', '音频驱动肖像；身体、商品沿用参考图'),
    ('infinitetalk', 'InfiniteTalk', 'https://github.com/MeiGen-AI/InfiniteTalk', 'LTX 分段关键帧引导，FusionX LoRA 8 步重新生成'),
    ('longcat', 'LongCat-Video-Avatar 1.5', 'https://github.com/meituan-longcat/LongCat-Video', '参考首帧＋音频＋提示词，DMD 8 步分段续接'),
    ('liveportrait', 'LivePortrait', 'https://github.com/KlingAIResearch/LivePortrait', '沿用 LTX 身体动作，以已有口播视频驱动嘴部'),
    ('latentsync', 'LatentSync 1.6', 'https://github.com/bytedance/LatentSync', '沿用 LTX 身体动作，20 步音频驱动口型'),
    ('avatarforever', 'Avatar-Forever', 'https://github.com/leeruibin/avatarforever', 'LTX 2.3 22B，首帧＋音频＋提示词，历史特征缓存开启'),
]
receipts = json.loads((ROOT/'measured_results.json').read_text())
rows = []
for key, title, url, scope in MODELS:
    group = [r for r in receipts if r['engine'] == key]
    times = ' / '.join(f"{r['render_seconds']:.1f}" for r in group) or '—'
    peak = f"{max(r['peak_cuda_allocated_gib'] for r in group):.2f}" if group else '—'
    rows.append(f'| [{title}]({url}) | {len(group)}/3 | {times} | {peak} | {scope} |')
held = [f"{r['engine']}/{r['product']}" for r in receipts if r.get('final_frame_hold_seconds')]
held_text = '、'.join(held) or '目前无'
qa = []
if (ROOT/'quality_review.json').exists():
    for row in json.loads((ROOT/'quality_review.json').read_text()).get('observations', []):
        qa.append(f"- **{row['engine']}**：{row['finding']}")
report = f'''# 六项公司数字人项目：三组商品实测

日期：2026-10-08。六项项目包含京东 JoyHallo / JoyVASA 两种模型，实际为七种模型、21 个商品测试。

[打开对比页](review.html)（当前本地预览：http://127.0.0.1:58123/review.html）。页面只展示实际推理完成并验证的成片。

## 共同输入与验收目标

原味、健怡、零度各 8.04 秒、25 FPS、201 帧。每组目标为「拿起商品 → 手持介绍 → 放回并松手」。使用同一套 Serena 柔和中文女声，成片统一混入原始 24 kHz 配音。16 kHz 音频是部分模型需要的输入副本。

动作参照为此前 LTX 生成视频，用户明确同意沿用；本轮没有实拍素材。图生视频模型使用对应视频的首帧。JoyHallo 为符合其肖像输入要求，另做固定身份的面部裁切；该结果仅评价口播。LivePortrait 由此前 Serena/MuseTalk 成片驱动面部，因此不是独立的音频转动作模型。

首帧、视频和音频派生记录见 [共同输入](input_manifest.json)、[派生输入](derived_inputs.json)。基线本身已有包装文字错乱；新模型沿用这些画面时，不能把既有错字算成新模型生成的问题，也不能宣称包装正确。

InfiniteTalk 官方 streaming 实现每段取 LTX 视频的一张关键帧作为图像条件，并用前一段生成结果的 9 帧续接。当前 81 帧分段的关键帧位置为 0 / 72 / 144 帧（0 / 2.88 / 5.76 秒），身体和商品动作仍由模型重新生成。\n\n## 实测结果

已完成 **{len(receipts)}/21** 组。以下时间按原味 / 健怡 / 零度顺序排列；缺少成片的项目没有填入推算结果。

| 模型 | 完成 | 各组生成秒数 | 最大 CUDA 已分配 GiB | 本轮范围 |
| --- | --- | --- | --- | --- |
{chr(10).join(rows)}

「生成秒数」来自 Spark 原始运行记录：通常排除一次共享权重加载，包含模型推理和原生视频编码，不含最终统一配音封装。Avatar-Forever 存在延迟加载，生成计时包含延迟权重加载，详见各组 metrics.json。CUDA 峰值仅统计 PyTorch 分配，不能当成机器总内存。三个 8.04 秒片段的 24.12 秒合辑是顺序剪辑，没有验证一次生成 24 秒的连续动作。

## 画面检查记录

{chr(10).join(qa) or '尚未形成最终画面结论。'}

动作关键帧和说话边界的连续原始帧在对比页中。帧图仅做裁切、缩放和拼排，没有补帧或生成修图。单帧闭嘴不能用于判定口型延迟；需要结合实际人声起点和连续播放。

统一成片通常为 201 帧；原生 200 帧、8.00 秒的个别输出，仅延长真实末帧显示 40 毫秒以统一播放时长。当前记录：{held_text}。原生输出及原始封装记录均保留，动作验收使用原生画面。松手判断要求明确离手画面，见 [验收依据](acceptance_criteria.json)。\n\n## 环境与可复现性

DGX Spark GB10，ARM64，128 GB 标称统一内存，Python 3.12、PyTorch 2.14.1 / CUDA 13。模型串行占用 GPU。官方代码提交及依赖版本见 [环境记录](environment.json)。

所有模型使用实际官方权重；下载清单与校验见 modelscope_manifest.json、hf_manifest.json、infinitetalk_lora_manifest.json 及相应 download_receipt。适配文件位于仓库 scripts/04_test_benchmark/company_avatar_trials，原始源码保存在 Spark 的 /home/admin/avatar-company-tests/sources。

ARM64 环境使用 OpenCV / FFmpeg 实现 decord 读取接口，ONNX 面部检测使用 CPU 四线程。LongCat / InfiniteTalk 等需要的 FlashAttention 接口由 PyTorch SDPA 执行同等密集注意力；它不代表原生 FlashAttention 内核的性能。BF16 数值核对记录见 [注意力适配验证](attention_compatibility.json)。LatentSync 使用独立 Diffusers 0.32.2 目录；其他依赖也独立安装，没有改动原有业务环境。

JoyHallo 的三组官方人脸预处理已在 CPU 上实际执行，特征与遮罩记录见 [预处理检查](preflight_joyhallo_image.json)；这项检查不计入视频生成完成数。

每条成片 SHA256 与 Spark 原始记录一致，完整解码、帧数、时长、音轨验证见 [媒体验证](verification.json)。候选音轨与对应 Serena 基线的解码 PCM 逐样本一致性见 [配音验证](audio_verification.json)。每组原生输出和完整日志保留在 Spark /home/admin/avatar-company-tests/outputs 与 logs。没有以其他模型的成片替代失败或待运行结果。

本轮验证离线商品口播效果和单机生成时间，未测试 RTMP 推流、多人交互或实时直播链路。
'''
if len(receipts)==21:
    report = report.replace('## 共同输入与验收目标', '本轮建议优先保留 LTX 商品动作，以 LatentSync 1.6 处理口型；LivePortrait 可作已有口播视频驱动的备选。LongCat、InfiniteTalk、Avatar-Forever 重新生成动作时没有在三组中稳定完成完整商品流程。JoyHallo、JoyVASA 的肖像口播范围无法满足拿放商品要求。\n\n## 共同输入与验收目标')
(ROOT/'README.md').write_text(report)
if (ROOT/'avatarforever_diagnostics.html').exists():
    with (ROOT/'README.md').open('a') as stream:
        stream.write('\n## Avatar-Forever 默认缓存配置与口播对照\n\n另有四条补充视频，独立于 21 条主测试：[三组缓存与作者提示词对照](avatarforever_diagnostics.html)。官方脚本默认关闭历史特征缓存，先按这个设置补测三组商品，只改变该缓存开关；再用原味音频配合作者默认口播提示词，不要求拿放商品。不能将仅口播对照当作完整商品动作通过。参数及默认值核对见 [参数记录](avatarforever_parameter_audit.json)。\n')
print(f'Report: {len(receipts)}/21 completed')
