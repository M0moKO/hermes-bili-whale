"""养鱼面板的本地小服务（零外部依赖，只绑回环）。

由插件 `bili_whale` 在 register() 时拉起，或单独运行调试：

    python panel_server.py            # 前台跑
    python panel_server.py --test     # 起一下、自检几个 API、退出

设计约束：
- 只监听 127.0.0.1，不对外。
- 绝不返回 cookie：凭据只回昵称 / mid / 是否有效。
- 所有 node 调用一律前台（后台会报 `stdin is not a tty`），带超时。
"""

from __future__ import annotations

import base64
import json
import os
import shutil
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(os.environ.get("BILI_WHALE_HOME") or (Path(os.path.expanduser("~")) / "bili-whale"))
STATE = ROOT / "state"
CONFIG_PATH = STATE / "bili-whale.config.json"
DIARY_PATH = STATE / "whale-diary.md"
LOG_PATH = STATE / "whale-log.jsonl"
QR_PATH = ROOT / "qr-login.png"
CRED_PATH = Path(os.environ.get("USERPROFILE") or os.path.expanduser("~")) / ".bili-ai" / "credentials.json"
HERE = Path(__file__).resolve().parent
PANEL = HERE / "panel.html"

HOST, PORT = "127.0.0.1", 8791
_session_cache: dict = {"at": 0.0, "value": None}
_config_cache: dict = {"at": 0.0, "value": None}


def _node() -> str:
    found = shutil.which("node")
    if found:
        return found
    for cand in (Path(os.environ.get("LOCALAPPDATA", "")) / "hermes" / "tools").glob("node-*/node.exe"):
        return str(cand)
    return "node"


def cli(args: list[str], timeout: int = 40) -> tuple[int, str]:
    """跑 node tools/bili.mjs ...（前台）。"""
    entry = ROOT / "tools" / "bili.mjs"
    argv = [_node(), str(entry), *args]
    env = {**os.environ, "DSH_HOME": str(STATE)}
    try:
        proc = subprocess.run(
            argv, cwd=str(ROOT), env=env, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=timeout,
        )
        return proc.returncode, ((proc.stdout or "") + (proc.stderr or "")).strip()
    except subprocess.TimeoutExpired:
        return 124, f"超时（{timeout}s）"
    except Exception as exc:  # pragma: no cover
        return 1, f"{type(exc).__name__}: {exc}"


def cli_json(args: list[str], timeout: int = 40):
    code, out = cli(args, timeout)
    if not out:
        return None
    start = out.find("{")
    if start < 0:
        return None
    depth, end = 0, -1
    for i, ch in enumerate(out[start:], start):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                end = i + 1
                break
    if end < 0:
        return None
    try:
        return json.loads(out[start:end])
    except Exception:
        return None


def load_config() -> dict:
    try:
        return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def merge(base: dict, over: dict) -> dict:
    out = dict(base)
    for k, v in (over or {}).items():
        out[k] = merge(base.get(k, {}), v) if isinstance(v, dict) and isinstance(base.get(k), dict) else v
    return out


def save_config(patch: dict) -> dict:
    cfg = merge(load_config(), patch or {})
    STATE.mkdir(parents=True, exist_ok=True)
    tmp = CONFIG_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(CONFIG_PATH)
    _config_cache["at"] = 0.0
    return cfg


def account_info() -> dict:
    now = time.time()
    if _session_cache["value"] and now - _session_cache["at"] < 60:
        return _session_cache["value"]
    info: dict = {"valid": CRED_PATH.exists(), "name": "", "mid": "", "raw": ""}
    if CRED_PATH.exists():
        code, out = cli(["session"], timeout=25)
        for line in out.splitlines():
            s = line.strip()
            if s.startswith("账号"):
                info["name"] = s.split(":", 1)[-1].strip()
            elif s.startswith("mid"):
                info["mid"] = s.split(":", 1)[-1].strip()
        info["valid"] = code == 0 and "凭据有效" in out
        info["raw"] = out[:600]
    _session_cache.update(at=now, value=info)
    return info


def diary_text() -> dict:
    out = {"narrative": "", "events": []}
    try:
        out["narrative"] = DIARY_PATH.read_text(encoding="utf-8")[-20000:]
    except Exception:
        out["narrative"] = ""
    try:
        lines = LOG_PATH.read_text(encoding="utf-8").strip().splitlines()[-60:]
        for line in lines:
            try:
                out["events"].append(json.loads(line))
            except Exception:
                continue
    except Exception:
        pass
    return out


def state_payload() -> dict:
    cfg = load_config()
    acct = account_info()
    night = cli_json(["night", "status"], timeout=30) or {}
    quota_txt = cli(["quota", "status"], timeout=30)[1]
    return {
        "ok": True,
        "config": cfg,
        "account": {"valid": acct["valid"], "name": acct["name"], "mid": acct["mid"]},
        "night": night,
        "quota": quota_txt[:1200],
        "diary": diary_text(),
        "paths": {"root": str(ROOT), "config": str(CONFIG_PATH), "diary": str(DIARY_PATH)},
    }


class Handler(BaseHTTPRequestHandler):
    server_version = "biliWhalePanel/0.1"

    def log_message(self, fmt, *args):  # 静音
        return

    def _send(self, body: bytes, ctype: str, code: int = 200) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype + "; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        try:
            self.wfile.write(body)
        except Exception:
            pass

    def _json(self, obj, code: int = 200) -> None:
        self._send(json.dumps(obj, ensure_ascii=False).encode("utf-8"), "application/json", code)

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        qs = parse_qs(urlparse(self.path).query)
        if path in ("/", "/index.html"):
            try:
                self._send(PANEL.read_bytes(), "text/html")
            except Exception as exc:
                self._send(f"panel.html 读不到：{exc}".encode(), "text/plain", 500)
            return
        if path == "/api/state":
            self._json(state_payload())
            return
        if path == "/api/diary":
            which = (qs.get("which") or ["narrative"])[0]
            d = diary_text()
            self._json({"which": which, "narrative": d["narrative"], "events": d["events"]})
            return
        if path == "/api/login/status":
            code, out = cli_login(["--poll-once"])
            self._json({"raw": out[:400], "code": code})
            return
        self._json({"ok": False, "error": "not found"}, 404)

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else b"{}"
        try:
            data = json.loads(body or b"{}")
        except Exception:
            data = {}
        if path == "/api/config":
            try:
                cfg = save_config(data)
                self._json({"ok": True, "config": cfg})
            except Exception as exc:
                self._json({"ok": False, "error": str(exc)}, 500)
            return
        if path == "/api/login":
            code, out = cli_login(["--qr"])
            if QR_PATH.exists():
                b64 = base64.b64encode(QR_PATH.read_bytes()).decode()
                self._json({"ok": True, "image": "data:image/png;base64," + b64, "raw": out[:200]})
            else:
                self._json({"ok": False, "error": out[:300]}, 500)
            return
        if path == "/api/cli":
            allowed = {"feed", "night", "quota", "diary", "session", "deps"}
            cmd = str(data.get("cmd") or "")
            if cmd not in allowed:
                self._json({"ok": False, "error": f"只允许 {sorted(allowed)}"}, 400)
                return
            code, out = cli([cmd, *[str(a) for a in (data.get("args") or [])]], timeout=120)
            self._json({"ok": code == 0, "code": code, "out": out[:6000]})
            return
        self._json({"ok": False, "error": "not found"}, 404)


def cli_login(args: list[str], timeout: int = 60) -> tuple[int, str]:
    """跑 桌面/hermes/bili-whale/login.mjs（不是 bili.mjs）。"""
    argv = [_node(), str(ROOT / "login.mjs"), *args]
    env = {**os.environ, "DSH_HOME": str(STATE)}
    try:
        proc = subprocess.run(
            argv, cwd=str(ROOT), env=env, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=timeout,
        )
        return proc.returncode, ((proc.stdout or "") + (proc.stderr or "")).strip()
    except subprocess.TimeoutExpired:
        return 124, f"超时（{timeout}s）"
    except Exception as exc:
        return 1, f"{type(exc).__name__}: {exc}"


_server: ThreadingHTTPServer | None = None


def start(port: int = PORT) -> ThreadingHTTPServer | None:
    """启动后台服务（幂等）。"""
    global _server
    if _server is not None:
        return _server
    try:
        srv = ThreadingHTTPServer((HOST, port), Handler)
    except OSError:
        return None  # 端口被占：多半已经起过一个
    srv.daemon_threads = True
    threading.Thread(target=srv.serve_forever, name="bili-whale-panel", daemon=True).start()
    _server = srv
    return srv


if __name__ == "__main__":
    srv = start()
    if srv is None:
        print(f"端口 {PORT} 已被占用")
    else:
        print(f"养鱼面板: http://{HOST}:{PORT}/")
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        pass
