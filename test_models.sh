#!/bin/bash
models=(
  "nvidia/nemotron-3-super-120b-a12b:free"
  "minimax/minimax-m2.5:free"
  "stepfun/step-3.5-flash:free"
  "arcee-ai/trinity-large-preview:free"
  "liquid/lfm-2.5-1.2b-thinking:free"
  "liquid/lfm-2.5-1.2b-instruct:free"
  "nvidia/nemotron-nano-30b-a3b:free"
  "arcee-ai/trinity-mini:free"
  "nvidia/nemotron-nano-12b-v2-vl:free"
  "qwen/qwen3-next-80b-a3b-instruct:free"
  "nvidia/nemotron-nano-9b-v2:free"
  "openai/gpt-oss-120b:free"
  "openai/gpt-oss-20b:free"
  "z-ai/glm-4.5-air:free"
  "qwen/qwen3-coder:free"
  "cognitivecomputations/dolphin-mistral-24b-venice-edition:free"
  "google/gemma-3n-e2b-it:free"
  "google/gemma-3n-e4b-it:free"
  "qwen/qwen3-4b:free"
  "mistralai/mistral-small-3.1-24b-instruct:free"
  "google/gemma-4b-it:free"
  "google/gemma-3-12b-it:free"
  "google/gemma-3-27b-it:free"
  "meta-llama/llama-3.3-70b-instruct:free"
  "meta-llama/llama-3.2-3b-instruct:free"
  "nousresearch/hermes-3-llama-3.1-405b:free"
)

echo "==============================="
echo "OpenRouter 免费模型测试 V2 (官方API列表)"
echo "时间: $(date)"
echo "模型数: ${#models[@]}"
echo "==============================="
echo ""

ok=0
fail=0

for m in "${models[@]}"; do
  resp=$(curl -s -w "\n%{http_code}" \
    https://openrouter.ai/api/v1/chat/completions \
    -H "Authorization: Bearer $OPENROUTER_API_KEY" \
    -H "Content-Type: application/json" \
    -d "{\"model\":\"$m\",\"messages\":[{\"role\":\"user\",\"content\":\"ping\"}],\"max_tokens\":10}")
  code=$(echo "$resp" | tail -1)
  body=$(echo "$resp" | head -n -1)
  if [ "$code" = "200" ]; then
    echo "OK $m"
    ok=$((ok+1))
  else
    err=$(echo "$body" | grep -o '"message":"[^"]*"' | head -1)
    echo "FAIL $m (HTTP $code) $err"
    fail=$((fail+1))
  fi
  sleep 2
done

echo ""
echo "==============================="
echo "结果: OK $ok / FAIL $fail (共 ${#models[@]})"
echo "==============================="
