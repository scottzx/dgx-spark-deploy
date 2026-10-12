#!/usr/bin/env bash
# ==============================================================================
# 测试 Spark 上的 llama-server 本地 OpenAI 兼容 API 连通性与流式输出
# ==============================================================================
set -euo pipefail

BASE_URL="${BASE_URL:-http://127.0.0.1:8000}"
MODEL_NAME="${MODEL_NAME:-Qwen3.8-27B-Q8_0}"

echo "1. 检查健康状态 /health..."
curl -s "${BASE_URL}/health" || echo "服务尚未就绪"
echo ""

echo "2. 获取已加载模型列表 /v1/models..."
curl -s "${BASE_URL}/v1/models" || true
echo -e "\n"

echo "3. 向 ${MODEL_NAME} 发送测试对话请求..."
curl -s -N "${BASE_URL}/v1/chat/completions" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer no-key" \
  -d '{
    "model": "'"${MODEL_NAME}"'",
    "messages": [
      {"role": "system", "content": "你是由通义千问团队研发的大型多模态语言模型，当前正运行在客户私有化的 NVIDIA DGX Spark 个人超算上。"},
      {"role": "user", "content": "请用一段简短精炼的话做自我介绍，并说明你当前在 GB10 统一显存下的推理运行优势。"}
    ],
    "temperature": 0.7,
    "max_tokens": 512,
    "stream": true
  }'
echo ""
