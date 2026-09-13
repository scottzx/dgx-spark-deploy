#!/usr/bin/env bash
set -Eeuo pipefail

# ==============================================================================
# NVIDIA DGX Spark - Qwen3.8 Flash-Next 500 会话 FIFO 生产全套拉起脚本
# 架构:
#   - 底层引擎: llama-server (Docker) 监听 8001 端口, 挂载 NVMe /slots
#   - 前端代理: session_fifo_proxy.py 监听 8000 端口, 自动管理 500 会话 FIFO
# ==============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROXY_SCRIPT="${HOME}/session_fifo_proxy.py"
PYTHON_BIN="${HOME}/envs/proxy-env/bin/python3"
LLAMA_PORT="8001"
CLIENT_PORT="8000"

echo "=========================================================="
echo "1. 重启底层 llama-server 容器 (切换至内部端口 ${LLAMA_PORT})..."
echo "=========================================================="
PORT="${LLAMA_PORT}" bash "${HOME}/start_qwen3.8_flash_next_docker.sh"

echo "=========================================================="
echo "2. 停止旧的 Proxy 守护进程 (如有)..."
echo "=========================================================="
pkill -f "session_fifo_proxy.py" 2>/dev/null || true
sleep 1

echo "=========================================================="
echo "3. 启动 500 会话 FIFO 智能调度代理 (监听对外端口 ${CLIENT_PORT})..."
echo "=========================================================="
BACKEND_URL="http://127.0.0.1:${LLAMA_PORT}" \
PROXY_PORT="${CLIENT_PORT}" \
SLOT_CACHE_DIR="${HOME}/slot_cache" \
MAX_SESSIONS=500 \
nohup "${PYTHON_BIN}" "${PROXY_SCRIPT}" > "${HOME}/proxy.log" 2>&1 &

sleep 2

# 健康检查
for i in {1..15}; do
    if curl -sf "http://127.0.0.1:${CLIENT_PORT}/health" >/dev/null 2>&1; then
        echo "=========================================================="
        echo "✅ 全套生产服务启动成功！"
        echo "客户端接口 (零感知): http://0.0.0.0:${CLIENT_PORT}/v1"
        echo "FIFO 存储队列目录:   ${HOME}/slot_cache (上限 500 个会话快照)"
        echo "代理日志查看:        tail -f ${HOME}/proxy.log"
        echo "=========================================================="
        exit 0
    fi
    sleep 1
done

echo "⚠️ Proxy 仍在初始化中，请查看日志: cat ${HOME}/proxy.log"
