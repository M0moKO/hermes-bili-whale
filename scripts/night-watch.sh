#!/usr/bin/env bash
# 生物钟观察器 —— 给 Hermes cron 的 monitor 用（0 token 待机）。
#
# 输出必须是确定性的：没到点恒定输出 SLEEP（monitor 输出不变就不唤醒 agent），
# 到点且未处理时输出 WAKE <时刻>（输出变化 → 唤醒 agent 跑「醒来流程」）。
#
# 醒来流程第一步必须是 `night mark`（或等价标记），否则每个 tick 都会重复唤醒。
set -u
ROOT="${BILI_WHALE_HOME:-$HOME/bili-whale}"
export DSH_HOME="$ROOT/state"

RAW=$(cd "$ROOT" && node tools/bili.mjs night status 2>/dev/null)

printf '%s' "$RAW" | node -e '
let buf = ""
process.stdin.on("data", (d) => (buf += d)).on("end", () => {
  let j
  try { j = JSON.parse(buf) } catch { process.stdout.write("SLEEP"); return }
  const st = (j && j.state) || {}
  if (st.fired) return process.stdout.write("SLEEP")
  if (st.action === "skip") return process.stdout.write("SLEEP")
  if (!st.atMs) return process.stdout.write("SLEEP")
  if (Date.now() < Number(st.atMs)) return process.stdout.write("SLEEP")
  process.stdout.write("WAKE " + (st.atText || ""))
})
'
