# 木马计：夺门 · 1.25倍速配音版

基于91.25秒中文男声配音成片生成1.25倍速版，输出73秒。保留全部2190帧，帧率由24fps提升为30fps；分辨率仍为672×384。视频时间戳缩短至0.8倍，整条混音使用atempo=1.25保持音调，再锁定为73秒、32kHz双声道AAC。旁白与环境音一同加速，字幕时间戳同样缩短至0.8倍。原速成片保留。

入口：[73秒加速片](film_1_25x.mp4)、[审阅页](review.html)、[对应字幕](narration_1_25x.srt)、[原速配音版](../review.html)。审阅地址：http://127.0.0.1:59137/video_ltx_main_v3/voiceover_minimax/speed_1_25/review.html 。本文件已经加速，播放器以默认1倍播放。

技术检查：2190帧、30fps，视频、音频与容器时长均73秒，全文件解码通过。源片哈希与上轮配音回执匹配，详见[verification.json](verification.json)。浏览器实际播放、音频解码、拖动56.48秒、同步字幕和206分段读取见[browser_verification.json](browser_verification.json)。没有独立听审，不改变原片已记录的画面质量问题。

导出命令：

```sh
ffmpeg -hide_banner -nostdin -y -i ../film_voiced.mp4 \
  -map 0:v:0 -map 0:a:0 -vf 'setpts=(PTS-STARTPTS)/1.25' \
  -r 30 -fps_mode cfr \
  -af 'atempo=1.25,aresample=32000,apad=whole_len=2336000,atrim=end_sample=2336000,asetpts=N/SR/TB' \
  -c:v libx264 -preset fast -crf 18 -c:a aac -b:a 192k \
  -ar 32000 -ac 2 -t 73 -movflags +faststart film_1_25x.mp4
```
