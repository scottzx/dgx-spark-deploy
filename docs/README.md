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
├── presentations/                     # 连续技术报告与视觉呈现工作台 (01 ~ 06)
│   ├── 01_sol_h3_spark_story/         # 技术报告 01：微短剧实战复盘 (小红书 3:4 长图与工作台)
│   ├── 02_llm_session_cache/          # 技术报告 02：NVMe 会话缓存与多槽位调度工程卡片
│   ├── 03_speculative_decoding/       # 技术报告 03：投机采样加速技术卡片
│   ├── 04_acceptance_standard_cases/  # 技术报告 04：官方标准三用例基准验收与全景接触表
│   ├── 05_pool_daughter_blow_test/    # 技术报告 05：单镜头微动作连续性测试技术报告
│   ├── 06_pool_elbow_story_batch/     # 技术报告 06：三镜头连续微短剧批次生成与一致性评测报告
│   └── archive/                       # 历史卡片版本归档
└── assets/                            # 共享视觉多媒体资源
```

---

## 一、核心部署手册 (Deployments)

| 文档名称 | 核心主题 | 主要内容 |
| :--- | :--- | :--- |
| [Sol-H3-Spark部署.md](deployments/Sol-H3-Spark部署.md) | **视频多模态生成** | H3 扩散草稿 + LTX-2.5 视频精修全流程部署、多镜头批处理调度、微短剧实测与 5 大工业化暗坑复盘 |
| [DGX_Spark_Qwen3.8_部署与实战全景总结.md](deployments/DGX_Spark_Qwen3.8_部署与实战全景总结.md) | **大语言模型推理** | 基于 llama.cpp 编译 Blackwell (sm_121a) 原生加速、Docker 生产级部署、投机采样与 NVMe 会话缓存 |

---

## 二、连续技术报告与视觉呈现体系 (Presentations: 01 ~ 06)

本系列按序列记录了从“基础理论、长图文复盘”到“全流程基准测试与多镜头故事生成”的连续技术报告：

| 编号 | 报告与成果主题 | 形式与交付物 | 核心内容摘要 |
| :--- | :--- | :--- | :--- |
| **01** | [01_sol_h3_spark_story](presentations/01_sol_h3_spark_story/) | 3:4 科技长图卡片 / HTML 巡展工作台 | 英伟达Sol-H3-Spark第一次微短剧实战复盘（7页 1440×1920，含 index.html 交互工作台） |
| **02** | [02_llm_session_cache](presentations/02_llm_session_cache/) | 3:4 科技长图卡片 | 大模型高并发 NVMe 会话持久化与 KV Cache 调度优化工程卡片 |
| **03** | [03_speculative_decoding](presentations/03_speculative_decoding/) | 3:4 科技长图卡片 | 基于小模型辅助的投机采样推理加速实践卡片 |
| **04** | [04_acceptance_standard_cases](presentations/04_acceptance_standard_cases/) | 技术报告 / 关键帧接触表 | 官方标准三用例（海浪/舞蹈/公园）端到端 67s 验收与全帧无损解码质检 |
| **05** | [05_pool_daughter_blow_test](presentations/05_pool_daughter_blow_test/) | 技术报告 / 关键帧接触表 | 单镜头高动态双人人际交互动作解算测试（小女孩学巧虎吹手肘，手部解剖结构零崩溃） |
| **06** | [06_pool_elbow_story_batch](presentations/06_pool_elbow_story_batch/) | 技术报告 / 分镜接触表 | 三镜头连续微短剧批处理测试（平均 65.3s/镜）与角色/场景跨镜头一致性深入复盘 |
