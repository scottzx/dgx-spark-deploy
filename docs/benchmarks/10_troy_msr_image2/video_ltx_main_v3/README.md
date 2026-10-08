# 木马计：夺门 · LTX主 H3辅 · 完整影片V3

本轮20镜全部重新生成并拼接：最终为 **LTX19镜、H3辅助1镜，剪辑版91.25秒，672×384、24fps**。共生成22条，原计划LTX17镜和H3三镜；H3的S01/S07提前开舱，S07还提前出现梯子，已用两条新生成LTX替换，原失败输出保留。实际选片和哈希见[selection.json](selection.json)，冻结的原批次不改写。

入口：[91.25秒完整影片](film.mp4)、[31.75秒战斗段](battle.mp4)、[100秒未剪版](film_uncut_100s.mp4)、[逐镜审阅与旧版同步对照](review.html)、[测试记录](qa.md)。浏览器地址：http://127.0.0.1:59137/video_ltx_main_v3/review.html 。旧版对照使用100秒未剪版按20×5秒对齐。

20镜剧情全部保留。S09取前2秒避免重复落地；S11取前2.5秒去掉回走；S17取前1.75秒闭门军阵待命，避开模型提前开门。其他17镜各5秒，所有原始片段完整保留。剪辑帧数和原因见[edit_plan.json](edit_plan.json)。

LTX沿用上一轮连续攻防测试的独立首帧流程：BF16 dev＋distilled LoRA strength1、8步、首帧strength1、原生LTX视频和音频VAE，没有MSR或尾帧。H3使用现有W8A8／FastH3-VSA四次更新和完整原生H3 VAE，没有LTX精修。FastH3预览主要蒸馏文生视频，本轮首帧辅助镜头不代表完整H3底模表现。

复用现有分镜与此前自托管Qwen Image2.1改进的S10/S15/S16/S20首帧；本轮仅统一技术尺寸，没有新增语义生图。后续语义生图继续使用自托管Qwen Image2.1。阿喀琉斯不出场。动作从实际首帧状态继续：S06加固已经关闭的门闩，S09开始下梯，S11落地后示意，S18继续扩大门缝。原始剧本与分镜保存在source_script.md和source_storyboard.json。

运行顺序：prepare.py → run_h3.py → offline_session.py中原生H3解码、LTX提示词缓存和LTX生成 → repair_session.py补跑 → build_review.py → 采样审阅 → edit_film.py → check_review.py。补跑沿用父监督器的两把推理锁，等原LTX子进程退出后才加载模型，结束后恢复父监督器和原服务。原服务已恢复READY，最终回执见session.json和service_health_after.json。

技术规格、指纹、哈希及全文件解码通过，真实浏览器播放、拖动和旧版同步播放通过。serve_review.py在本地59137端口提供字节Range读取，支持长视频拖动，并继续提供此前的审阅页面。其进程信息见review-server.json。

视觉已检查20镜250张精确时间采样，仍有S15武器变形、S16机械结构错误、S19/S20群体交手和角色推进不足。此轮完成整片测试，未标记为制作质量全部合格。保留原生音轨；没有独立听审，无对白与无配乐仍是提示词目标。详见quality_review.json、qa.md、performance.json及run_status.json。

## LTX主 H3辅完整影片V3

2026-10-06按用户选择的LTX连续攻防方向重新生成完整20镜，共22条新视频，最终选入LTX19镜、H3军阵辅助1镜。提供[91.25秒剪辑版](video_ltx_main_v3/film.mp4)、[100秒未剪版](video_ltx_main_v3/film_uncut_100s.mp4)、[31.75秒战斗段](video_ltx_main_v3/battle.mp4)和[逐镜审阅页](video_ltx_main_v3/review.html)。技术和播放检查通过，采样仍见武器、门闩机械和群体接触问题；详见[V3说明](video_ltx_main_v3/README.md)与[测试记录](video_ltx_main_v3/qa.md)。原视频服务已恢复READY。

## MiniMax中文配音版

已使用官方MiniMax CLI生成12段普通话男声旁白，并与原生场景音混音。提供[91.25秒配音片](voiceover_minimax/film_voiced.mp4)、[31.75秒战斗段](voiceover_minimax/battle_voiced.mp4)、[配音审阅页](voiceover_minimax/review.html)和[制作说明](voiceover_minimax/README.md)。完整片视频包哈希与原片相同；旁白按剧情放置，没有额外时间拉伸。
