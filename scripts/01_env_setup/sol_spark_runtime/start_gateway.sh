#!/usr/bin/env bash
set -euo pipefail

runtime=/home/admin/sol-spark-runtime
pkill -f "sol_async_gateway.py" || true
sleep 1

nohup "$runtime/bootstrap-env/bin/python" "$runtime/sol_async_gateway.py" > "$runtime/outputs/gateway.log" 2>&1 &
sleep 2

echo "Sol-H3 Async Gateway started on port 8095 (PID: $(pgrep -f sol_async_gateway.py))"
