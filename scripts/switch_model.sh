#!/usr/bin/env bash
# Switch the local vLLM server to another fine-tuned model (home / localhost use only).
#   scripts/switch_model.sh list            show the models and which one is running
#   scripts/switch_model.sh 4b|9b|gemma     stop the current model, load this one, wait until ready
#   scripts/switch_model.sh stop            stop the server (frees the GPU, e.g. before training)
#   scripts/switch_model.sh status
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
case "${1:-status}" in
  list|status|stop) exec "$ROOT/.venv/bin/python" -m app.serving "$1" ;;
  *) exec "$ROOT/.venv/bin/python" -m app.serving switch "$1" ;;
esac
