# 女装自然语气合成

使用已选第一版「日常女声」Serena 默认语气。三件商品的短句直接采用已校对的试听音频，采样内容、语速、音高及响度保持不变，仅增加静音以匹配 8.04 秒动作窗口。

LTX 身体动作复用上一轮；LatentSync、LongCat 与 InfiniteTalk 均重新用新音频推理。人物、服装参考图、动作提示与随机种子沿用原测试。每条路线三件各 8.04 秒，合辑 24.12 秒，576×768、25 FPS、精确 3:4。

[打开本轮视频](review.html) · [上一轮视频](../review.html) · [自然语气试听](../natural_voice_v2/index.html)。

这是三件商品分别合成后顺序剪辑，动作完成与生成完成分别检查；参考动作来自生成的 LTX 视频，没有实拍素材。原生输出和所有质量异常保留。

过程记录：synthesis_provenance.json、inputs/voice.json、measured_results.json、verification.json、audio_verification.json。
