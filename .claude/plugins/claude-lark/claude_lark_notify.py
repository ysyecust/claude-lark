#!/usr/bin/env python3
"""Claude Code → Lark (飞书) notification hook.

Zero external dependencies — uses only Python stdlib.
Reads Claude Code hook event from stdin, parses the session transcript
for rich stats, and sends an interactive card to the configured Lark user.

Config: ~/.config/claude-lark/config.json
"""

from __future__ import annotations

import json
import os
import platform
import subprocess
import sys
import time
import traceback
import urllib.error
import urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path

# ── Paths ────────────────────────────────────────────────────────────
CONFIG_DIR = Path.home() / ".config" / "claude-lark"
CONFIG_PATH = CONFIG_DIR / "config.json"
TOKEN_CACHE_PATH = CONFIG_DIR / ".token_cache"
DEBUG_LOG_PATH = CONFIG_DIR / "debug.log"

# ── Debug logging ────────────────────────────────────────────────────
_DEBUG = os.environ.get("CLAUDE_LARK_DEBUG", "").strip() in ("1", "true", "yes")


def _debug_log(msg: str) -> None:
    """Write a debug message to the log file (only when CLAUDE_LARK_DEBUG=1)."""
    if not _DEBUG:
        return
    try:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        with open(DEBUG_LOG_PATH, "a", encoding="utf-8") as f:
            ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            f.write(f"[{ts}] {msg}\n")
    except OSError:
        pass

# ── Lark API ─────────────────────────────────────────────────────────
LARK_TOKEN_URL = (
    "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal/"
)
LARK_MESSAGE_URL = "https://open.feishu.cn/open-apis/im/v1/messages"

# ── Constants ────────────────────────────────────────────────────────
HTTP_TIMEOUT = 10
TOKEN_REFRESH_BUFFER = 300
DEFAULT_EVENTS = ["Stop", "Notification"]

# ── Config & stdin ───────────────────────────────────────────────────


def _load_config() -> dict | None:
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        if not all(cfg.get(k) for k in ("app_id", "app_secret", "open_id")):
            _debug_log(f"Config incomplete: {CONFIG_PATH}")
            return None
        _debug_log(f"Config loaded: app_id={cfg['app_id']}, open_id={cfg['open_id']}")
        return cfg
    except (FileNotFoundError, json.JSONDecodeError, KeyError) as e:
        _debug_log(f"Config load failed: {e}")
        return None


def _read_stdin() -> dict:
    try:
        if sys.stdin.isatty():
            _debug_log("stdin is a tty, no event data")
            return {}
        raw = sys.stdin.read()
        event = json.loads(raw) if raw.strip() else {}
        _debug_log(f"Event received: {event.get('hook_event_name', '?')}, cwd={event.get('cwd', '?')}")
        return event
    except (json.JSONDecodeError, IOError) as e:
        _debug_log(f"stdin read failed: {e}")
        return {}


# ── Token management ────────────────────────────────────────────────


def _get_cached_token() -> str | None:
    try:
        with open(TOKEN_CACHE_PATH, "r") as f:
            cache = json.load(f)
        if cache.get("expires_at", 0) > time.time() + TOKEN_REFRESH_BUFFER:
            return cache.get("token")
    except (FileNotFoundError, json.JSONDecodeError, KeyError):
        pass
    return None


def _save_token_cache(token: str, expires_in: int) -> None:
    try:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        with open(TOKEN_CACHE_PATH, "w") as f:
            json.dump({"token": token, "expires_at": time.time() + expires_in}, f)
    except OSError:
        pass


def _fetch_tenant_token(app_id: str, app_secret: str) -> str | None:
    payload = json.dumps({"app_id": app_id, "app_secret": app_secret}).encode()
    req = urllib.request.Request(
        LARK_TOKEN_URL, data=payload,
        headers={"Content-Type": "application/json"}, method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
            data = json.loads(resp.read())
        if data.get("code") != 0:
            _debug_log(f"Token fetch failed: code={data.get('code')}, msg={data.get('msg')}")
            return None
        token = data.get("tenant_access_token", "")
        if token:
            _save_token_cache(token, data.get("expire", 7200))
            _debug_log("Token fetched and cached")
        return token or None
    except (urllib.error.URLError, json.JSONDecodeError, OSError) as e:
        _debug_log(f"Token fetch error: {e}")
        return None


def get_token(app_id: str, app_secret: str) -> str | None:
    return _get_cached_token() or _fetch_tenant_token(app_id, app_secret)


# ── Transcript parsing ──────────────────────────────────────────────


def _parse_transcript(path: str) -> dict:
    """Parse session transcript JSONL for rich statistics."""
    stats = {
        "total_output_tokens": 0,
        "total_tool_calls": 0,
        "total_turns": 0,
        "total_agents": 0,
        "agents": [],          # all agents in session
        "turn_agents": [],     # agents spawned since last user msg
        "last_user_ts": None,
        "model": "",
        "git_branch": "",
    }
    if not path:
        return stats
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue

                gb = obj.get("gitBranch")
                if gb:
                    stats["git_branch"] = gb

                record_type = obj.get("type")
                ts = obj.get("timestamp")

                if record_type == "user":
                    stats["total_turns"] += 1
                    # Only track REAL user messages (not tool results)
                    # Tool results have "toolUseResult" key; actual human
                    # messages have "permissionMode" and no "toolUseResult"
                    is_real_user = (
                        obj.get("userType") == "external"
                        and "toolUseResult" not in obj
                    )
                    if ts and is_real_user:
                        stats["last_user_ts"] = ts
                        stats["turn_agents"] = []  # reset per turn

                if record_type == "assistant" and isinstance(obj.get("message"), dict):
                    msg = obj["message"]
                    m = msg.get("model", "")
                    if m:
                        stats["model"] = m

                    usage = msg.get("usage", {})
                    if usage:
                        stats["total_output_tokens"] += usage.get("output_tokens", 0)

                    content = msg.get("content", [])
                    if isinstance(content, list):
                        for c in content:
                            if not isinstance(c, dict):
                                continue
                            if c.get("type") == "tool_use":
                                stats["total_tool_calls"] += 1
                                # Track Agent tool calls
                                if c.get("name") == "Agent":
                                    inp = c.get("input", {})
                                    agent_info = {
                                        "desc": inp.get("description", ""),
                                        "type": inp.get("subagent_type", ""),
                                        "name": inp.get("name", ""),
                                    }
                                    stats["total_agents"] += 1
                                    stats["agents"].append(agent_info)
                                    stats["turn_agents"].append(agent_info)
    except (FileNotFoundError, OSError):
        pass
    return stats


# ── Checkpoint (per-session, for turn-level stats) ───────────────────

CHECKPOINT_DIR = CONFIG_DIR / "checkpoints"


def _checkpoint_path(session_id: str) -> Path:
    """Per-session checkpoint file."""
    safe_id = session_id.replace("/", "_")[:64] if session_id else "default"
    return CHECKPOINT_DIR / f"{safe_id}.json"


def _load_checkpoint(session_id: str) -> dict:
    try:
        with open(_checkpoint_path(session_id), "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save_checkpoint(session_id: str, stats: dict) -> None:
    try:
        CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)
        checkpoint = {
            "output_tokens": stats["total_output_tokens"],
            "tool_calls": stats["total_tool_calls"],
            "turns": stats["total_turns"],
            "agents": stats["total_agents"],
            "time": time.time(),
        }
        with open(_checkpoint_path(session_id), "w") as f:
            json.dump(checkpoint, f)
        # Cleanup: remove checkpoints older than 7 days
        _cleanup_old_checkpoints()
    except OSError:
        pass


def _cleanup_old_checkpoints() -> None:
    """Remove checkpoint files older than 7 days."""
    try:
        cutoff = time.time() - 7 * 86400
        for f in CHECKPOINT_DIR.iterdir():
            if f.suffix == ".json" and f.stat().st_mtime < cutoff:
                f.unlink()
    except OSError:
        pass


def _calc_duration(start_ts: str | None) -> str:
    """Calculate duration from an ISO timestamp to now."""
    if not start_ts:
        return ""
    try:
        fmt = "%Y-%m-%dT%H:%M:%S"
        t1 = datetime.strptime(start_ts[:19], fmt).replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        secs = int((now - t1).total_seconds())
        if secs < 0:
            secs = 0
        if secs < 60:
            return f"{secs}s"
        if secs < 3600:
            return f"{secs // 60}m {secs % 60}s"
        return f"{secs // 3600}h {(secs % 3600) // 60}m"
    except (ValueError, TypeError):
        return ""


# ── Git info ─────────────────────────────────────────────────────────


def _get_git_info(cwd: str) -> dict:
    """Get git info from the working directory."""
    info = {"branch": "", "last_commit": "", "dirty": False}
    if not cwd:
        return info
    try:
        # Branch
        r = subprocess.run(
            ["git", "-C", cwd, "branch", "--show-current"],
            capture_output=True, text=True, timeout=5,
        )
        if r.returncode == 0:
            info["branch"] = r.stdout.strip()

        # Last commit (short)
        r = subprocess.run(
            ["git", "-C", cwd, "log", "--oneline", "-1", "--format=%h %s"],
            capture_output=True, text=True, timeout=5,
        )
        if r.returncode == 0:
            info["last_commit"] = r.stdout.strip()[:60]

        # Dirty?
        r = subprocess.run(
            ["git", "-C", cwd, "status", "--porcelain"],
            capture_output=True, text=True, timeout=5,
        )
        if r.returncode == 0:
            info["dirty"] = bool(r.stdout.strip())
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        pass
    return info


# ── Helpers ──────────────────────────────────────────────────────────


def _now_str() -> str:
    # Use TZ env or default to Asia/Shanghai (UTC+8)
    offset_hours = int(os.environ.get("CLAUDE_LARK_TZ_OFFSET", "8"))
    local = datetime.now(timezone.utc) + timedelta(hours=offset_hours)
    return local.strftime("%Y-%m-%d %H:%M:%S")


def _project_name(cwd: str) -> str:
    """Extract project name. For worktrees, resolve to the original repo name."""
    if not cwd:
        return "unknown"
    # Try to get the original repo path via git (handles worktrees)
    try:
        r = subprocess.run(
            ["git", "-C", cwd, "rev-parse", "--path-format=absolute", "--git-common-dir"],
            capture_output=True, text=True, timeout=3,
        )
        if r.returncode == 0:
            # Returns e.g. "/Users/me/Code/SEIR/.git" → "SEIR"
            git_dir = r.stdout.strip().rstrip("/")
            if git_dir.endswith("/.git"):
                return Path(git_dir).parent.name
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        pass
    return Path(cwd).name


def _hostname() -> str:
    return platform.node().split(".")[0] or "unknown"


def _truncate(text: str, max_len: int = 200) -> str:
    if not text:
        return ""
    text = text.strip()
    return text[:max_len] + "..." if len(text) > max_len else text


def _clean_markdown(text: str) -> str:
    """Convert standard Markdown to Lark card compatible subset.

    Lark card markdown supports:
      **bold**, *italic*, ~~strike~~, [link](url), `inline code`,
      <font color='red/green/grey'>colored text</font>

    Does NOT support:
      # headings, tables, code blocks, ordered/unordered lists, blockquotes
    """
    import re

    lines = text.split("\n")
    out: list[str] = []
    in_code_block = False

    for line in lines:
        # Toggle code blocks (``` ... ```)
        if line.strip().startswith("```"):
            in_code_block = not in_code_block
            continue  # skip delimiter

        if in_code_block:
            stripped = line.rstrip()
            if stripped:
                out.append(f"`{stripped}`")
            else:
                out.append("")
            continue

        # Headings → bold (with color for emphasis)
        heading_match = re.match(r'^(#{1,6})\s+(.+)$', line)
        if heading_match:
            level = len(heading_match.group(1))
            title = heading_match.group(2).strip()
            if level <= 2:
                out.append(f"<font color='green'>**{title}**</font>")
            else:
                out.append(f"**{title}**")
            continue

        # Table separator lines (|------|------| ) → skip
        if re.match(r'^\s*\|[\s:]*[-]+[\s:]*(\|[\s:]*[-]+[\s:]*)*\|\s*$', line):
            continue

        # Table rows: | A | B | C | → A | B | C (strip outer pipes)
        table_match = re.match(r'^\s*\|(.+)\|\s*$', line)
        if table_match:
            cells = [c.strip() for c in table_match.group(1).split("|")]
            out.append("  ".join(cells))
            continue

        # Blockquotes → italic
        if line.startswith("> "):
            out.append(f"*{line[2:]}*")
            continue

        # Unordered list items → bullet
        list_match = re.match(r'^(\s*)[-*]\s+(.+)$', line)
        if list_match:
            indent = "  " * (len(list_match.group(1)) // 2)
            out.append(f"{indent}• {list_match.group(2)}")
            continue

        # Everything else: keep as-is
        out.append(line)

    return "\n".join(out)


def _fmt_tokens(n: int) -> str:
    """Format token count: 856, 12.5k, 1.2M."""
    if n < 1_000:
        return str(n)
    if n < 1_000_000:
        return f"{n / 1_000:.1f}k"
    return f"{n / 1_000_000:.1f}M"


# ── Card builders ────────────────────────────────────────────────────


def _column(weight: int, content: str) -> dict:
    """Helper to build a single column element."""
    return {
        "tag": "column",
        "width": "weighted",
        "weight": weight,
        "vertical_align": "top",
        "elements": [{"tag": "markdown", "content": content}],
    }


def _columns(cols: list[dict]) -> dict:
    """Helper to build a column_set."""
    return {
        "tag": "column_set",
        "flex_mode": "none",
        "background_style": "default",
        "columns": cols,
    }


def _is_subagent(event: dict) -> bool:
    """Detect if this hook was triggered by a sub-agent (worktree/swarm)."""
    cwd = event.get("cwd", "")
    # Normalize to forward slashes for cross-platform matching
    normalized = cwd.replace("\\", "/")
    return "/worktrees/" in normalized or "/.worktree" in normalized


def _build_stop_card(event: dict, stats: dict, git: dict) -> dict:
    """Rich card for Stop events with full statistics."""
    cwd = event.get("cwd", "")
    project = _project_name(cwd)
    last_msg = event.get("last_assistant_message", "")
    host = _hostname()
    now = _now_str()
    is_sub = _is_subagent(event)
    session_id = event.get("session_id", "")

    branch = git.get("branch") or stats.get("git_branch") or ""

    # Calculate turn data via checkpoint diff (per-session)
    prev = _load_checkpoint(session_id)
    total_tok = stats["total_output_tokens"]
    total_tools = stats["total_tool_calls"]
    turn_tok = total_tok - prev.get("output_tokens", 0)
    turn_tools = total_tools - prev.get("tool_calls", 0)
    if turn_tok < 0:
        turn_tok = total_tok  # new session, no valid checkpoint
    if turn_tools < 0:
        turn_tools = total_tools

    # Duration: time from user's last message to now (actual Claude processing time)
    duration = _calc_duration(stats["last_user_ts"])

    elements: list[dict] = []

    # ── Row 1: Project + Device ──
    elements.append(_columns([
        _column(1, f"📁 **项目**\n{project}"),
        _column(1, f"💻 **设备**\n{host}"),
    ]))

    elements.append({"tag": "hr"})

    # ── Stats row: 5 columns ──
    stats_cols = []
    if duration:
        stats_cols.append(_column(1, f"⏱ **耗时**\n{duration}"))
    if total_tok > 0:
        stats_cols.append(_column(1, f"📊 **Tokens**\n{_fmt_tokens(turn_tok)} / {_fmt_tokens(total_tok)}"))
    if total_tools > 0:
        stats_cols.append(_column(1, f"🔧 **工具**\n{turn_tools} / {total_tools}"))
    if stats["total_turns"] > 0:
        stats_cols.append(_column(1, f"💬 **对话**\n{stats['total_turns']} 轮"))
    if branch:
        dirty_mark = " ●" if git.get("dirty") else ""
        stats_cols.append(_column(1, f"🌿 **分支**\n`{branch}`{dirty_mark}"))

    if stats_cols:
        elements.append(_columns(stats_cols))

    # ── Sub-agents (only show new ones since last checkpoint) ──
    all_agents = stats.get("agents", [])
    total_agents = stats.get("total_agents", 0)
    prev_agent_count = prev.get("agents", 0)
    new_agent_count = total_agents - prev_agent_count
    if new_agent_count < 0:
        new_agent_count = total_agents
        prev_agent_count = 0

    if new_agent_count > 0:
        # Show only the newly spawned agents (tail of the list)
        new_agents = all_agents[-new_agent_count:] if all_agents else []
        agent_lines = []
        for a in new_agents:
            label = a.get("name") or a.get("type") or "agent"
            desc = a.get("desc", "")
            if desc:
                agent_lines.append(f"• **{label}**  {desc}")
            else:
                agent_lines.append(f"• **{label}**")
        header = f"🤖 **子 Agent** ({new_agent_count} 个"
        if prev_agent_count > 0:
            header += f" / 本会话共 {total_agents}"
        header += ")"
        elements.append({"tag": "markdown", "content": header + "\n" + "\n".join(agent_lines)})

    # ── Git last commit ──
    last_commit = git.get("last_commit", "")
    if last_commit:
        elements.append({"tag": "markdown", "content": f"📝 **最近提交**  `{last_commit}`"})

    elements.append({"tag": "hr"})

    # ── Claude's last message ──
    if last_msg:
        cleaned = _clean_markdown(last_msg)
        # Lark card payload limit ~28KB; leave room for other fields
        snippet = _truncate(cleaned, 4000)
        elements.append({"tag": "markdown", "content": f"💬 **Claude 的回复**\n{snippet}"})
        elements.append({"tag": "hr"})

    # ── Footer ──
    footer_parts = []
    if cwd:
        footer_parts.append(f"📂 {cwd}")
    session_id = event.get("session_id", "")
    if session_id:
        footer_parts.append(f"🔑 {session_id[:12]}")
    footer_parts.append(f"🕐 {now}")

    elements.append({
        "tag": "note",
        "elements": [{"tag": "plain_text", "content": "  |  ".join(footer_parts)}],
    })

    # Header: differentiate main vs sub-agent
    if is_sub:
        worktree_name = Path(cwd).name if cwd else ""
        if worktree_name and worktree_name != project:
            header_title = f"🔧 子 Agent 完成 — {project}/{worktree_name}"
        else:
            header_title = f"🔧 子 Agent 完成 — {project}"
        header_color = "blue"
    else:
        header_title = "✅ Claude Code 任务完成"
        header_color = "turquoise"

    return {
        "config": {"wide_screen_mode": True},
        "header": {
            "title": {"tag": "plain_text", "content": header_title},
            "template": header_color,
        },
        "elements": elements,
    }


def _build_notification_card(event: dict, stats: dict, git: dict) -> dict:
    """Rich card for Notification events."""
    cwd = event.get("cwd", "")
    project = _project_name(cwd)
    message = event.get("message", "")
    title_text = event.get("title", "")
    notif_type = event.get("notification_type", "")
    host = _hostname()
    now = _now_str()
    branch = git.get("branch") or stats.get("git_branch") or ""

    header_map = {
        "permission_prompt": ("⚠️ Claude Code 需要你的确认", "orange"),
        "idle_prompt":       ("⏳ Claude Code 等待输入", "yellow"),
        "auth_success":      ("✅ Claude Code 认证成功", "green"),
        "elicitation_dialog": ("📝 Claude Code 需要信息", "blue"),
    }
    header_title, header_color = header_map.get(
        notif_type, ("🔔 Claude Code 通知", "blue")
    )

    elements: list[dict] = []

    # ── Row 1: Project + Device ──
    col1 = [_column(1, f"📁 **项目**\n{project}")]
    col1.append(_column(1, f"💻 **设备**\n{host}"))
    elements.append(_columns(col1))

    elements.append({"tag": "hr"})

    # ── Title + Message ──
    if title_text:
        elements.append({"tag": "markdown", "content": f"**{title_text}**"})
    if message:
        elements.append({"tag": "markdown", "content": f"💬 {_truncate(_clean_markdown(message), 4000)}"})

    # ── Branch info ──
    if branch:
        elements.append({"tag": "markdown", "content": f"🌿 **分支**  `{branch}`"})

    elements.append({"tag": "hr"})

    # ── Footer ──
    footer_parts = []
    if cwd:
        footer_parts.append(f"📂 {cwd}")
    footer_parts.append(f"🕐 {now}")

    elements.append({
        "tag": "note",
        "elements": [{"tag": "plain_text", "content": "  |  ".join(footer_parts)}],
    })

    return {
        "config": {"wide_screen_mode": True},
        "header": {
            "title": {"tag": "plain_text", "content": header_title},
            "template": header_color,
        },
        "elements": elements,
    }


# ── Send ─────────────────────────────────────────────────────────────


def send_card(token: str, open_id: str, card: dict) -> bool:
    payload = json.dumps(
        {
            "receive_id": open_id,
            "msg_type": "interactive",
            "content": json.dumps(card, ensure_ascii=False),
        },
        ensure_ascii=False,
    ).encode("utf-8")

    req = urllib.request.Request(
        f"{LARK_MESSAGE_URL}?receive_id_type=open_id",
        data=payload,
        headers={
            "Content-Type": "application/json; charset=utf-8",
            "Authorization": f"Bearer {token}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
            result = json.loads(resp.read())
            success = result.get("code") == 0
            if success:
                _debug_log("Card sent successfully")
            else:
                _debug_log(f"Card send failed: code={result.get('code')}, msg={result.get('msg')}")
            return success
    except (urllib.error.URLError, json.JSONDecodeError, OSError) as e:
        _debug_log(f"Card send error: {e}")
        return False


# ── Main ─────────────────────────────────────────────────────────────


def main() -> None:
    _debug_log("=== claude-lark notify start ===")

    config = _load_config()
    if not config:
        _debug_log("No config, exiting")
        return

    event = _read_stdin()
    if not event:
        _debug_log("No event data, exiting")
        return

    # Event filtering
    event_name = event.get("hook_event_name", "")
    allowed = config.get("events", DEFAULT_EVENTS)
    if event_name and event_name not in allowed:
        _debug_log(f"Event '{event_name}' not in allowed list {allowed}, skipping")
        return

    # Quiet hours filter (e.g. "quiet_hours": [23, 8] = 23:00–08:00 no notify)
    quiet = config.get("quiet_hours")
    if quiet and len(quiet) == 2 and event_name == "Stop":
        import os as _os
        offset = int(_os.environ.get("CLAUDE_LARK_TZ_OFFSET", "8"))
        local_hour = (datetime.now(timezone.utc) + timedelta(hours=offset)).hour
        start, end = quiet
        if start > end:  # overnight range e.g. [23, 8]
            is_quiet = local_hour >= start or local_hour < end
        else:  # daytime range e.g. [12, 14]
            is_quiet = start <= local_hour < end
        if is_quiet:
            _debug_log(f"Quiet hours ({start}-{end}), local hour={local_hour}, skipping")
            return

    # Parse transcript for rich stats
    transcript_path = event.get("transcript_path", "")
    stats = _parse_transcript(transcript_path)

    # Min duration filter (skip quick responses, e.g. "min_duration": 30)
    min_dur = config.get("min_duration", 0)
    if min_dur > 0 and event_name == "Stop" and stats.get("last_user_ts"):
        try:
            fmt = "%Y-%m-%dT%H:%M:%S"
            t1 = datetime.strptime(stats["last_user_ts"][:19], fmt).replace(tzinfo=timezone.utc)
            elapsed = (datetime.now(timezone.utc) - t1).total_seconds()
            if elapsed < min_dur:
                _debug_log(f"Duration {elapsed:.0f}s < min_duration {min_dur}s, skipping")
                return
        except (ValueError, TypeError):
            pass

    # Get git info
    cwd = event.get("cwd", "")
    git = _get_git_info(cwd)

    # Build card
    if event_name == "Stop":
        card = _build_stop_card(event, stats, git)
    else:
        card = _build_notification_card(event, stats, git)

    # Send + save checkpoint
    token = get_token(config["app_id"], config["app_secret"])
    if token:
        send_card(token, config["open_id"], card)
        session_id = event.get("session_id", "")
        _save_checkpoint(session_id, stats)
    else:
        _debug_log("Failed to get token, notification not sent")

    _debug_log("=== claude-lark notify end ===")


if __name__ == "__main__":
    main()
