#!/usr/bin/env bash
# ==============================================================================
# MiniMax-H3 模型下载夜间自动守护/断点续传脚本
# ==============================================================================
LOG_FILE="/home/admin/logs/download_minimax_h3.log"
MARKER="/home/admin/models_cache/MiniMax-H3/.download_complete"
MODEL_DIR="/home/admin/models_cache/MiniMax-H3"
MODELSCOPE_BIN="/home/admin/.local/bin/modelscope"

while true; do
    if [[ -f "$MARKER" ]]; then
        echo "[$(date +'%Y-%m-%d %H:%M:%S')] ✅ 守护进程检测到下载已全部完成。" >> "$LOG_FILE"
        break
    fi

    if ! pgrep -f "modelscope download MiniMax/MiniMax-H3" > /dev/null; then
        echo "[$(date +'%Y-%m-%d %H:%M:%S')] ⚠️ 未检测到下载进程，正在启动断点续传..." >> "$LOG_FILE"
        if "$MODELSCOPE_BIN" download MiniMax/MiniMax-H3 --local-dir "$MODEL_DIR" --max-workers 8 >> "$LOG_FILE" 2>&1; then
            touch "$MARKER"
            echo "[$(date +'%Y-%m-%d %H:%M:%S')] 🎉 MiniMax-H3 全量模型下载成功完成！" >> "$LOG_FILE"
            break
        else
            echo "[$(date +'%Y-%m-%d %H:%M:%S')] ❌ 阶段性传输中断，15秒后自动重试续传..." >> "$LOG_FILE"
            sleep 15
        fi
    fi
    sleep 30
done
