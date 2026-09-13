#!/usr/bin/env bash
set -Eeuo pipefail

SRC_DIR="${HOME}/src/llama.cpp"
BUILD_DIR="${SRC_DIR}/build"
export PATH="/usr/local/cuda/bin:${HOME}/.local/bin:${PATH}"

mkdir -p "${HOME}/src" "${HOME}/.local/bin"

if [[ -d "${SRC_DIR}" ]] && ! git -C "${SRC_DIR}" rev-parse --verify HEAD >/dev/null 2>&1; then
    mv "${SRC_DIR}" "${SRC_DIR}.incomplete.$(date +%Y%m%d-%H%M%S)"
fi

if [[ ! -d "${SRC_DIR}/.git" ]]; then
    git clone --depth 1 https://github.com/ggml-org/llama.cpp.git "${SRC_DIR}"
else
    git -C "${SRC_DIR}" pull --ff-only
fi

echo "Building llama.cpp commit $(git -C "${SRC_DIR}" rev-parse HEAD)"

cmake -S "${SRC_DIR}" -B "${BUILD_DIR}" \
    -DGGML_CUDA=ON \
    -DGGML_CUDA_FA=ON \
    -DGGML_CUDA_GRAPHS=ON \
    -DGGML_NATIVE=ON \
    -DCMAKE_CUDA_ARCHITECTURES=121 \
    -DCMAKE_BUILD_TYPE=Release \
    -DLLAMA_CURL=OFF

cmake --build "${BUILD_DIR}" --config Release -j "$(nproc)"

ln -sfn "${BUILD_DIR}/bin/llama-server" "${HOME}/.local/bin/llama-server"
ln -sfn "${BUILD_DIR}/bin/llama-cli" "${HOME}/.local/bin/llama-cli"

"${HOME}/.local/bin/llama-server" --version
