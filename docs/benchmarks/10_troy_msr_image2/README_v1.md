# 木马计：人物、场景与分镜 V1

已完成 **12 张独立资产：7 张人物参考、5 张场景与道具参考**，以及 **16 张独立分镜图**。本轮跳过阿喀琉斯，继续按“西农劝诱 → 特洛伊人搬运木马 → 奥德修斯带队出马 → 阿伽门农接应”制作剧本和分镜。视频与多角度身份验证尚未执行。

打开 [交互预览页](review.html)，可并排查看三名主角、拖动日夜对照滑块，以及逐张打开原图。

## 剧本、场景和分镜

新剧本 **《木马计：开门》** 拆为 6 个场景、16 镜，剪辑目标约 80 秒。无对白、无配乐，仅环境声与动作声。故事结束在门内接应完成。

- [顺序分镜预览](storyboard/review.html)：按镜或场景查看，图片可打开原图，保留动作起止与审阅记录。
- [完整剧本](script.md) 与 [场景拆解](scene_breakdown.md)。
- [结构化镜头表与完整提示词](storyboard/shotlist.json)：每镜人数、参考图、设备状态、摄影和目标时段。
- [逐镜出图记录](storyboard/results.json)：实际出图进度、源文件、尺寸、SHA-256、耗时、人工审阅和保留的修订版本。

16 镜初版已完成，另外保留 3 张修订前图片。S06 修成闭门上闩，S12 修正士兵下梯朝向，S14 修正阿伽门农剑鞘左右位置；各原 V1 均保留。夜间段从 S07 空广场、S09 梯子布置继续制作；门内段从修正的 S06 布景继续制作。参考图与提示词均记录实际生成输入。

文件完整性、源图复制、提示词和参考路径检查通过。静态人工审阅 13 镜通过、3 镜部分通过，见 [审阅记录](storyboard/qa.md)。S10–S12 的舱框、梯子横档和盔甲纹饰仍有生成差异。动作是否真正连贯、人物是否在视频中稳定，需下一阶段 MSR 视频验证。

## 出图方式与资料

使用内置 **image_gen**，按用户指定的 image2 方向制作。工具结果提供图片和本机保存路径，未返回具体模型版本；[资产清单](asset_manifest.json) 如实记录请求名称与实际工具入口。

本轮工具未开放“精细生图 / 快生图”选择或 quality 参数，实际模式未知；未根据耗时或像素尺寸推断模式。API 可配置 quality 与本轮内置工具是否采用该配置是两件事。

资产完整提示词见 [prompts.json](prompts.json)，逐张提示词另存于 `prompts/`。原图是生成结果的未经修改副本，保留尺寸、SHA-256、参考来源和复制一致性检查。

| 图片 | 原图 | 提示词 |
| --- | --- | --- |
| 奥德修斯 | [原图](assets/characters/odysseus_v1.png) | [提示词](prompts/odysseus.txt) |
| 特洛伊守卫 | [原图](assets/characters/trojan_guard_01_v1.png) | [提示词](prompts/trojan_guard_01.txt) |
| 木马独立道具 | [原图](assets/scenes/trojan_horse_v1.png) | [提示词](prompts/trojan_horse.txt) |
| 西农 | [原图](assets/characters/sinon_v1.png) | [提示词](prompts/sinon.txt) |
| 阿伽门农 | [原图](assets/characters/agamemnon_v1.png) | [提示词](prompts/agamemnon.txt) |
| 广场 · 日景 | [原图](assets/scenes/square_day_v1.png) | [提示词](prompts/square_day.txt) |
| 广场 · 夜景 | [原图](assets/scenes/square_night_v1.png) | [提示词](prompts/square_night.txt) |
| 特洛伊搬运者 | [原图](assets/characters/trojan_worker_01_v1.png) | [提示词](prompts/trojan_worker_01.txt) |
| 特洛伊市民 | [原图](assets/characters/trojan_citizen_01_v1.png) | [提示词](prompts/trojan_citizen_01.txt) |
| 希腊随队士兵 | [原图](assets/characters/greek_soldier_01_v1.png) | [提示词](prompts/greek_soldier_01.txt) |
| 城门外景 | [原图](assets/scenes/gate_day_v1.png) | [提示词](prompts/gate_day.txt) |
| 广场 · 暮景 | [原图](assets/scenes/square_dusk_v1.png) | [提示词](prompts/square_dusk.txt) |

## 造型与装备

西农采用朴素亚麻衣装、无甲无武器；奥德修斯采用深蓝衣装与实用青铜甲；阿伽门农采用年长统帅造型、红披风与装饰青铜甲。守卫、搬运者、市民和随队士兵各制作一名代表，后续可在选定外观后补更多群众与独立角度。

以实际画面作为这版的装备约定：奥德修斯、阿伽门农、随队士兵的剑在**左髋入鞘**；奥德修斯与阿伽门农无盾；随队士兵的单一圆盾背负、双手空。守卫右手持矛、左手持圆盾。奥德修斯提示词曾要求右髋，生成结果实际在左髋，此处已按图修正记录，后续不得把左右位置写混。

## 场景检查

木马独立道具保持刚性木板结构、青铜箍带、四轮平台、单一闭合侧腹舱门。广场日景使用木马道具与旧场景作参考，暮景、夜景均直接编辑同一张日景，人工查看木马、喷泉、城门和火盆的构图位置基本保持；未进行像素级几何一致性测量。

夜景木材和舱门仍可读，无人物、打开的舱门或外露梯子。远处建筑出现暖光，属于本次出图结果；不能据此声称只有两处可见发光区域。

城门外景保留旧城门参考的近取景和太阳纹样旗帜；广场使用纯色旗帜。若采用此造型，分镜定稿前需要统一旗帜并补更宽的城门机位。此预览保留实际差异，方便选定美术方向。

文件完整性检查只验证 PNG、尺寸与原图复制一致，不代表未来视频中的人物和动作一致性通过。项目下一阶段方案见 [MSR V2 + image2](../09_troy_climax/next_msr_image2.md)。
