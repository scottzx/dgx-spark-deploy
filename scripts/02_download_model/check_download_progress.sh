#!/usr/bin/env bash
echo "=== MiniMax-H3 下载进度监控 ==="
echo "时间: $(date "+%Y-%m-%d %H:%M:%S")"
echo "--- 进程状态 ---"
ps aux | grep -E "modelscope download|auto_resume" | grep -v grep || echo "下载进程未运行"
echo "--- 磁盘已用/剩余 ---"
df -h /home/admin | tail -n 1 | awk '{print "总空间: " $2 ", 已用: " $3 ", 可用: " $4}'
echo "--- 当前模型缓存目录大小 ---"
du -sh /home/admin/models_cache/MiniMax-H3 2>/dev/null || echo "0B"
echo "--- 各子模块大小 ---"
du -sh /home/admin/models_cache/MiniMax-H3/* 2>/dev/null
echo "--- 最新下载日志 (后 15 行) ---"
tail -n 15 /home/admin/logs/download_minimax_h3.log 2>/dev/null
