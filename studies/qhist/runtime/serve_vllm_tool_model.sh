#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 2 ]]; then
  echo "usage: $0 MODEL_PATH SERVED_MODEL_NAME" >&2
  exit 2
fi

model_path=$1
served_model_name=$2

if [[ ! -f "$model_path/config.json" ]]; then
  echo "model config not found: $model_path/config.json" >&2
  exit 1
fi

export HF_HUB_OFFLINE=1
export TRANSFORMERS_OFFLINE=1
export CUDA_VISIBLE_DEVICES=0
# FlashInfer 0.6.16.post3 的 sampler 能力检测会误判 Blackwell SM 12.0。
# 此开关只禁用 FlashInfer top-k/top-p sampler，不改变 vLLM 的 attention backend。
export VLLM_USE_FLASHINFER_SAMPLER=0

exec .venvs/vllm028/bin/vllm serve "$model_path" \
  --served-model-name "$served_model_name" \
  --dtype bfloat16 \
  --max-model-len 8192 \
  --gpu-memory-utilization 0.75 \
  --host 127.0.0.1 \
  --port 8000 \
  --api-key EMPTY \
  --enable-auto-tool-choice \
  --tool-call-parser hermes
