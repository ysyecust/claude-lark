"""Tests for claude_lark_notify — pure stdlib, no external deps."""

import json
import sys
import time
from pathlib import Path
from unittest import mock

# Ensure the project root is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import claude_lark_notify as notify


# ── Helpers ──────────────────────────────────────────────────────────


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f)


def _make_transcript(path: str, records: list[dict]) -> None:
    with open(path, "w") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")


# ── _load_config ─────────────────────────────────────────────────────


class TestLoadConfig:
    def test_valid_config(self, tmp_path):
        cfg = {"app_id": "cli_x", "app_secret": "secret", "open_id": "ou_x"}
        p = tmp_path / "config.json"
        _write_json(p, cfg)
        with mock.patch.object(notify, "CONFIG_PATH", p):
            result = notify._load_config()
        assert result is not None
        assert result["app_id"] == "cli_x"

    def test_missing_file(self, tmp_path):
        with mock.patch.object(notify, "CONFIG_PATH", tmp_path / "nope.json"):
            assert notify._load_config() is None

    def test_missing_fields(self, tmp_path):
        p = tmp_path / "config.json"
        _write_json(p, {"app_id": "cli_x", "app_secret": ""})
        with mock.patch.object(notify, "CONFIG_PATH", p):
            assert notify._load_config() is None

    def test_invalid_json(self, tmp_path):
        p = tmp_path / "config.json"
        p.write_text("{bad json")
        with mock.patch.object(notify, "CONFIG_PATH", p):
            assert notify._load_config() is None


# ── _read_stdin ──────────────────────────────────────────────────────


class TestReadStdin:
    def test_valid_json(self):
        with mock.patch("sys.stdin") as m:
            m.isatty.return_value = False
            m.read.return_value = '{"hook_event_name": "Stop"}'
            result = notify._read_stdin()
        assert result == {"hook_event_name": "Stop"}

    def test_empty_stdin(self):
        with mock.patch("sys.stdin") as m:
            m.isatty.return_value = False
            m.read.return_value = ""
            assert notify._read_stdin() == {}

    def test_invalid_json(self):
        with mock.patch("sys.stdin") as m:
            m.isatty.return_value = False
            m.read.return_value = "{broken"
            assert notify._read_stdin() == {}

    def test_tty(self):
        with mock.patch("sys.stdin") as m:
            m.isatty.return_value = True
            assert notify._read_stdin() == {}


# ── Token cache ──────────────────────────────────────────────────────


class TestTokenCache:
    def test_valid_cache(self, tmp_path):
        p = tmp_path / ".token_cache"
        _write_json(p, {"token": "t-abc", "expires_at": time.time() + 3600})
        with mock.patch.object(notify, "TOKEN_CACHE_PATH", p):
            assert notify._get_cached_token() == "t-abc"

    def test_expired_cache(self, tmp_path):
        p = tmp_path / ".token_cache"
        _write_json(p, {"token": "t-old", "expires_at": time.time() - 100})
        with mock.patch.object(notify, "TOKEN_CACHE_PATH", p):
            assert notify._get_cached_token() is None

    def test_missing_cache(self, tmp_path):
        with mock.patch.object(notify, "TOKEN_CACHE_PATH", tmp_path / "nope"):
            assert notify._get_cached_token() is None

    def test_save_and_load(self, tmp_path):
        p = tmp_path / ".token_cache"
        with mock.patch.object(notify, "TOKEN_CACHE_PATH", p), \
             mock.patch.object(notify, "CONFIG_DIR", tmp_path):
            notify._save_token_cache("t-new", 7200)
            assert notify._get_cached_token() == "t-new"


# ── _parse_transcript ────────────────────────────────────────────────


class TestParseTranscript:
    def test_empty_path(self):
        stats = notify._parse_transcript("")
        assert stats["total_output_tokens"] == 0
        assert stats["total_tool_calls"] == 0

    def test_missing_file(self):
        stats = notify._parse_transcript("/nonexistent/file.jsonl")
        assert stats["total_output_tokens"] == 0

    def test_basic_stats(self, tmp_path):
        records = [
            {"type": "user", "userType": "external", "timestamp": "2026-03-14T10:00:00Z"},
            {
                "type": "assistant",
                "message": {
                    "model": "claude-opus-4-6",
                    "usage": {"output_tokens": 500},
                    "content": [
                        {"type": "tool_use", "name": "Read", "input": {}},
                        {"type": "tool_use", "name": "Edit", "input": {}},
                        {"type": "text", "text": "done"},
                    ],
                },
            },
            {"type": "user", "userType": "external", "timestamp": "2026-03-14T10:05:00Z"},
            {
                "type": "assistant",
                "message": {
                    "model": "claude-opus-4-6",
                    "usage": {"output_tokens": 300},
                    "content": [
                        {"type": "tool_use", "name": "Bash", "input": {}},
                        {"type": "text", "text": "ok"},
                    ],
                },
            },
        ]
        p = str(tmp_path / "transcript.jsonl")
        _make_transcript(p, records)
        stats = notify._parse_transcript(p)
        assert stats["total_output_tokens"] == 800
        assert stats["total_tool_calls"] == 3
        assert stats["total_turns"] == 2
        assert stats["model"] == "claude-opus-4-6"

    def test_agent_tracking(self, tmp_path):
        records = [
            {"type": "user", "userType": "external", "timestamp": "2026-03-14T10:00:00Z"},
            {
                "type": "assistant",
                "message": {
                    "usage": {"output_tokens": 100},
                    "content": [
                        {
                            "type": "tool_use",
                            "name": "Agent",
                            "input": {
                                "description": "Explore codebase",
                                "subagent_type": "Explore",
                                "name": "",
                            },
                        },
                        {
                            "type": "tool_use",
                            "name": "Agent",
                            "input": {
                                "description": "Run tests",
                                "subagent_type": "general-purpose",
                                "name": "test-runner",
                            },
                        },
                    ],
                },
            },
        ]
        p = str(tmp_path / "transcript.jsonl")
        _make_transcript(p, records)
        stats = notify._parse_transcript(p)
        assert stats["total_agents"] == 2
        assert len(stats["agents"]) == 2
        assert stats["agents"][0]["desc"] == "Explore codebase"
        assert stats["agents"][1]["name"] == "test-runner"

    def test_turn_agents_reset(self, tmp_path):
        """turn_agents resets on each external user message."""
        records = [
            {"type": "user", "userType": "external", "timestamp": "2026-03-14T10:00:00Z"},
            {
                "type": "assistant",
                "message": {
                    "usage": {"output_tokens": 50},
                    "content": [
                        {"type": "tool_use", "name": "Agent", "input": {"description": "old agent", "subagent_type": "", "name": ""}},
                    ],
                },
            },
            {"type": "user", "userType": "external", "timestamp": "2026-03-14T10:10:00Z"},
            {
                "type": "assistant",
                "message": {
                    "usage": {"output_tokens": 50},
                    "content": [
                        {"type": "tool_use", "name": "Agent", "input": {"description": "new agent", "subagent_type": "Explore", "name": ""}},
                    ],
                },
            },
        ]
        p = str(tmp_path / "transcript.jsonl")
        _make_transcript(p, records)
        stats = notify._parse_transcript(p)
        assert stats["total_agents"] == 2
        assert len(stats["turn_agents"]) == 1
        assert stats["turn_agents"][0]["desc"] == "new agent"

    def test_git_branch(self, tmp_path):
        records = [
            {"type": "progress", "gitBranch": "feature/x", "timestamp": "2026-03-14T10:00:00Z"},
        ]
        p = str(tmp_path / "transcript.jsonl")
        _make_transcript(p, records)
        stats = notify._parse_transcript(p)
        assert stats["git_branch"] == "feature/x"

    def test_malformed_lines_skipped(self, tmp_path):
        p = str(tmp_path / "transcript.jsonl")
        with open(p, "w") as f:
            f.write("not json\n")
            f.write(json.dumps({"type": "user", "userType": "external", "timestamp": "2026-03-14T10:00:00Z"}) + "\n")
        stats = notify._parse_transcript(p)
        assert stats["total_turns"] == 1


# ── Checkpoint ───────────────────────────────────────────────────────


class TestCheckpoint:
    def test_roundtrip(self, tmp_path):
        cp_dir = tmp_path / "checkpoints"
        with mock.patch.object(notify, "CHECKPOINT_DIR", cp_dir):
            stats = {
                "total_output_tokens": 5000,
                "total_tool_calls": 42,
                "total_turns": 10,
                "total_agents": 3,
            }
            notify._save_checkpoint("sess-123", stats)
            loaded = notify._load_checkpoint("sess-123")
        assert loaded["output_tokens"] == 5000
        assert loaded["tool_calls"] == 42
        assert loaded["agents"] == 3
        assert "time" in loaded

    def test_missing_checkpoint(self, tmp_path):
        with mock.patch.object(notify, "CHECKPOINT_DIR", tmp_path / "nope"):
            assert notify._load_checkpoint("unknown") == {}

    def test_session_isolation(self, tmp_path):
        """Different sessions get different checkpoints."""
        cp_dir = tmp_path / "checkpoints"
        with mock.patch.object(notify, "CHECKPOINT_DIR", cp_dir):
            stats_a = {"total_output_tokens": 1000, "total_tool_calls": 10, "total_turns": 5, "total_agents": 1}
            stats_b = {"total_output_tokens": 9999, "total_tool_calls": 99, "total_turns": 50, "total_agents": 5}
            notify._save_checkpoint("sess-a", stats_a)
            notify._save_checkpoint("sess-b", stats_b)
            assert notify._load_checkpoint("sess-a")["output_tokens"] == 1000
            assert notify._load_checkpoint("sess-b")["output_tokens"] == 9999


# ── _calc_duration ───────────────────────────────────────────────────


class TestCalcDuration:
    def test_none_input(self):
        assert notify._calc_duration(None) == ""

    def test_seconds(self):
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)
        ts = (now - __import__("datetime").timedelta(seconds=30)).strftime("%Y-%m-%dT%H:%M:%S.000Z")
        result = notify._calc_duration(ts)
        # Should be around 30s (allow 2s margin)
        assert result.endswith("s")
        secs = int(result.rstrip("s"))
        assert 28 <= secs <= 35

    def test_minutes(self):
        from datetime import datetime, timezone, timedelta
        now = datetime.now(timezone.utc)
        ts = (now - timedelta(minutes=5, seconds=30)).strftime("%Y-%m-%dT%H:%M:%S.000Z")
        result = notify._calc_duration(ts)
        assert "5m" in result

    def test_hours(self):
        from datetime import datetime, timezone, timedelta
        now = datetime.now(timezone.utc)
        ts = (now - timedelta(hours=2, minutes=15)).strftime("%Y-%m-%dT%H:%M:%S.000Z")
        result = notify._calc_duration(ts)
        assert "2h" in result


# ── _clean_markdown ──────────────────────────────────────────────────


class TestCleanMarkdown:
    def test_heading_h2(self):
        result = notify._clean_markdown("## Title Here")
        assert "**Title Here**" in result
        assert "<font color='green'>" in result

    def test_heading_h3(self):
        result = notify._clean_markdown("### Sub Title")
        assert result.strip() == "**Sub Title**"

    def test_table_separator_removed(self):
        md = "| A | B |\n|---|---|\n| 1 | 2 |"
        result = notify._clean_markdown(md)
        assert "---" not in result
        assert "1" in result and "2" in result

    def test_table_cells(self):
        result = notify._clean_markdown("| foo | bar | baz |")
        assert "|" not in result or result.count("|") == 0
        assert "foo" in result
        assert "bar" in result

    def test_code_block(self):
        md = "```python\ndef hello():\n    pass\n```"
        result = notify._clean_markdown(md)
        assert "```" not in result
        assert "`def hello():`" in result

    def test_unordered_list(self):
        result = notify._clean_markdown("- item one\n- item two")
        assert "• item one" in result
        assert "• item two" in result

    def test_blockquote(self):
        result = notify._clean_markdown("> quoted text")
        assert "*quoted text*" in result

    def test_plain_text_unchanged(self):
        text = "Just normal text with **bold** already"
        assert notify._clean_markdown(text) == text

    def test_mixed_content(self):
        md = "## Heading\n\nSome text\n\n- list item\n\n> quote\n\n```\ncode\n```"
        result = notify._clean_markdown(md)
        assert "**Heading**" in result
        assert "Some text" in result
        assert "• list item" in result
        assert "*quote*" in result
        assert "`code`" in result


# ── Helpers ──────────────────────────────────────────────────────────


class TestHelpers:
    def test_project_name(self):
        assert notify._project_name("/Users/me/Code/my-project") == "my-project"
        assert notify._project_name("") == "unknown"
        assert notify._project_name("/single") == "single"

    def test_truncate(self):
        assert notify._truncate("", 10) == ""
        assert notify._truncate("short", 10) == "short"
        assert notify._truncate("a" * 20, 10) == "a" * 10 + "..."

    def test_fmt_tokens(self):
        assert notify._fmt_tokens(0) == "0"
        assert notify._fmt_tokens(500) == "500"
        assert notify._fmt_tokens(1500) == "1.5k"
        assert notify._fmt_tokens(12500) == "12.5k"
        assert notify._fmt_tokens(1_500_000) == "1.5M"

    def test_hostname(self):
        result = notify._hostname()
        assert isinstance(result, str)
        assert len(result) > 0

    def test_now_str(self):
        result = notify._now_str()
        assert "2026" in result or "202" in result  # sanity check
        assert len(result) == 19  # YYYY-MM-DD HH:MM:SS


# ── _is_subagent ─────────────────────────────────────────────────────


class TestIsSubagent:
    def test_normal_path(self):
        assert notify._is_subagent({"cwd": "/Users/me/Code/project"}) is False

    def test_worktree_path(self):
        assert notify._is_subagent({"cwd": "/Users/me/Code/project/worktrees/agent-1"}) is True

    def test_dot_worktree(self):
        assert notify._is_subagent({"cwd": "/tmp/.worktree/test"}) is True

    def test_empty_cwd(self):
        assert notify._is_subagent({"cwd": ""}) is False
        assert notify._is_subagent({}) is False


# ── Card builders ────────────────────────────────────────────────────


class TestBuildStopCard:
    def _base_event(self):
        return {
            "hook_event_name": "Stop",
            "cwd": "/Users/me/Code/my-project",
            "session_id": "abc-123-def",
            "last_assistant_message": "Task completed successfully.",
        }

    def _base_stats(self):
        return {
            "total_output_tokens": 5000,
            "total_tool_calls": 20,
            "total_turns": 10,
            "total_agents": 0,
            "agents": [],
            "turn_agents": [],
            "last_user_ts": None,
            "model": "claude-opus-4-6",
            "git_branch": "main",
        }

    def _base_git(self):
        return {"branch": "main", "last_commit": "abc1234 initial commit", "dirty": False}

    def test_basic_card(self, tmp_path):
        cp_dir = tmp_path / "checkpoints"
        with mock.patch.object(notify, "CHECKPOINT_DIR", cp_dir):
            card = notify._build_stop_card(self._base_event(), self._base_stats(), self._base_git())
        assert card["header"]["template"] == "turquoise"
        assert "任务完成" in card["header"]["title"]["content"]
        assert len(card["elements"]) > 0

    def test_subagent_card(self, tmp_path):
        event = self._base_event()
        event["cwd"] = "/tmp/project/worktrees/agent-1"
        cp_dir = tmp_path / "checkpoints"
        with mock.patch.object(notify, "CHECKPOINT_DIR", cp_dir):
            card = notify._build_stop_card(event, self._base_stats(), self._base_git())
        assert card["header"]["template"] == "blue"
        assert "子 Agent" in card["header"]["title"]["content"]

    def test_card_with_agents(self, tmp_path):
        stats = self._base_stats()
        stats["total_agents"] = 2
        stats["agents"] = [
            {"desc": "Explore code", "type": "Explore", "name": ""},
            {"desc": "Run tests", "type": "", "name": "test-runner"},
        ]
        # No previous checkpoint → all agents are "new"
        cp_dir = tmp_path / "checkpoints"
        with mock.patch.object(notify, "CHECKPOINT_DIR", cp_dir):
            card = notify._build_stop_card(self._base_event(), stats, self._base_git())
        card_json = json.dumps(card, ensure_ascii=False)
        assert "Explore" in card_json
        assert "test-runner" in card_json

    def test_card_no_agents_after_checkpoint(self, tmp_path):
        """If checkpoint already recorded agents, don't show them again."""
        stats = self._base_stats()
        stats["total_agents"] = 2
        stats["agents"] = [
            {"desc": "old", "type": "Explore", "name": ""},
        ]
        cp_dir = tmp_path / "checkpoints"
        cp_dir.mkdir(parents=True)
        cp_file = cp_dir / "abc-123-def.json"
        _write_json(cp_file, {"output_tokens": 0, "tool_calls": 0, "turns": 0, "agents": 2, "time": time.time() - 60})
        with mock.patch.object(notify, "CHECKPOINT_DIR", cp_dir):
            card = notify._build_stop_card(self._base_event(), stats, self._base_git())
        card_json = json.dumps(card, ensure_ascii=False)
        assert "子 Agent" not in card_json


class TestBuildNotificationCard:
    def test_permission_prompt(self):
        event = {
            "hook_event_name": "Notification",
            "cwd": "/Users/me/Code/proj",
            "notification_type": "permission_prompt",
            "title": "Permission needed",
            "message": "Claude wants to run rm -rf /tmp",
        }
        stats = {"git_branch": "main"}
        git = {"branch": "main", "last_commit": "", "dirty": False}
        card = notify._build_notification_card(event, stats, git)
        assert card["header"]["template"] == "orange"
        assert "确认" in card["header"]["title"]["content"]

    def test_idle_prompt(self):
        event = {
            "hook_event_name": "Notification",
            "cwd": "/tmp",
            "notification_type": "idle_prompt",
            "message": "Waiting for input",
        }
        card = notify._build_notification_card(event, {"git_branch": ""}, {"branch": "", "last_commit": "", "dirty": False})
        assert card["header"]["template"] == "yellow"

    def test_unknown_type(self):
        event = {
            "hook_event_name": "Notification",
            "cwd": "/tmp",
            "notification_type": "some_future_type",
            "message": "Something",
        }
        card = notify._build_notification_card(event, {"git_branch": ""}, {"branch": "", "last_commit": "", "dirty": False})
        assert card["header"]["template"] == "blue"


# ── Main flow ────────────────────────────────────────────────────────


class TestSendCard:
    def test_success(self):
        resp_body = json.dumps({"code": 0}).encode()
        mock_resp = mock.MagicMock()
        mock_resp.read.return_value = resp_body
        mock_resp.__enter__ = mock.MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = mock.MagicMock(return_value=False)
        with mock.patch("urllib.request.urlopen", return_value=mock_resp):
            result = notify.send_card("t-abc", "ou_x", {"header": {}, "elements": []})
        assert result is True

    def test_api_error(self):
        resp_body = json.dumps({"code": 99999, "msg": "fail"}).encode()
        mock_resp = mock.MagicMock()
        mock_resp.read.return_value = resp_body
        mock_resp.__enter__ = mock.MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = mock.MagicMock(return_value=False)
        with mock.patch("urllib.request.urlopen", return_value=mock_resp):
            result = notify.send_card("t-abc", "ou_x", {"header": {}, "elements": []})
        assert result is False

    def test_network_error(self):
        with mock.patch("urllib.request.urlopen", side_effect=notify.urllib.error.URLError("timeout")):
            result = notify.send_card("t-abc", "ou_x", {"header": {}, "elements": []})
        assert result is False


class TestTruncateLargeMessage:
    def test_oversized_message_truncated(self, tmp_path):
        """Messages > 4000 chars should be truncated in the card."""
        huge_msg = "x" * 5000
        event = {
            "hook_event_name": "Stop",
            "cwd": "/tmp/proj",
            "session_id": "s1",
            "last_assistant_message": huge_msg,
        }
        stats = {
            "total_output_tokens": 100, "total_tool_calls": 1,
            "total_turns": 1, "total_agents": 0, "agents": [],
            "turn_agents": [], "last_user_ts": None, "model": "", "git_branch": "",
        }
        git = {"branch": "", "last_commit": "", "dirty": False}
        cp_dir = tmp_path / "checkpoints"
        with mock.patch.object(notify, "CHECKPOINT_DIR", cp_dir):
            card = notify._build_stop_card(event, stats, git)
        card_str = json.dumps(card)
        # The 5000-char message should be truncated to ~4000 + "..."
        assert len(card_str) < 10000


class TestMain:
    def test_no_config_exits_silently(self, tmp_path):
        with mock.patch.object(notify, "CONFIG_PATH", tmp_path / "nope.json"):
            notify.main()  # should not raise

    def test_event_filtering(self, tmp_path):
        cfg_path = tmp_path / "config.json"
        _write_json(cfg_path, {
            "app_id": "cli_x", "app_secret": "s", "open_id": "ou_x",
            "events": ["Notification"],  # Stop not in list
        })
        with mock.patch.object(notify, "CONFIG_PATH", cfg_path), \
             mock.patch("sys.stdin") as m, \
             mock.patch.object(notify, "send_card") as send:
            m.isatty.return_value = False
            m.read.return_value = json.dumps({"hook_event_name": "Stop", "cwd": "/tmp"})
            notify.main()
        send.assert_not_called()

    def test_full_flow_mocked(self, tmp_path):
        cfg_path = tmp_path / "config.json"
        cp_dir = tmp_path / "checkpoints"
        _write_json(cfg_path, {"app_id": "cli_x", "app_secret": "s", "open_id": "ou_x"})

        event = {
            "hook_event_name": "Stop",
            "cwd": "/Users/me/Code/proj",
            "session_id": "sess-1",
            "last_assistant_message": "Done!",
            "transcript_path": "",
        }
        with mock.patch.object(notify, "CONFIG_PATH", cfg_path), \
             mock.patch.object(notify, "CHECKPOINT_DIR", cp_dir), \
             mock.patch.object(notify, "CONFIG_DIR", tmp_path), \
             mock.patch("sys.stdin") as m, \
             mock.patch.object(notify, "get_token", return_value="t-mock"), \
             mock.patch.object(notify, "send_card", return_value=True) as send, \
             mock.patch.object(notify, "_get_git_info", return_value={"branch": "main", "last_commit": "", "dirty": False}):
            m.isatty.return_value = False
            m.read.return_value = json.dumps(event)
            notify.main()
        send.assert_called_once()
        card = send.call_args[0][2]
        assert card["header"]["template"] == "turquoise"
