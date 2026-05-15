"""Shared pytest fixtures."""

from __future__ import annotations

import os
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


import pytest  # noqa: E402


@pytest.fixture
def plugin_data_dir(tmp_path, monkeypatch):
    """Isolated plugin data directory per test."""
    data_dir = tmp_path / "plugin_data"
    data_dir.mkdir()
    monkeypatch.setenv("CLAUDE_PLUGIN_DATA", str(data_dir))
    return data_dir


@pytest.fixture
def plugin_root(tmp_path, monkeypatch):
    """Isolated plugin root directory per test."""
    root = tmp_path / "plugin_root"
    root.mkdir()
    monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", str(root))
    return root


@pytest.fixture
def isolated_env(plugin_data_dir, plugin_root):
    """Both env vars set, returns (root, data) tuple."""
    return plugin_root, plugin_data_dir


@pytest.fixture(autouse=True)
def _clean_env(tmp_path_factory, monkeypatch):
    """Isolate tests from caller env and from the host's real `~/.claude/`.

    The host machine may have a real Claude Code install whose
    `~/.claude/plugins/data/agent-output-tracer-*` directory would
    otherwise be picked up by `resolve_data_dir`'s auto-scan and break
    tests that assert "no data dir is configured".
    """
    for var in ("CLAUDE_PLUGIN_ROOT", "CLAUDE_PLUGIN_DATA", "CODEX_PLUGIN_DATA"):
        if var in os.environ:
            monkeypatch.delenv(var, raising=False)
    # Pin HOME at an empty tmp dir so resolve_data_dir's filesystem
    # scans see nothing unless a test explicitly seeds them.
    fake_home = tmp_path_factory.mktemp("fake_home")
    monkeypatch.setenv("HOME", str(fake_home))
    yield
