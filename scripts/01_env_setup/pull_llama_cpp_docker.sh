#!/usr/bin/env bash
set -u

IMAGE="${LLAMA_CPP_IMAGE:-ghcr.io/ggml-org/llama.cpp:server-cuda13}"
RETRY_DELAY="${RETRY_DELAY:-30}"
attempt=1

while true; do
    echo "[$(date --iso-8601=seconds)] Pull attempt ${attempt}: ${IMAGE}"
    if docker pull "${IMAGE}"; then
        echo "[$(date --iso-8601=seconds)] Pull complete"
        docker image inspect --format 'ID={{.Id}} ARCH={{.Architecture}} OS={{.Os}}' "${IMAGE}"
        exit 0
    fi

    echo "[$(date --iso-8601=seconds)] Pull failed; retrying in ${RETRY_DELAY}s"
    sleep "${RETRY_DELAY}"
    attempt=$((attempt + 1))
done
