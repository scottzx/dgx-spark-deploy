# 木马计：夺门 · MiniMax中文配音版

使用用户已登录的官方MiniMax CLI `mmx 1.0.25` 生成12段中文男声旁白，覆盖现有91.25秒完整影片。模型`speech-2.8-hd`，系统音色`Chinese (Mandarin)_Male_Announcer`（播报男声），速度1.06、音高-1、32kHz单声道WAV源音频。API返回每段字幕时间戳。

入口：[91.25秒配音完整片](film_voiced.mp4)、[31.75秒战斗段](battle_voiced.mp4)、[配音审阅页](review.html)、[旁白音轨](narration.wav)、[旁白文稿](script.md)、[字幕](narration.srt)。浏览器地址：http://127.0.0.1:59137/video_ltx_main_v3/voiceover_minimax/review.html 。播放器可选择开启中文字幕。

原12段合计51.769秒，均落在预定窗口内，没有额外拉伸或加速。完整旁白音轨按91.25秒时间轴保留空隙。每段仅加10毫秒边缘淡入淡出以防点击声。旁白按照西农劝诱、搬运木马、落闩入夜、奥德修斯与伏兵下梯、夺门战斗、掩护解闩、阿伽门农待命、开门与军团战的剧情放置。

混音保留影片原生音轨。环境音基础增益0.55；旁白通过侧链压缩使环境音在说话期间降低，空隙时恢复。旁白目标-18 LUFS，混音目标-16 LUFS，真峰值目标-1.5dBTP；配音版实际测得-16.02 LUFS、-1.68dBTP。原AAC解码末端短于容器时间，混音尾端补齐并锁定为2920000个32kHz采样，正好91.25秒。最终输出双声道AAC。

完整片的视频流直接复制，原片与配音片的视频包SHA256完全相同；仍为2190帧、24fps、672×384，没有改动画面或重跑图像/视频模型。战斗段为便于试看按S14起点59.5秒精确裁剪后独立编码，762帧、31.75秒。原版影片及其审阅记录保留。

12段音频、完整片、战斗段和混音WAV均全文件解码通过。输入文稿、源影片和音频的哈希绑定在[plan.json](plan.json)、[synthesis_results.json](synthesis_results.json)及[placement.json](placement.json)中；[mix_verification.json](mix_verification.json)记录时长、画面复制和最终响度。真实浏览器音频解码、非静音播放、拖动、字幕及206分段读取结果见[browser_verification.json](browser_verification.json)。这些是技术检查，尚未完成独立听审或独立ASR核对。

生成过程中48kHz请求被API拒绝，改用32kHz；N10首次遇到服务非JSON响应，重试成功，前九段复用而未重生成。失败回执保留在segments/N01/failed_attempt_48khz.json及segments/N10/failure_attempt1.json。当前CLI没有转写子命令；可选新版帮助获取及Whisper模型冷下载已停止，不影响已完成的TTS与混音。

运行：`python3 run_speech.py` → 使用含numpy的Python运行`mix_voiceover.py` → 使用含playwright的Python运行`check_review.py`。本机可用的依赖解释器为`/Library/Frameworks/Python.framework/Versions/3.12/bin/python3`。TTS脚本检查批次指纹及已有音频哈希后复用成功输出；不会显示凭据。认证仍由已有mmx配置管理。官方CLI说明：https://github.com/MiniMax-AI/cli 。

## 1.25倍速版

新增[73秒加速片](speed_1_25/film_1_25x.mp4)与[审阅页](speed_1_25/review.html)。旁白、环境音和字幕同步加速，保持音调，2190帧以30fps输出。原速配音版保留。详见[导出与检查说明](speed_1_25/README.md)。
