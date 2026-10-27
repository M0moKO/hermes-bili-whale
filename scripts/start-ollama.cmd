@echo off
REM 手动启动本地视觉后端（Ollama）。本机已禁用开机自启，需要看图前双击本文件。
REM 配置：qwen3-vl:4b @ 16K 上下文（8 GB 显存下 100% GPU，约 15 秒/张）
set OLLAMA_HOST=127.0.0.1:11434
set OLLAMA_CONTEXT_LENGTH=16384
set OLLAMA_KEEP_ALIVE=5m
start "" "%LOCALAPPDATA%\Programs\Ollama\ollama.exe" serve
echo Ollama serve started on 127.0.0.1:11434 (ctx=16384, keep_alive=5m)
