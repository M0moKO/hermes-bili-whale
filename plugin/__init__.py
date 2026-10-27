"""bili_whale — B 站养鱼工具集（dsh-bili-whale 的 tools/ 在 Hermes 里的封装）。

上游仓库的 ``tools/bili.mjs`` 是一个 38 条命令的 Node CLI（零外部依赖）。这个插件
只做三件事：

1. 把命令按语义收成 8 个工具，避免把 38 个工具塞进每轮上下文；
2. 统一注入 ``DSH_HOME``（指向项目内的 state 目录）与超时；
3. **写操作一律默认干跑**：没有 ``go=true`` 时自动补 ``--dry``，真发必须显式表态。

凭据不经过这里：cookie 由 ``~/.bili-ai/credentials.json`` 提供，插件不读也不打印。
"""

from __future__ import annotations

import importlib.util
import json
import logging
import os
import shutil
import subprocess
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

ROOT = Path(os.environ.get("BILI_WHALE_HOME") or (Path(os.path.expanduser("~")) / "bili-whale"))
ENTRY = ROOT / "tools" / "bili.mjs"
MAX_OUT = 14000
PANEL_PORT = int(os.environ.get("BILI_WHALE_PANEL_PORT") or 8791)


def _node() -> str:
    found = shutil.which("node")
    if found:
        return found
    fallback = Path(os.environ.get("LOCALAPPDATA", "")) / "hermes" / "tools"
    for cand in fallback.glob("node-*/node.exe"):
        return str(cand)
    return "node"


def _run(cmd: str, extra: list[str], timeout: int) -> str:
    if not ENTRY.exists():
        return json.dumps({"ok": False, "error": f"找不到 {ENTRY}（bili-whale tools 未就位）"}, ensure_ascii=False)
    argv = [_node(), str(ENTRY), cmd, *extra]
    env = {**os.environ, "DSH_HOME": str(ROOT / "state")}
    try:
        proc = subprocess.run(
            argv, cwd=str(ROOT), env=env, capture_output=True,
            text=True, encoding="utf-8", errors="replace", timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return json.dumps({"ok": False, "error": f"命令 {cmd} 超时（{timeout}s）。监听类命令请加大 timeout_s"}, ensure_ascii=False)
    except Exception as exc:  # pragma: no cover — defensive
        return json.dumps({"ok": False, "error": f"{type(exc).__name__}: {exc}"}, ensure_ascii=False)
    out = (proc.stdout or "").strip()
    err = (proc.stderr or "").strip()
    body = out if out else "(无输出)"
    if err:
        body += "\n[stderr]\n" + err
    if len(body) > MAX_OUT:
        body = body[:MAX_OUT // 2] + f"\n…（截断，原长 {len(body)} 字）…\n" + body[-MAX_OUT // 2:]
    if proc.returncode not in (0, None):
        body = f"[exit {proc.returncode}]\n" + body
    return body


def _schema(actions: dict[str, str], target_desc: str, write: bool = False) -> dict:
    props: dict = {
        "action": {
            "type": "string",
            "enum": list(actions),
            "description": "；".join(f"{k} = {v}" for k, v in actions.items()),
        },
        "target": {"type": "string", "description": target_desc},
        "args": {
            "type": "array", "items": {"type": "string"},
            "description": '追加的原生命令行参数，例如 ["--top","5"]、["--hours","24"]',
        },
        "timeout_s": {"type": "integer", "description": "超时秒数（默认按命令类型给）"},
    }
    if write:
        props["go"] = {
            "type": "boolean",
            "description": "写操作开关：true = 真的发出去；省略或 false = 干跑（--dry），只打印请求",
        }
    return {"type": "object", "properties": props, "additionalProperties": False}


def _mk(actions: dict[str, tuple[str, list[str]]], write: bool = False, base_timeout: int = 300):
    """把 {action: (cli命令, 固定前置参数)} 变成一个 handler。"""
    def handler(args: dict, **_kw) -> str:
        action = str(args.get("action") or next(iter(actions))).strip()
        spec = actions.get(action)
        if spec is None:
            return json.dumps(
                {"ok": False, "error": f"未知 action={action!r}", "allowed": sorted(actions)}, ensure_ascii=False)
        cmd, pre, *rest = spec
        target_flag = rest[0] if rest else ""
        extra = list(pre)
        target = str(args.get("target") or "").strip()
        if target:
            extra += [target_flag, target] if target_flag else [target]
        for item in args.get("args") or []:
            extra.append(str(item))
        if write:
            extra.append("--go" if args.get("go") is True else "--dry")
        timeout = int(args.get("timeout_s") or base_timeout)
        body = _run(cmd, extra, timeout)
        if write and args.get("go") is not True:
            body = "（干跑：没有发出去。确认无误后传 go=true 才真发）\n" + body
        return body
    return handler


# —— 工具定义（38 条原生命令全覆盖）——

DOCTOR = {
    "session": ("session", [], ),
    "deps": ("deps", []),
    "selftest": ("selftest", []),
    "traffic": ("traffic", []),
}

VERIFY = {
    "thread": ("thread", []),
    "check-comment": ("check-comment", []),
    "check-dynamic": ("check-dynamic", []),
    "check-mention": ("check-mention", []),
    "recon": ("recon", []),
    "watch": ("watch", []),
}

READ = {
    "video": ("video", []),
    "subtitles": ("subtitles", []),
    "comments": ("comments", []),
    "feed": ("feed", []),
    "covers": ("covers", []),
    "ai-share": ("ai-share", []),
}

LOOKUP = {
    "search": ("search", []),
    "whois": ("whois", []),
    "likes": ("likes", []),
}

STATE = {
    "diary": ("diary", []),
    "night": ("night", []),
    "quota": ("quota", []),
    "notify": ("notify", []),
}

LISTEN = {
    "comment-await": ("comment-await", []),
    "comment-digest": ("comment-digest", []),
    "dm-await": ("dm-await", []),
    "danmaku-await": ("await", []),
}

WRITE = {
    "comment": ("comment", [], "--oid"),
    "dm": ("dm", []),
    "dynamic": ("dynamic", []),
    "dynamic-image": ("dynamic-image", []),
    "dynamic-edit": ("dynamic-edit", []),
    "danmaku": ("danmaku", []),
    "fav": ("fav", []),
    "reply-draft": ("reply-draft", []),
    "comment-del": ("comment-del", []),
}

def _panel_handler(args: dict, **_kw) -> str:
    """返回面板地址；真的打开要由 agent 调 desktop_preview。"""
    url = f"http://127.0.0.1:{PANEL_PORT}/"
    return json.dumps(
        {"ok": True, "url": url, "hint": "用 desktop_preview(action='open', url=...) 打开它"},
        ensure_ascii=False)


_TOOLS = (
    ("bili_doctor", _schema({k: k for k in DOCTOR}, "无（诊断命令不需要 target）"),
     _mk({k: (v[0], v[1]) for k, v in DOCTOR.items()}), "🩺",
     "B站养鱼诊断：session=凭据属于哪个号，deps=依赖体检，selftest=启动测试，traffic=请求保护/限流状态。先跑这个再谈别的。"),

    ("bili_verify", _schema({k: k for k in VERIFY}, "评论 rpid / 动态 id / BV，视 action 而定；用 args 传 --aid/--root 等"),
     _mk({k: (v[0], v[1]) for k, v in VERIFY.items()}), "🔍",
     "写后复核与侦查：thread=导出楼中楼，check-comment=按 rpid 复核评论，check-dynamic=看动态结构，check-mention=确认 @ 真提及，recon=发评论前侦查，watch=盯楼中楼新回复。"),

    ("bili_read", _schema({k: k for k in READ}, "BV 号或关键词（feed 可不填）"),
     _mk({k: (v[0], v[1]) for k, v in READ.items()}, base_timeout=420), "📄",
     "读内容（不下载视频）：video=读简介/字幕/弹幕/评论还原内容，subtitles=官方字幕全文，comments=热评，feed=按日记喜好捞候选，covers=抓封面，ai-share=分享前评论抽样。"),

    ("bili_debrief", _schema({"debrief": "debrief"}, "BV 号（支持 ?p=N 与 b23.tv 短链）"),
     _mk({"debrief": ("debrief", [])}, base_timeout=600), "🎬",
     "看懂一条视频（一条龙）：封面+简介+官方字幕+弹幕热区+热评+画面抽帧。输出证据包，随后用本地视觉模型逐张读图。"),

    ("bili_lookup", _schema({k: k for k in LOOKUP}, "search=关键词；whois=mid；likes 可留空"),
     _mk({k: (v[0], v[1]) for k, v in LOOKUP.items()}), "🔎",
     "查人查赞：search=关键词搜视频，whois=按 mid 查昵称（@ 人前先核准名字），likes=谁赞了她（--hours 24）。"),

    ("bili_state", _schema({k: k for k in STATE}, "diary/night/quota/notify 的子命令，如 show / plan / status"),
     _mk({k: (v[0], v[1]) for k, v in STATE.items()}), "📔",
     "她的状态：diary=日记（show/log/tail），night=生物钟（plan/clock/status/mark），quota=限额闸（status/check/record/set），notify=通知分发。"),

    ("bili_listen", _schema({k: k for k in LISTEN}, "无（监听类靠 args 传 --minutes/--interval）"),
     _mk({k: (v[0], v[1]) for k, v in LISTEN.items()}, base_timeout=600), "👂",
     "廉价守候（0 token，命中才叫醒 agent）：comment-await=等评论回复，dm-await=等私信（只认主人），danmaku-await=等直播间弹幕，comment-digest=汇总今天谁找过她。监听类务必给 timeout_s。"),

    ("bili_write", _schema({k: k for k in WRITE}, "按 action：评论=BV、私信=文本、动态/弹幕=内容", write=True),
     _mk({k: (v[0], v[1]) for k, v in WRITE.items()}, write=True), "✍️",
     "写操作（危险）：comment=发评论，dm=私信，dynamic/dynamic-image/dynamic-edit=动态，danmaku=直播间弹幕，fav=收藏，reply-draft=待审回复队列，comment-del=删自己的评论。**默认干跑**，确认后传 go=true 才真发；发完必须用 bili_verify 回读复核。"),

    ("bili_panel", {"type": "object", "properties": {}, "additionalProperties": False},
     _panel_handler, "🖥️",
     "养鱼面板：返回本地面板地址（127.0.0.1:8791）。用 desktop_preview 打开后可以改身份/作息/限额、看日记与今晚计划、重新扫码登录。"),
)


_panel_mod = None


def _start_panel() -> None:
    """拉起面板小服务（幂等，失败不影响插件加载）。"""
    global _panel_mod
    try:
        path = Path(__file__).with_name("panel_server.py")
        spec = importlib.util.spec_from_file_location("bili_whale_panel_server", path)
        module = importlib.util.module_from_spec(spec)
        sys.modules.setdefault(spec.name, module)
        spec.loader.exec_module(module)  # type: ignore[union-attr]
        _panel_mod = module
        server = module.start(PANEL_PORT)
        if server is None:
            logger.info("bili_whale: 面板端口 %s 被占用（可能已启动），跳过", PANEL_PORT)
        else:
            logger.info("bili_whale: 养鱼面板已启动 http://127.0.0.1:%s/", PANEL_PORT)
    except Exception as exc:  # pragma: no cover — 面板挂了不能拖垮工具
        logger.warning("bili_whale: 面板启动失败：%s", exc)


def _slash_bili(raw_args: str = "") -> str:
    """`/bili` 斜杠命令：状态速览；`/bili panel` 给面板地址。"""
    arg = (raw_args or "").strip().lower()
    url = f"http://127.0.0.1:{PANEL_PORT}/"
    if arg in ("panel", "open", "面板", "ui"):
        return (
            f"🖥️ 养鱼面板：{url}\n"
            "想要它开在聊天旁边，跟我说一句「打开养鱼面板」，我用 desktop_preview 摆出来。")
    if _panel_mod is None:
        return "🐟 养鱼：面板服务没起来（端口被占或启动失败），先看 Hermes 日志。"
    try:
        st = _panel_mod.state_payload()
    except Exception as exc:
        return f"🐟 养鱼：读取状态失败（{type(exc).__name__}: {exc}）"
    acct = st.get("account") or {}
    night = (st.get("night") or {}).get("state") or {}
    cfg = st.get("config") or {}
    quota_line = (st.get("quota") or "").splitlines()[0] if st.get("quota") else "—"
    fired = night.get("fired")
    action = night.get("action")
    if fired:
        plan = "今天已经醒过"
    elif action == "skip":
        plan = "今天不想看（30% 那枚骰子）"
    else:
        plan = f"下次醒来 {night.get('atText') or '待定'}"
    persona = (cfg.get("persona") or {}).get("name") or ""
    owner = ((cfg.get("owner") or {}).get("name")) or "—"
    return "\n".join([
        f"🐟 {persona} 速览",
        f"· 她是：{(acct.get('name') or '未登录')}（mid {acct.get('mid') or '—'}）",
        f"· 主人：{owner}",
        f"· 今晚：{plan}",
        f"· {quota_line.strip()}",
        f"· 面板：{url}",
    ])


def register(ctx) -> None:
    """插件加载时注册 9 个工具 + `/bili` 斜杠命令，并拉起养鱼面板。"""
    _start_panel()
    try:
        ctx.register_command(
            "bili", _slash_bili,
            description="养鱼面板与状态速览（/bili 看状态，/bili panel 给面板地址）",
            args_hint="[panel|status]",
        )
    except Exception as exc:  # pragma: no cover
        logger.warning("bili_whale: /bili 命令注册失败：%s", exc)
    for name, schema, handler, emoji, description in _TOOLS:
        ctx.register_tool(
            name=name, toolset="bili", schema=schema, handler=handler,
            description=description, emoji=emoji,
        )
