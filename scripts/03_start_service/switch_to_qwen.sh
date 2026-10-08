#!/usr/bin/env bash
set -Eeuo pipefail

# ==============================================================================
# 切换至 Qwen 3.8 Flash (停止 MiniMax / Sol-H3-Spark 释放显存，启动 Qwen 3.8 Flash 常驻服务)
# ==============================================================================
echo "=========================================================="
echo "准备切换至 Qwen 3.8 Flash 服务..."
echo "=========================================================="

# 1. 停止 MiniMax-H3 / Sol-H3-Spark 服务
echo "1. 正在停止 MiniMax / Sol-H3-Spark 相关进程与容器..."

# 1.1 停止 Sol-H3-Spark 常驻 API 服务及 Worker
if pgrep -f "sol_api_server.py" >/dev/null 2>&1 || pgrep -f "runtime.worker" >/dev/null 2>&1; then
    echo "   发现 Sol-H3-Spark 运行中，正在停止..."
    if [[ -x /home/admin/sol-spark-runtime/stop_sol_server.sh ]]; then
        bash /home/admin/sol-spark-runtime/stop_sol_server.sh || true
    else
        pkill -f "sol_api_server.py" || true
        sleep 2
        pkill -9 -f "runtime.worker" || true
        pkill -9 -f "stage1-env" || true
        pkill -9 -f "stage2-env" || true
    fi
fi

# 1.2 清理 Sol-H3 的临时 Qwen Docker 容器
SOL_QWEN_CONTAINERS=$(docker ps -q --filter "name=sol-h3-qwen" 2>/dev/null || true)
if [[ -n "${SOL_QWEN_CONTAINERS}" ]]; then
    echo "   正在移除 Sol-H3 Qwen 临时容器..."
    docker rm -f ${SOL_QWEN_CONTAINERS} >/dev/null 2>&1 || true
fi

# 1.3 停止旧版 SGLang MiniMax-H3
if pgrep -f "sglang.*MiniMax-H3" >/dev/null 2>&1; then
    echo "   停止 SGLang MiniMax-H3 进程..."
    pkill -f "sglang.*MiniMax-H3" || true
fi

rm -f /home/admin/h3-lightning/server.pid 2>/dev/null || true
rm -f /home/admin/sol-spark-runtime/inference.lock 2>/dev/null || true

echo "   等待显存与进程完全释放..."
for i in {1..15}; do
    if ! pgrep -f "sol_api_server|stage1-env|stage2-env|runtime.worker|sglang.*MiniMax" >/dev/null 2>&1; then
        break
    fi
    sleep 1
done
echo "   MiniMax 相关服务已完全停止，显存已释放。"

# 2. 启动 Qwen 3.8 Flash (生产常驻全套服务: Docker 8001 + FIFO Proxy 8000)
echo "2. 正在启动 Qwen 3.8 Flash (qwen3-8-flash-next)..."
if [[ -f /home/admin/start_service_with_proxy.sh ]]; then
    bash /home/admin/start_service_with_proxy.sh
elif docker ps -a --format "{{.Names}}" | grep -q "^qwen3-8-flash-next$"; then
    docker start qwen3-8-flash-next
else
    bash /home/admin/start_qwen3.8_flash_next_docker.sh
fi

echo "3. 等待 Qwen 服务健康检查通过..."
for i in {1..30}; do
    if curl -sf "http://127.0.0.1:8000/health" >/dev/null 2>&1; then
        echo "=========================================================="
        echo "✅ Qwen 3.8 Flash 服务已成功恢复并健康运行！"
        echo "   API 端点: http://0.0.0.0:8000/v1"
        echo "=========================================================="
        docker ps --filter "name=qwen3-8-flash-next"
        exit 0
    fi
    sleep 2
done

echo "⚠️ Qwen 容器已启动，但健康检查尚未通过，可通过 'docker logs -f qwen3-8-flash-next' 查看日志。"
