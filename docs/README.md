# DGX Spark 项目文档体系索引 (Documentation Index)

本目录归档了在 **NVIDIA DGX Spark (GB10 / 128GB Unified Memory / aarch64)** 上进行大语言模型与多模态视频生成私有化部署的全流程技术文档、实操手册与技术报告体系。

---

## 目录结构概览

```text
docs/
├── README.md                          # 本文档导航索引
├── deployments/                       # 核心服务部署与运维实操手册
│   ├── Sol-H3-Spark部署.md            # Sol-H3-Spark 视频生成部署与微短剧实战记录
│   └── DGX_Spark_Qwen3.8_部署与实战全景总结.md # Qwen3.8 / llama.cpp / NVMe 缓存全景总结
├── benchmarks/                        # 性能基准验收与分镜画质质检报告
│   ├── 04_acceptance_standard_cases/  # 官方标准三用例基准验收与全景接触表
│   ├── 05_pool_daughter_blow_test/    # 单镜头微动作连续性测试技术报告
│   └── 06_pool_elbow_story_batch/     # 三镜头连续微短剧批次生成与一致性评测报告
└── assets/                            # 共享视觉多媒体资源
```

> [!TIP]
> **小红书内容创作与发布体系已全量归口**：  
> 本项目对应的小红书 3:4 科技长图卡片、HTML 巡展工作台、社媒文案、封面与移动端一键发布链路已统一归口至内容创作库：  
> `~/Documents/03-内容创作/xhs-publish/01-spark本地部署/`（涵盖 Vol.01 ~ Vol.07 完整分期系列）。

---

## 一、核心部署手册 (Deployments)

| 文档名称 | 核心主题 | 主要内容 |
| :--- | :--- | :--- |
| [Sol-H3-Spark部署.md](deployments/Sol-H3-Spark部署.md) | **视频多模态生成** | H3 扩散草稿 + LTX-2.5 视频精修全流程部署、多镜头批处理调度、微短剧实测与 5 大工业化暗坑复盘 |
| [DGX_Spark_Qwen3.8_部署与实战全景总结.md](deployments/DGX_Spark_Qwen3.8_部署与实战全景总结.md) | **大语言模型推理** | 基于 llama.cpp 编译 Blackwell (sm_121a) 原生加速、Docker 生产级部署、投机采样与 NVMe 会话缓存 |

---

## 二、工程基准验收与质检报告 (Benchmarks)

| 编号 | 验收报告主题 | 形式与交付物 | 核心内容摘要 |
| :--- | :--- | :--- | :--- |
| **04** | [04_acceptance_standard_cases](benchmarks/04_acceptance_standard_cases/) | 技术报告 / 关键帧接触表 | 官方标准三用例（海浪/舞蹈/公园）端到端 67s 验收与全帧无损解码质检 |
| **05** | [05_pool_daughter_blow_test](benchmarks/05_pool_daughter_blow_test/) | 技术报告 / 关键帧接触表 | 单镜头高动态双人人际交互动作解算测试（小女孩学巧虎吹手肘，手部解剖结构零崩溃） |
| **06** | [06_pool_elbow_story_batch](benchmarks/06_pool_elbow_story_batch/) | 技术报告 / 分镜接触表 | 三镜头连续微短剧批处理测试（平均 65.3s/镜）与角色/场景跨镜头一致性深入复盘 |

---

## 三、小红书发布体系关联 (XHS Publication Linkage)

小红书对应的大系列内容位于：[`~/Documents/03-内容创作/xhs-publish/01-spark本地部署/`](file:///Users/scott/Documents/03-%E5%86%85%E5%AE%B9%E5%88%9B%E4%BD%9C/xhs-publish/01-spark%E6%9C%AC%E5%9C%B0%E9%83%A8%E7%BD%B2/)

* **Vol.01** 模型选型与部署实录（53分钟实录粗剪与转录）
* **Vol.02** 部署实战全景总结（13页长图卡片与成片视频）
* **Vol.03** 长上下文突破与并发调度工程实战（8页长图卡片）
* **Vol.04** Sol-H3-Spark 第一次微短剧实战复盘（7页 1440×1920 长图与交互工作台）
* **Vol.05** NVMe 会话持久化与 KV Cache 调度优化（5页长图卡片）
* **Vol.06** 小模型辅助投机采样推理加速实践（6页长图卡片）
* **Vol.07** 四镜头 20 秒链式动画微短剧（单机 56s/镜）、角色 TTS 混流、双语字幕压制与移动端一键发布平台
