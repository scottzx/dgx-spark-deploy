# Sol-H3-Spark 双工作流

常驻服务通过每个镜头的 `transition` 选择独立生成或连续续拍。FL2VA 使用首尾分镜图，Ref2VA 使用有序角色参考；每个模型实例内均可切换这两种工作流。`mode=draft|final` 仍控制草稿与精修，两组选项分别生效。

## API

独立镜头使用新的分镜图，省略 `transition` 也默认独立：

```json
POST /api/generate
{
  "case_id": "duel_01",
  "transition": "independent",
  "first_frame": "/home/admin/sol-spark-runtime/inputs/troy_workflows_20261003/board_01.png",
  "prompt": "integrated_multimodal_description: ... overall_soundscape: ... non_diegetic_music: None.",
  "mode": "final",
  "duration_s": 5
}
```

续拍指定同一服务会话中已完成的片段，不再指定首帧：

```json
POST /api/generate
{
  "case_id": "duel_02",
  "transition": "continue",
  "previous_clip_id": "duel_01",
  "context_frames": 22,
  "audio_context_frames": 24,
  "prompt": "integrated_multimodal_description: Continue the preceding tracking shot ... overall_soundscape: ... non_diegetic_music: None.",
  "mode": "final",
  "duration_s": 5
}
```

FL2VA 续拍可另传 `last_frame`，指定后续镜头的终点。不能同时传 `first_frame` 或精修复用用的 `capture_dir`。`previous_clip_id` 必须属于当前 Pipeline 会话，服务重启后应重新开始一条链。

`context_frames` 支持 5、22、39、56；`audio_context_frames` 为 3–120 内的 3 的倍数，默认 24。5/10 秒配置保留。续拍支持 FL2VA 和 Ref2VA 分区。

Ref2VA 的 `/api/generate` 请求使用 `references`，每次按相同顺序提供角色、装备和场景资产。独立请求与续拍请求都保留这些参考；续拍再传 `transition=continue` 和 `previous_clip_id`，不传首尾帧。其视频与音频参考的原始位置、顺序及值均保留，不把上一段的端点图片插入参考列表。Ref2VA 实例由 `SOL_TASK=ref2va`、`SOL_PATHS_FILE=/home/admin/sol-spark-runtime/paths.ref2va.json` 选择，FL2VA 与 Ref2VA 需要各自的模型实例。

FL2VA 的 `/api/story` 每个镜头可以传 `transition`、`first_frame`、`last_frame`、`duration_s` 和上下文窗口。显式 `continue` 自动接续上一镜；显式 `independent` 使用该镜分镜图。旧客户端没有 `transition` 时，保留原有尾帧图片串联行为。Ref2VA 当前使用顺序调用 `/api/generate` 后拼接。

## 实现与时间线

- `stage1_ops/continuation.py` 在当前请求的 H3 潜变量准备阶段插入固定的视频、音频上下文行，并保留可选尾帧条件。
- 视频上下文沿 H3 的 `(1,4,4,4,4)` 帧周期取整，直接复用归一化潜变量；音频使用 40 Hz 潜变量网格，以交付画面的结束时刻作为续接端点。
- 原生去噪循环只更新目标行。每次续拍验证视频、音频上下文及保留的原生参考行在去噪前后逐值相同，并写入 `capture.json`。
- AdaLN 预计算表覆盖普通首尾帧、续拍、续拍加尾帧三种时间步组合，保留 W8A8/VSA 加速和精确 BF16 预计算投影。
- 每个片段保存带 SHA-256 的 `continuation_state.pt`。独立请求清除本请求的上下文状态。
- FL2VA 的 Qwen 使用上一段最终成片的端点图片识别人物与场景；Ref2VA 保持原有有序参考输入。H3 的运动与音频上下文均来自潜变量。

Spark 的 5 秒路径是 H3 124 帧 → LTX 121 帧。默认 22 帧视频上下文包含尚未交付的 3 帧，因此从下一段裁掉 **19 帧**，让那 3 帧落在下一段的交付时间线上，避免跳帧。续拍段新增 **102 帧 / 4.25 秒**。10 秒前驱的 243→241 路径对应裁掉 20 帧。

返回值包含 `transition`、`previous_clip_id`、`trim_frames`、`delivered_frames`、`delivered_duration_s` 和 `continuation` 审计。下游剪辑使用交付帧数，不能按名义 `duration_s` 推算拼接时长。

固定的是 H3 条件行；LTX 会独立精修画面，因此最终成片的动作、色彩和音频接缝仍需要实际检查。该能力不替代角色资产管理、对白 TTS 或口型对齐。

## 部署与回退

实现副本在 `scripts/01_env_setup/sol_spark_runtime/workflow_overlay/`。安装工具先验证所有源文件哈希，再核对服务器文件与已审阅版本一致；不匹配则拒绝覆盖。替换文件保存在服务器 `backups/workflows_<时间>/`，既有时长、Ref2VA 和草稿功能一并保留。

```bash
python install_workflow_overlay.py --overlay workflow_overlay
```

安装后启动新的服务进程才会加载完整改动。代码没有修改 FastVideo 或 ComfyUI checkout。回退时停止自己启动的服务，恢复备份中的同名文件，再启动原服务。

## 验证与素材

- `test_sol_h3_workflows.py`：CPU 测试真实 FastVideo packing ABI，覆盖交付端点、错误请求、立体声音频坐标、冻结条件及模式状态隔离。
- 原有 CPU 回归测试：65 项；测试替身增加新的 capture 元数据，Stage2 测试改为引用已有的 5/10 秒 profile API。
- `run_troy_workflow_comparison.py`：通过真实 API 顺序运行独立 → 续拍 → 独立；两部对照成片共享开场，第二段分别独立生成或续拍。
- `extend_troy_continuous.py`：从续拍片段再次接续 10 秒，检查连续链及长时长输出。
- `run_troy_mixed_story.py`：在一个实际 `/api/story` GPU 请求中运行独立 → 续拍 → 独立，并校验精确帧数拼接。
- `test_sol_h3_story_api.py`：3 项路由集成检查，使用生成器替身与真实成片，验证混合模式、旧客户端尾帧行为、首镜非法接续及真实 FFmpeg 拼接帧数。
- `analyze_sol_h3_join.py`：记录接缝像素差、短窗音频响度变化和生成重叠音频相关性。数值用于比较，不自动宣称感知上无缝。
- 本地 Qwen-Image-2.1 Turbo 生成“特洛伊木马下的希腊武士决斗”分镜素材，摄影方向为 1970 年代邵氏武侠电影的棚景、硬光、色彩和推拉镜头。

实测成片、耗时、接缝观察和测试日志见 [特洛伊双工作流实测](../benchmarks/07_troy_dual_workflows/README.md)。

2026-10-04 的 [角色一致性实测](../benchmarks/08_identity_consistency/README.md) 包含 Ref2VA 实际独立→续拍→独立、专用 LTX 提示词、低噪精修、Ingredients 和 MSR V2。参考条件冻结检查通过，仍不能保证脸、服装及装备的语义一致性；后段出现额外盾牌的原生 H3 与精修画面均已记录。

续接设计参考：[ComfyUI-H3-Motion-Context](https://github.com/NikoDemon80/ComfyUI-H3-Motion-Context)。
