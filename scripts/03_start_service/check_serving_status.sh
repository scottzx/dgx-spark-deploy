#!/usr/bin/env bash
# ==============================================================================
# 模型服务运行状态查询脚本
# ==============================================================================
echo "=========================================================="
echo "当前 GPU 显存与进程状态:"
echo "=========================================================="
nvidia-smi --query-gpu=utilization.gpu,memory.used,memory.total,temperature.gpu --format=csv,noheader
free -h

echo ""
echo "=========================================================="
echo "服务状态检查:"
echo "=========================================================="

QWEN_RUNNING=0
if docker ps --format "{{.Names}}" | grep -q "^qwen3-8-flash-next$"; then
    QWEN_HEALTH=$(curl -s -m 2 http://127.0.0.1:8000/health || echo "connecting")
    echo "🟢 [在线] Qwen 3.8 Flash (Docker: qwen3-8-flash-next)"
    echo "   API 端点: http://0.0.0.0:8000/v1"
    echo "   健康检查: ${QWEN_HEALTH}"
    QWEN_RUNNING=1
else
    echo "⚪ [离线] Qwen 3.8 Flash (容器未运行)"
fi

MINIMAX_RUNNING=0
if pgrep -f '[i]nfer.py --paths /home/admin/sol-spark-runtime/paths.json' >/dev/null 2>&1; then
    echo '🟢 [运行中] Sol-H3-Spark 视频任务'
    echo '   方式：官方 CLI，当前批次复用模型'
    echo '   输出与耗时：本次输出目录中的 results.json'
    MINIMAX_RUNNING=1
elif pgrep -f "sglang.*MiniMax-H3" >/dev/null 2>&1; then
    H3_HEALTH=$(curl -s -m 2 http://127.0.0.1:30010/health || echo "initializing/loading")
    echo "🟢 [在线] MiniMax-H3 (SGLang Lightning, PID: $(pgrep -f "sglang.*MiniMax-H3" | head -n 1))"
    echo "   API 端点: http://0.0.0.0:30010/v1/videos"
    echo "   健康检查: ${H3_HEALTH}"
    echo "   日志文件: /home/admin/h3-lightning/server.log"
    MINIMAX_RUNNING=1
else
    if [[ -f /home/admin/sol-spark-runtime/paths.json && -f /home/admin/sol-spark-runtime/fixed-prompt.pt ]]; then
        echo '⚪ [空闲] Sol-H3-Spark（未运行视频任务）'
    else
        echo '⚪ [准备中] Sol-H3-Spark（路径清单或提示词缓存未就绪）'
    fi
fi

echo "=========================================================="
if [ $QWEN_RUNNING -eq 1 ] && [ $MINIMAX_RUNNING -eq 0 ]; then
    echo "当前活跃模型: Qwen 3.8 Flash"
elif [ $QWEN_RUNNING -eq 0 ] && [ $MINIMAX_RUNNING -eq 1 ]; then
    echo "当前活跃模型: MiniMax-H3"
elif [ $QWEN_RUNNING -eq 1 ] && [ $MINIMAX_RUNNING -eq 1 ]; then
    echo "⚠️ 警告: 检测到两个模型同时在运行，可能导致 128GB 显存超额！"
else
    echo "当前无模型在运行。"
fi
echo "=========================================================="
