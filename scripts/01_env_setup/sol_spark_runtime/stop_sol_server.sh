#!/usr/bin/env bash
echo "Stopping Sol-H3-Spark resident server..."
pkill -f "sol_api_server.py" || true
sleep 2
pkill -9 -f "runtime.worker" || true
pkill -9 -f "stage1-env" || true
pkill -9 -f "stage2-env" || true
docker rm -f $(docker ps -q --filter name=qwen3-8-) 2>/dev/null || true
echo "Sol-H3-Spark resident server stopped cleanly."
