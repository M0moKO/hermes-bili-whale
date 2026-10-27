# hermes-bili-whale

把 [DeepSeek Harness 的 bili-whale](https://github.com/Alterssss/dsh-bili-whale)（「养一条会自己刷 B 站的鱼」）
搬进 **Hermes Agent** 的适配层：9 个工具 + 一个能改配置的网页面板 + Hermes 侧栏入口 +
「自己按生物钟醒来」的 cron 骨架。

> **本仓库不含上游的 `tools/` 与 `bv.py`。** 那是原作者的作品，请按 [安装](#安装) 一节从上游获取。
> 这里只有「让它跑在 Hermes 里」的那一层胶水。

---

## English overview

`hermes-bili-whale` is an **adapter layer** that ports the "keep a fish that browses Bilibili for
you" idea from [DeepSeek Harness](https://github.com/deepseek-ai/deepseek-harness) to
**Hermes Agent**. It ships **no upstream code** — you install the upstream CLI yourself; this
repository is the glue.

What you get:

- **9 Hermes tools** wrapping 39 upstream CLI commands. Read/write are split: every write action
  (`comment`, `dm`, `dynamic`, `danmaku`, `fav`, …) defaults to `--dry` and only fires with an
  explicit `go=true`.
- **A localhost panel** (`127.0.0.1:8791`, Python stdlib only) for persona, schedule, quota,
  diary viewing and QR re-login. It never returns cookies — only nickname / uid / login validity.
- **A desktop runtime plugin** that adds one sidebar row plus a full page inside the Hermes
  desktop app (`sidebar.nav` + `routes` contributions, loaded from
  `$HERMES_HOME/desktop-plugins/`, no build step, no npm).
- **A two-stage QR login CLI** (`--qr` → `--poll`), credentials written to
  `~/.bili-ai/credentials.json` with mode 600.
- **A zero-token cron monitor**: the wake-up probe prints a stable `SLEEP` line until the
  schedule actually fires, so an idle day costs nothing.

Requirements: Hermes Agent (desktop), Node ≥ 22, Python ≥ 3.10, ffmpeg/ffprobe, and a
**throwaway Bilibili account** — not your main one.

Upstream (MIT, not redistributed here): [Alterssss/dsh-bili-whale](https://github.com/Alterssss/dsh-bili-whale)
— see [NOTICE](NOTICE) for the full attribution and what this layer changed.

License: MIT.

---

## 它做什么

养鱼的核心是**克制**，不是刷量：

- **自己醒**：在你设的时段里随机时刻醒来（默认每晚 20:00–24:00 一次），3 成概率「今天不想看」
- **真看懂**：字幕 / 弹幕热区 / 热评 / 画面抽帧多路互补，不是关键词搜索
- **最多 @ 你 3 次/天**：评分卡不到线就一条都不发——这是合法结果，不是失败
- **两本日记**：一本给你看，一本她自己留着
- **会衰减**：连续几天没回应，分享额度逐天收紧

本适配层负责：把上面这些包成 Hermes 工具、给一个面板改参数、在 Hermes 侧栏挂一个入口、
用 cron 的 `monitor` 模式让「待机」真正零 token。

## 前置要求

| 项 | 版本 | 说明 |
|---|---|---|
| Hermes Agent | 桌面版 | 需要 `plugins/` 目录与 `desktop-plugins/` 运行时插件支持 |
| Node.js | ≥ 22 | 上游 `tools/bili.mjs` 是纯 Node ESM |
| Python | ≥ 3.10 | 插件与面板服务只用标准库 |
| ffmpeg / ffprobe | 任意新版 | 抽帧 |
| 上游 bili-whale | — | `tools/` 必须存在，见下 |
| 一个 B 站**小号** | — | 别用主号。默认值就是替新号挡风控的 |

## 安装

**Windows 一键装**（推荐，会顺带把上游 `tools/` 克隆到 `~/bili-whale`）：

```powershell
.\install.ps1 -CloneUpstream
```

不加 `-CloneUpstream` 就只装适配层，上游你自己放。下面是手工五步（等价于脚本做的事）。

### 1) 取上游 tools

```bash
git clone https://github.com/Alterssss/dsh-bili-whale.git
mkdir -p ~/bili-whale && cp -r dsh-bili-whale/tools ~/bili-whale/
```

（Windows 上 `~` 是 `%USERPROFILE%`；也可以用环境变量 `BILI_WHALE_HOME` 指到别处。）

### 2) 装 Python 插件

```bash
cp -r plugin "$LOCALAPPDATA/hermes/plugins/bili_whale"     # Windows
# cp -r plugin ~/.hermes/plugins/bili_whale                  # Linux/macOS
printf 'Y\n' | hermes plugins enable bili_whale
```

装完会得到 9 个工具（`bili_doctor` / `bili_read` / `bili_debrief` / `bili_write` …）和 `/bili` 斜杠命令。
**要重启 Hermes 或开新会话**才会挂上。

### 3) 装桌面侧栏入口

```bash
cp -r desktop-plugin "$LOCALAPPDATA/hermes/desktop-plugins/bili-whale"
```

重启 Hermes 后，侧栏「技能与工具」那一排会多一行 **养鱼**，点进去是整页面板。

### 4) 登录小号

```bash
cd ~/bili-whale && node "$OLDPWD/scripts/login.mjs" --qr    # 生成二维码
node "$OLDPWD/scripts/login.mjs" --poll                     # 扫码后轮询（或面板里点「重新扫码」）
```

凭据只写进 `~/.bili-ai/credentials.json`，**不经过任何服务端，也不打印**。

### 5) 接上「自己醒」（可选）

1. 把 `scripts/night-watch.sh` 放进 `%LOCALAPPDATA%/hermes/scripts/`（Hermes cron 的 monitor 只接受该目录下的文件名）
2. 建一个 cron：`schedule=every 10m`，`monitor=bili-whale-night.sh`，prompt 见 `docs/cron-prompt.md`

`monitor` 输出不变时**不会唤醒模型**（零 token 待机），只有到点才叫醒 agent。

## 面板

面板是 `plugin/panel_server.py` 起的本地小服务，只绑 `127.0.0.1:8791`：

- `GET /api/state` 身份 / 登录状态 / 今晚计划 / 今日配额 / 日记
- `POST /api/config` 写回 `bili-whale.config.json`
- `POST /api/cli` **只读白名单**（deps/diary/feed/night/quota/session），未知命令 400
- 绝不返回 cookie（只回昵称 / mid / 是否有效）

端口可用 `BILI_WHALE_PANEL_PORT` 改。

## 梗库

`memes/default.json`（46 条：31 通用 + 8 技术向 + 7 私房），`scripts/memes.mjs` 负责查：

```bash
node scripts/memes.mjs scan "<弹幕/热评/字幕文本>"   # 找出可接的梗
node scripts/memes.mjs lookup 绷不住                  # 精确查一条
node scripts/memes.mjs list                           # 看词库
```

规矩（照社区踩过的坑定的）：**只收两字以上、只做字面匹配、一条评论最多接 1 个、没命中就不接**。
单字词条（典、急、乐）一律不收——它们做包含匹配会把「经典老图」「别着急」误接成玩笑，
**误接梗比接不上尴尬得多**。完整理由见 [docs/human-voice.md](docs/human-voice.md) 的「接梗」一节。

## 已知限制

- **`vision_analyze` 可能不走本地视觉**。本仓库不绑定视觉模型；如果你像我们一样把
  `auxiliary.vision` 指向本地 Ollama，注意 Hermes 有时会忽略 `base_url` 打到云厂商。
  稳妥做法：用 MCP 视觉桥（如 `vision-bridge-mcp`）并把 `*_BASE_URL` 指向本地端点。
- 上游 `rapidocr_onnxruntime` 声明 `requires_python <3.13`，Python 3.14 上装不上 → 画面 OCR 这一路缺失。
- 匿名状态拿不到官方字幕；要字幕需 `BILI_SESSDATA`，否则走本地 ASR（首次要下模型）。
- 评论监听默认**关**（每 60 秒一次请求，一天 1440 次，小号扛不住）。想过风控就别急着开。
- 抽帧是稀疏采样，短暂事件会漏；480px 的四宫格里小字读不清。

## 上游与致谢

**本项目赖以成立的全部核心能力来自上游，作者是别人。** 详见 [NOTICE](NOTICE)。

- [Alterssss/dsh-bili-whale](https://github.com/Alterssss/dsh-bili-whale) — `tools/`（29 条命令）、配置结构、生物钟与限额的语义
- [icyaaaww/dsh-bili-vision](https://github.com/icyaaaww/dsh-bili-vision) — `bv.py`（证据化抽帧/字幕/覆盖率）
- DeepSeek Harness 的插件生态给了这套设计最初的形状

## 许可

本仓库的适配层代码：**MIT**（见 [LICENSE](LICENSE)）。
上游代码按各自仓库的许可（均声明 MIT），本仓库不再分发它们。
