# 测量结果

| 路线 | 有效 FPS | 26.44 秒生成耗时 | 加载与准备 | CUDA allocated 峰值 |
| --- | ---: | ---: | ---: | ---: |
| A · LiveTalking MuseTalk 1.5 rendering components | 30.22 | 21.87s | 5.49s | 6.68 GiB |
| B · OpenAvatarChat FlashHeadProcessor + SoulX-FlashHead Lite | 17.19 | 38.45s | 5.81s | 4.98 GiB |
| C · EchoMimicV3 Flash | 1.03 | 642.15s | 49.38s | 19.29 GiB |

推荐 A 作为 Spark 实时口播的起点；B 用来继续评估人物自然度与提速；C 适合离线视频制作。

这是本次固定口播组件测试的结果。各路线的计时范围与未测项目见 [实测说明](README.md)。
