# Qwen-Image-2.1 图像资产生成

部署目标：`spark-e72e`，DGX Spark / GB10 SM121 / ARM64 / 128GB 统一内存。

连续资产生产的性能测试见 [加速实测](Qwen-Image-2.1加速实测.md)。下文基础 CLI 仍为逐张加载的原版入口。

## 用途与来源

用于制作视频所需的角色、道具、场景、参考图和透明 PNG 资产。官方同一流水线支持文生图、图像编辑和最多 10 张参考图。

- [官方仓库](https://github.com/QwenLM/Qwen-Image-2.1)
- [ModelScope 官方权重](https://modelscope.cn/models/Qwen/Qwen-Image-2.1)
- [模型许可证](https://huggingface.co/Qwen/Qwen-Image-2.1/blob/main/LICENSE)：Qwen Research License，限非商业研究/评估；商业使用需单独向模型方取得授权。

## 目录

| 内容 | Spark 绝对路径 |
|---|---|
| 官方 BF16 权重，约 33.1GB | `/home/admin/models_cache/Qwen-Image-2.1` |
| 独立运行环境及入口 | `/home/admin/qwen-image-2.1-runtime` |
| Python | `/home/admin/qwen-image-2.1-runtime/venv/bin/python` |
| 日志 | `/home/admin/qwen-image-2.1-runtime/logs` |
| 资产默认存放位置 | `/home/admin/qwen-image-2.1-runtime/outputs` |

模型含图像生成 Transformer、Qwen3-VL 文图编码器、RGBA VAE 及处理器配置。7B 指图像生成组件，并非整个流水线的总参数量。

## 环境

- Python 3.12；PyTorch `2.12.0+cu130`；Transformers `5.17.0`。
- Diffusers `0.41.0.dev0`，固定上游提交 `5ff8e59ff9fe81c6e2df4fb4c6ea0d97a5df5ab2`。安装时的 PyPI `0.40.0` 尚不提供 `QwenImage21Pipeline`，因此使用官方源码构建。
- 完整依赖记录：`/home/admin/qwen-image-2.1-runtime/requirements.lock.txt`。
- 本次 CUDA 运行库从已通过 GB10 验证的 Stage1 环境复制到独立目录，没有更改原视频环境。NVIDIA cuSPARSELt 0.8.1 的官方 wheel 使用 `manylinux2014_sbsa` 标记，`uv pip check` 会报告平台标记不兼容；实际 `.so` 经 `file` 检查是 ARM aarch64，CUDA/BF16 运算通过。

在 Spark 的项目检出目录，可使用 `bash scripts/01_env_setup/install_qwen_image_21.sh` 复现环境安装与下载；脚本不停止现有模型服务。

## 使用

以下命令在 Spark 上执行。生成前应确保语言模型及视频模型已释放 GPU；入口会检查 CUDA 计算进程、可用系统内存及图像/视频批次锁。执行期间不要从其他入口启动语言或视频模型。

普通资产：

```bash
bash /home/admin/qwen-image-2.1-runtime/run_qwen_image_21.sh \
  --prompt '电影级角色设定图，一位穿蓝色工作服的年轻维修师，全身，正面站姿，中性灰背景，无文字' \
  --width 1024 --height 1024 --steps 40 --seed 42 \
  --output /home/admin/qwen-image-2.1-runtime/outputs/mechanic.png
```

透明道具：

```bash
bash /home/admin/qwen-image-2.1-runtime/run_qwen_image_21.sh \
  --transparent --prompt 'A single handcrafted red ceramic teapot, three-quarter view, entire object visible, studio product lighting, no text.' \
  --output /home/admin/qwen-image-2.1-runtime/outputs/teapot.png
```

参考图编辑；可重复传入 `--image`，最多 10 张，顺序对应提示词中的图像顺序：

```bash
bash /home/admin/qwen-image-2.1-runtime/run_qwen_image_21.sh \
  --image /home/admin/qwen-image-2.1-runtime/outputs/mechanic.png \
  --prompt '保持人物面貌、发型和服装不变，改成侧面站姿，全身，中性灰背景，无文字' \
  --output /home/admin/qwen-image-2.1-runtime/outputs/mechanic-side.png
```

入口默认 1024×1024、40 步；官方原生规格为 2048×2048，可指定 `--width 2048 --height 2048`。不同尺寸的速度和峰值内存需分别测量。

每张 PNG 配有同名 JSON，记录实际提示词、参考图路径、种子、依赖版本、加载/生成耗时、GPU 峰值分配、Alpha 范围和文件 SHA-256。入口不会覆盖已有输出；PNG 可解码和像素非均匀检查不代表画面质量合格，仍需查看实际图片。

## 下载与完整性

安装时保存官方 ModelScope 文件清单 `modelscope-files.json`，按各文件提交版本下载并核对 SHA-256。分段下载可续传，完整文件校验成功后才落到正式路径。

```bash
python3 /home/admin/qwen-image-2.1-runtime/download_qwen_image_21.py \
  --manifest /home/admin/qwen-image-2.1-runtime/modelscope-files.json \
  --model /home/admin/models_cache/Qwen-Image-2.1

python3 /home/admin/qwen-image-2.1-runtime/verify_qwen_image_21.py \
  --manifest /home/admin/qwen-image-2.1-runtime/modelscope-files.json \
  --model /home/admin/models_cache/Qwen-Image-2.1 \
  --receipt /home/admin/qwen-image-2.1-runtime/weights-verified.json
```

## 验收状态

2026-09-29：安装与真实出图验收完成。

- 官方清单 29 个文件（33,134,789,599 字节）全部通过大小与 SHA-256 校验，凭据为 `weights-verified.json`。
- 独立 Python 环境的 GB10 CUDA/BF16 运算、五个模型组件导入通过。
- 实测入口在语言模型占用 GPU 时会拒绝加载图像模型。
- 三张 PNG 均可正常解码；场景图符合左侧窗户、工作台、陶器架等提示要求；参考图编辑将茶壶由红色变为蓝色，主体形状、构图基本保留。
- 红色、蓝色茶壶 Alpha 范围均为 0–255，近透明像素分别占 70.17% / 70.07%。个别查看工具会显示透明像素中保留的 RGB 底色；PNG 的 Alpha 数据本身有效。
- 验收后已恢复 `qwen3-8-flash-next`，语言模型 `:8001/health` 和代理 `:8000/health` 均返回 `status: ok`。图像模型按需运行，无常驻 GPU 进程。

### GB10 实测，BF16 / 40 步

| 用例 | 尺寸 | 模型加载 | 生成 | CUDA 峰值分配 |
|---|---|---:|---:|---:|
| 室内场景文生图 | 1344×768 | 202.85 秒 | 53.68 秒 | 36.75 GiB |
| 透明红色茶壶 | 1024×1024 | 186.12 秒 | 52.86 秒 | 36.86 GiB |
| 参考图改为蓝色茶壶 | 1024×1024 | 212.61 秒 | 59.16 秒 | 38.86 GiB |

前两项使用默认的 CPU 加载后移到 CUDA；第三项试验 `device_map="cuda"`，未体现启动优势，交付入口保留前者。每次独立命令都要重新加载，当前普通文生图从模型加载到生成结束约 4 分钟，不能把约 53 秒的生成阶段当作完整命令耗时。表中计时不含 Python 导入和最终 PNG 写入，CUDA 分配也不等于系统总内存。原生 2K 和 10 张参考图的上限尚未实测。

远端完整输出：`/home/admin/qwen-image-2.1-runtime/outputs/acceptance-20260929-164210/`。
本地副本：项目 `outputs/qwen-image-2.1-acceptance/`，包括图片、每张图的参数记录、权重校验凭据及依赖锁定文件。

验收脚本是 `scripts/04_test_benchmark/test_qwen_image_21.sh`。添加 `--pause-idle-qwen` 时，会检查语言模型没有活动请求，再临时暂停它；测试结束或失败后自动恢复并检查健康状态。
