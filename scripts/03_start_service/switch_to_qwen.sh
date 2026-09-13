#!/usr/bin/env bash
set -Eeuo pipefail

# Keep language-model startup exclusive with the Sol-H3-Spark batch.
if [[ -d /home/admin/sol-spark-runtime ]]; then
    exec 9>/home/admin/sol-spark-runtime/inference.lock
    if ! flock -n 9; then
        echo 'Sol-H3-Spark 正在生成视频；请等待任务完成，或在其运行终端按 Ctrl+C 结束后再切换。' >&2
        exit 1
    fi
fi

# ==============================================================================
# 切换至 Qwen 3.8 Flash (停止 MiniMax-H3 释放显存，启动 Qwen 3.8 Flash)
# ==============================================================================
echo "=========================================================="
echo "准备切换至 Qwen 3.8 Flash 服务..."
echo "=========================================================="

# 1. 停止 MiniMax-H3 服务
echo "1. 正在停止 MiniMax-H3 进程..."
if pgrep -f "sglang.*MiniMax-H3" >/dev/null 2>&1; then
    pkill -f "sglang.*MiniMax-H3" || true
    echo "   已发送停止信号，等待显存完全释放..."
    for i in {1..15}; do
        if ! pgrep -f "sglang.*MiniMax-H3" >/dev/null 2>&1; then
            break
        fi
        sleep 1
    done
    rm -f /home/admin/h3-lightning/server.pid
    echo "   MiniMax-H3 已停止。"
else
    echo "   MiniMax-H3 当前未在运行。"
fi

# 2. 启动 Qwen 3.8 Flash Docker 容器
echo "2. 正在启动 Qwen 3.8 Flash (qwen3-8-flash-next)..."
if docker ps -a --format "{{.Names}}" | grep -q "^qwen3-8-flash-next$"; then
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
