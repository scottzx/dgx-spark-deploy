#!/usr/bin/env bash
set -e

# ==============================================================================
# NVIDIA DGX Spark - DeepSeek-V4-Flash Q3_K_S 自动化下载与部署脚本
# 适配环境: Ubuntu 24.04 LTS (aarch64) / 128GB Unified Memory / Samsung NVMe SSD
# ==============================================================================

MODEL_DIR="${HOME}/models_cache/DeepSeek-V4-Flash-GGUF"
REPO_ID="unsloth/DeepSeek-V4-Flash-GGUF"
PATTERN="*Q3_K_S*"

echo "=========================================================="
echo "1. 检查并创建高速 NVMe 存储目录"
echo "=========================================================="
mkdir -p "${MODEL_DIR}"
echo "模型存放路径: ${MODEL_DIR}"

echo "=========================================================="
echo "2. 安全兜底：检查是否已配置 NVMe Swap 保护 (防极端内存溢出 OOM)"
echo "=========================================================="
# Q3_K_S 权重约 115GB，接近 121GiB 物理空闲上限，配置 32GB NVMe Swap 可保万无一失
SWAP_TOTAL=$(free -m | awk '/Swap:/ {print $2}')
if [ "${SWAP_TOTAL}" -lt 16384 ]; then
    echo "当前 Swap 较小 (${SWAP_TOTAL}MB)，检测到充足的高速 SSD 空间，正在创建 32GB 应急 Swapfile..."
    sudo fallocate -l 32G /swapfile_spark || sudo dd if=/dev/zero of=/swapfile_spark bs=1G count=32
    sudo chmod 600 /swapfile_spark
    sudo mkswap /swapfile_spark
    sudo swapon /swapfile_spark
    echo "/swapfile_spark none swap sw 0 0" | sudo tee -a /etc/fstab
    echo "✅ 32GB NVMe Swapfile 创建并启用成功！"
else
    echo "✅ 当前 Swap 充足 (${SWAP_TOTAL}MB)，无需额外创建。"
fi

echo "=========================================================="
echo "3. 开始通过 ModelScope 高速拉取 DeepSeek-V4-Flash Q3_K_S"
echo "=========================================================="
export MODELSCOPE_CACHE="${HOME}/models_cache"

# 仅拉取匹配 Q3_K_S 的权重分卷文件
modelscope download \
    --model "${REPO_ID}" \
    --include "${PATTERN}" \
    --local_dir "${MODEL_DIR}"

echo "=========================================================="
echo "✅ 模型文件下载完成！存放于: ${MODEL_DIR}"
echo "=========================================================="
ls -lh "${MODEL_DIR}"
