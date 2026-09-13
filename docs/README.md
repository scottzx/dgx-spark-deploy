# DGX Spark 项目文档体系索引 (Documentation Index)

本目录归档了在 **NVIDIA DGX Spark (GB10 / 128GB Unified Memory / aarch64)** 上进行大语言模型与多模态视频生成私有化部署的全流程技术文档、实操手册、基准压测与运营卡片。

---

## 目录结构概览

```text
docs/
├── README.md                     # 本文档导航索引
├── deployments/                  # 核心服务部署与运维实操手册
│   ├── Sol-H3-Spark部署.md       # Sol-H3-Spark 视频生成部署与微短剧实战记录
│   └── DGX_Spark_Qwen3.8_部署与实战全景总结.md # Qwen3.8 / llama.cpp / NVMe 缓存全景总结
├── benchmarks/                   # 验收测试与多模态抽帧接触表
│   ├── acceptance-20260913-023512/ # 官方三类标准用例（海浪/舞蹈/公园）验收
│   ├── pool_daughter_blow_001/    # 单镜头微动作测试接触表
│   └── pool_elbow_story_001/      # 三镜头父女泳池连续微短剧批次接触表
├── presentations/                # 视觉呈现与小红书 3:4 科技长图工作台
│   ├── 01_sol_h3_spark_story/    # 微短剧实战复盘（7页 1440×1920，含 index.html 巡展工作台）
│   ├── 02_llm_session_cache/     # NVMe 会话缓存与多槽位调度工程卡片
│   ├── 03_speculative_decoding/  # 投机采样加速卡片
│   └── archive/                  # 历史版本归档
└── assets/                       # 共享视觉多媒体资源
```

---

## 一、核心部署指南 (Deployments)

| 文档名称 | 核心主题 | 主要内容 |
| :--- | :--- | :--- |
| [Sol-H3-Spark部署.md](deployments/Sol-H3-Spark部署.md) | **视频多模态生成** | H3 扩散草稿 + LTX-2.5 视频精修全流程部署、多镜头批处理调度、微短剧实测与 5 大工业化暗坑复盘 |
| [DGX_Spark_Qwen3.8_部署与实战全景总结.md](deployments/DGX_Spark_Qwen3.8_部署与实战全景总结.md) | **大语言模型推理** | 基于 llama.cpp 编译 Blackwell (sm_121a) 原生加速、Docker 生产级部署、投机采样与 NVMe 会话缓存 |

---

## 二、评测与验收报告 (Benchmarks)

| 目录 | 评测目标 | 包含产物 |
| :--- | :--- | :--- |
| [acceptance-20260913-023512](benchmarks/acceptance-20260913-023512) | 官方标准三用例基准 | `dog_park`, `coastal_waves`, `dance_stage` 全帧无损解码与关键帧接触表 |
| [pool_daughter_blow_001](benchmarks/pool_daughter_blow_001) | 单镜头动作解算审查 | 小女孩学巧虎吹手肘痛痛拜拜微表情与手部解剖结构审查 |
| [pool_elbow_story_001](benchmarks/pool_elbow_story_001) | 三镜头微短剧批量推理 | 3 个分镜端到端用时（66.6s / 66.1s / 63.3s）、一致性审查与问题记录 |

---

## 三、视觉与宣发卡片 (Presentations)

基于 `xhs-tech-card` 规范制作的 1440×1920 Retina 高清小红书长图卡片：

* **[01_sol_h3_spark_story](presentations/01_sol_h3_spark_story/)**：
  * **主题**：英伟达Sol-H3-Spark第一次微短剧实战复盘
  * **包含**：7 张 3:4 高清 PNG、源码 [cards.md](presentations/01_sol_h3_spark_story/cards.md)、本地交互巡展工作台 [index.html](presentations/01_sol_h3_spark_story/index.html)。
* **[02_llm_session_cache](presentations/02_llm_session_cache/)**：
  * **主题**：大模型高并发 NVMe 会话持久化与 KV Cache 调度优化
* **[03_speculative_decoding](presentations/03_speculative_decoding/)**：
  * **主题**：基于小模型辅助的投机采样推理加速实践
