"""Unit tests for D-1 CLI helpers — colors, errors, doctor, config_cmd."""

from __future__ import annotations

import io
import os

import pytest

from cli.colors import Palette
from cli.errors import format_error_block
from core.path_utils import resolve_data_dir
from query import config_cmd
from query.doctor import doctor

# ----- Palette -----


def test_palette_disabled_when_no_color_set(monkeypatch):
    monkeypatch.setenv("NO_COLOR", "1")
    p = Palette(color_mode="auto", stream=io.StringIO())
    assert p.enabled is False
    # Even on a forced "auto" with NO_COLOR set, paint is a no-op.
    assert p.paint("hi", "red") == "hi"


def test_palette_disabled_on_non_tty(monkeypatch):
    monkeypatch.delenv("NO_COLOR", raising=False)
    # io.StringIO has no .isatty → treated as non-TTY → disabled.
    p = Palette(color_mode="auto", stream=io.StringIO())
    assert p.enabled is False


def test_palette_never_overrides_tty(monkeypatch):
    monkeypatch.delenv("NO_COLOR", raising=False)

    class FakeTTY:
        def isatty(self):
            return True

        def write(self, _):
            pass

    p = Palette(color_mode="never", stream=FakeTTY())
    assert p.enabled is False
    assert p.paint("x", "red") == "x"


def test_palette_always_forces_color(monkeypatch):
    p = Palette(color_mode="always", stream=io.StringIO())
    assert p.enabled is True
    out = p.paint("hi", "red")
    assert "\033[31m" in out and "\033[0m" in out


def test_palette_symbol_returns_ascii():
    p = Palette(color_mode="never", stream=io.StringIO())
    assert p.symbol("user_prompt") == ">>"
    assert p.symbol("agent_response") == "<<"
    assert p.symbol("hint") == "!"
    assert p.symbol("hallucination_candidate") == "?"


# ----- format_error_block -----


def test_format_error_block_minimal():
    out = format_error_block("oops")
    assert out == "error: oops"


def test_format_error_block_has_three_sections():
    out = format_error_block(
        "session 'abc' is ambiguous",
        cause="3 sessions match prefix 'abc'",
        tries=["aot list --filter prefix=abc", "aot trace --session abc94a3e --output 'JWT'"],
    )
    lines = out.splitlines()
    assert lines[0].startswith("error:")
    assert lines[1].lstrip().startswith("cause:")
    assert lines[2].lstrip().startswith("try:")
    # Additional try lines align beneath the first
    assert lines[3].startswith("         ")


def test_format_error_block_multiline_cause():
    out = format_error_block(
        "ambiguous",
        cause="line A\nline B",
        tries=["one"],
    )
    assert "line A" in out
    assert "line B" in out
    # Continuation lines are indented to match the headline column
    assert "         line B" in out


# ----- doctor -----


def test_doctor_with_no_data_dir(tmp_path, monkeypatch):
    monkeypatch.delenv("CLAUDE_PLUGIN_DATA", raising=False)
    monkeypatch.delenv("CODEX_PLUGIN_DATA", raising=False)
    # Aim well clear of any pre-existing Codex default
    monkeypatch.setenv("HOME", str(tmp_path))
    buf = io.StringIO()
    result = doctor(data_dir=None, fmt="text", stream=buf)
    assert result["$schema"] == "aot/doctor/v1"
    names = [c["name"] for c in result["checks"]]
    assert names == ["runtime", "data_dir", "recent_sessions", "hooks_wiring"]
    # data_dir should warn when nothing is configured
    data_dir_check = next(c for c in result["checks"] if c["name"] == "data_dir")
    assert data_dir_check["status"] == "warn"


def test_doctor_with_seeded_data_dir(tmp_path):
    # Create a minimal session structure
    sessions = tmp_path / "sessions" / "abcd-1234"
    sessions.mkdir(parents=True)
    (sessions / "events.jsonl").write_text(
        '{"v":1,"engine":"claude-code","event_type":"user_prompt",'
        '"session_id":"abcd-1234","ts":"2026-05-15T10:00:00.000+00:00",'
        '"cwd":"/p","user_prompt_text":"hi","tool_name":null,"tool_input":null,'
        '"tool_response":null,"agent_response_text":null,"stop_reason":null,'
        '"paths":[],"command":null,"result_bytes":0,"raw_event":{}}\n'
    )
    (sessions / "metadata.json").write_text(
        '{"v":1,"session_id":"abcd-1234","engine":"claude-code",'
        '"ts_start":"2026-05-15T10:00:00.000+00:00",'
        '"ts_end":"2026-05-15T10:01:00.000+00:00","cwd":"/p","tool_calls_total":0,'
        '"user_prompts_count":1,"agent_responses_count":0,"unique_files_read":0,'
        '"total_bytes_read":0,"tags":[]}'
    )
    buf = io.StringIO()
    result = doctor(data_dir=str(tmp_path), fmt="text", stream=buf)
    data_dir_check = next(c for c in result["checks"] if c["name"] == "data_dir")
    assert data_dir_check["status"] == "ok"
    recent = next(c for c in result["checks"] if c["name"] == "recent_sessions")
    assert recent["status"] == "ok"
    assert "tools=0" in recent["detail"]


def test_doctor_json_output(tmp_path):
    buf = io.StringIO()
    result = doctor(data_dir=str(tmp_path), fmt="json", stream=buf)
    payload = buf.getvalue()
    assert payload.startswith("{")
    assert '"$schema"' in payload
    assert result["ok"] in (True, False)


def _isolate_doctor_paths(tmp_path, monkeypatch):
    """Neutralise the dev-install probe and redirect $HOME to tmp_path.

    Lets tests simulate a pipx-style install where the CLI lives away from
    the plugin's hooks/ directory.
    """
    monkeypatch.setenv("HOME", str(tmp_path))
    fake_pkg = tmp_path / "fake-site-packages" / "query" / "doctor.py"
    fake_pkg.parent.mkdir(parents=True)
    fake_pkg.write_text("")
    monkeypatch.setattr("query.doctor.__file__", str(fake_pkg))
    return tmp_path


def test_doctor_hooks_wiring_finds_claude_marketplace(tmp_path, monkeypatch):
    _isolate_doctor_paths(tmp_path, monkeypatch)
    cc_install = (
        tmp_path / ".claude" / "plugins" / "marketplaces" / "itosdad-agent-output-tracer" / "hooks"
    )
    cc_install.mkdir(parents=True)
    (cc_install / "hooks.json").write_text('{"hooks": {"SessionStart": []}}')

    buf = io.StringIO()
    result = doctor(data_dir=str(tmp_path), fmt="text", stream=buf)
    hw = next(c for c in result["checks"] if c["name"] == "hooks_wiring")
    assert hw["status"] == "ok"
    assert "hooks.json" in hw["detail"]


def test_doctor_hooks_wiring_finds_codex_cache(tmp_path, monkeypatch):
    _isolate_doctor_paths(tmp_path, monkeypatch)
    cdx_install = (
        tmp_path
        / ".codex"
        / "plugins"
        / "cache"
        / "itosdad-agent-output-tracer"
        / "agent-output-tracer"
        / "0.6.0"
        / "hooks"
    )
    cdx_install.mkdir(parents=True)
    (cdx_install / "hooks.json").write_text('{"hooks": {"SessionStart": []}}')

    buf = io.StringIO()
    result = doctor(data_dir=str(tmp_path), fmt="text", stream=buf)
    hw = next(c for c in result["checks"] if c["name"] == "hooks_wiring")
    assert hw["status"] == "ok"


def test_doctor_hooks_wiring_warns_when_uninstalled(tmp_path, monkeypatch):
    """pipx-installed CLI with no marketplace install anywhere → warn, not fail."""
    _isolate_doctor_paths(tmp_path, monkeypatch)
    buf = io.StringIO()
    result = doctor(data_dir=str(tmp_path), fmt="text", stream=buf)
    hw = next(c for c in result["checks"] if c["name"] == "hooks_wiring")
    assert hw["status"] == "warn"
    assert "fix" in hw and hw["fix"]


# ----- resolve_data_dir scan-for-Claude-Code-naming -----


def _clear_data_env(monkeypatch):
    monkeypatch.delenv("CLAUDE_PLUGIN_DATA", raising=False)
    monkeypatch.delenv("CODEX_PLUGIN_DATA", raising=False)


def test_resolve_data_dir_finds_marketplace_named_dir(tmp_path, monkeypatch):
    """Claude Code names plugin data `<plugin>-<marketplace>` — the CLI must find it."""
    _clear_data_env(monkeypatch)
    monkeypatch.setenv("HOME", str(tmp_path))
    target = (
        tmp_path
        / ".claude"
        / "plugins"
        / "data"
        / "agent-output-tracer-itosdad-agent-output-tracer"
        / "sessions"
    )
    target.mkdir(parents=True)
    resolved = resolve_data_dir()
    assert resolved is not None
    assert resolved.name == "agent-output-tracer-itosdad-agent-output-tracer"


def test_resolve_data_dir_finds_inline_install(tmp_path, monkeypatch):
    _clear_data_env(monkeypatch)
    monkeypatch.setenv("HOME", str(tmp_path))
    (tmp_path / ".claude" / "plugins" / "data" / "agent-output-tracer-inline" / "sessions").mkdir(
        parents=True
    )
    resolved = resolve_data_dir()
    assert resolved is not None
    assert resolved.name == "agent-output-tracer-inline"


def test_resolve_data_dir_picks_most_recent_when_multiple(tmp_path, monkeypatch):
    """If both `-inline` and `-<marketplace>` dirs exist, pick the freshest."""
    _clear_data_env(monkeypatch)
    monkeypatch.setenv("HOME", str(tmp_path))
    data_root = tmp_path / ".claude" / "plugins" / "data"

    older = data_root / "agent-output-tracer-inline" / "sessions"
    newer = data_root / "agent-output-tracer-itosdad-agent-output-tracer" / "sessions"
    older.mkdir(parents=True)
    newer.mkdir(parents=True)
    # Force a measurable mtime gap.
    os.utime(older, (1000, 1000))
    os.utime(newer, (2000, 2000))

    resolved = resolve_data_dir()
    assert resolved.name == "agent-output-tracer-itosdad-agent-output-tracer"


def test_resolve_data_dir_env_still_wins(tmp_path, monkeypatch):
    """Explicit CLAUDE_PLUGIN_DATA must override the auto-scan."""
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("CLAUDE_PLUGIN_DATA", "/explicit/path")
    # Also create a dir that the scan would otherwise pick up.
    (tmp_path / ".claude" / "plugins" / "data" / "agent-output-tracer-inline").mkdir(parents=True)
    resolved = resolve_data_dir()
    assert str(resolved) == "/explicit/path"


# ----- config_cmd -----


@pytest.fixture
def isolated_config(tmp_path, monkeypatch):
    monkeypatch.setenv("AOT_CONFIG_DIR", str(tmp_path))
    return tmp_path


def test_config_list_shows_defaults(isolated_config):
    buf = io.StringIO()
    rc = config_cmd.config_list(stream=buf)
    assert rc == 0
    out = buf.getvalue()
    assert "defaults.density" in out
    assert "(default)" in out


def test_config_set_then_get(isolated_config):
    rc = config_cmd.config_set("defaults.density", "brief")
    assert rc == 0
    buf = io.StringIO()
    config_cmd.config_get("defaults.density", stream=buf)
    assert buf.getvalue().strip() == "brief"


def test_config_set_validates_enum(isolated_config):
    with pytest.raises(ValueError, match="defaults.density"):
        config_cmd.config_set("defaults.density", "nonsense")


def test_config_set_rejects_unknown_key(isolated_config):
    with pytest.raises(ValueError, match="unknown config key"):
        config_cmd.config_set("totally.fake", "x")


def test_config_unset_reverts_to_default(isolated_config):
    config_cmd.config_set("defaults.density", "brief")
    config_cmd.config_unset("defaults.density")
    buf = io.StringIO()
    config_cmd.config_get("defaults.density", stream=buf)
    assert buf.getvalue().strip() == "full"  # back to default


def test_config_persists_across_loads(isolated_config):
    config_cmd.config_set("user.name", "test-user")
    cfg = config_cmd.load_config()
    assert cfg.get("user", {}).get("name") == "test-user"


def test_config_path_honors_env(monkeypatch, tmp_path):
    monkeypatch.setenv("AOT_CONFIG_DIR", str(tmp_path))
    assert config_cmd.config_path().parent == tmp_path


def test_config_path_default(monkeypatch):
    monkeypatch.delenv("AOT_CONFIG_DIR", raising=False)
    expected = os.path.expanduser("~/.config/agent-output-tracer/config.toml")
    assert str(config_cmd.config_path()) == expected
