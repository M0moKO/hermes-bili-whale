#!/usr/bin/env bash
# 确保本地视觉后端在跑（幂等）。看图之前跑它：已起则秒回，未起则拉起并等就绪。
# 配置：qwen3-vl:4b @ 16K 上下文（8 GB 显存下 100% GPU，约 15 秒/张）
set -u
URL="http://127.0.0.1:11434/api/version"
EXE="C:\\Users\\PC\\AppData\\Local\\Programs\\Ollama\\ollama.exe"

if curl -s --max-time 2 "$URL" >/dev/null 2>&1; then
  echo "ALIVE"
  exit 0
fi

powershell -NoProfile -Command "\$env:OLLAMA_HOST='127.0.0.1:11434'; \$env:OLLAMA_CONTEXT_LENGTH='16384'; \$env:OLLAMA_KEEP_ALIVE='5m'; Start-Process -FilePath '$EXE' -ArgumentList 'serve' -WindowStyle Hidden" >/dev/null 2>&1

for _ in $(seq 1 25); do
  sleep 1
  if curl -s --max-time 2 "$URL" >/dev/null 2>&1; then
    echo "STARTED"
    exit 0
  fi
done

echo "FAILED: ollama serve 未能在 25 秒内应答"
exit 1
