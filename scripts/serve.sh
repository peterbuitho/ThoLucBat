#!/usr/bin/env bash
# Serve a model with vLLM on 127.0.0.1:8000 under the name "vietpoet".
# Usage: scripts/serve.sh [model path or HF id]   (default: unsloth/Qwen3.5-4B baseline)
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
MODEL="${1:-unsloth/Qwen3.5-4B}"
# Flatpak sandbox: expose the host's libcuda if the loader can't find it.
export LD_LIBRARY_PATH="/run/host/usr/lib/x86_64-linux-gnu:${LD_LIBRARY_PATH:-}"
export VLLM_USE_FLASHINFER_SAMPLER=0  # no nvcc in sandbox; avoid JIT
exec "$ROOT/.venv-server/bin/vllm" serve "$MODEL" \
  --served-model-name vietpoet \
  --host 127.0.0.1 --port 8000 \
  --max-model-len "${VLLM_MAX_LEN:-2048}" \
  --gpu-memory-utilization "${VLLM_GPU_UTIL:-0.85}"
