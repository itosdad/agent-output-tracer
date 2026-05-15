"""Sticky-defaults config for the TUI.

Stores last-used inputs (Find vocab, Trace phrase, Search regex,
Export format) in `~/.config/aot/config.toml` so the next launch
pre-fills the relevant fields. Theme is intentionally NOT persisted —
it auto-detects from the newest session's engine on every launch, and
`t` stays a per-session override.

Schema:

    [history]
    find_vocab     = "hallucinations"
    trace_phrase   = "hooks_wiring"
    search_regex   = "JWT|token"
    export_format  = "markdown"
    export_safe_share = true
    export_excerpt = 0

Reads via `tomllib` (stdlib, 3.11+). Writes use a hand-rolled minimal
encoder for the flat shapes we need — avoids pulling `tomli_w` into
the wheel for ~30 lines of code.

Failure modes are silent: a corrupted config file returns `{}`, a
missing directory is created on write, IO errors during write are
suppressed (saving sticky defaults must never crash the TUI).
"""

from __future__ import annotations

import os
import tomllib
from pathlib import Path
from typing import Any


def _config_path() -> Path:
    """Return the on-disk config path, honouring `$AOT_CONFIG_HOME` for
    tests and `$XDG_CONFIG_HOME` for Linux conventions."""
    if override := os.environ.get("AOT_CONFIG_HOME"):
        return Path(override) / "config.toml"
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "aot" / "config.toml"


def load_config() -> dict[str, Any]:
    """Read the config from disk. Returns `{}` if missing or unreadable."""
    path = _config_path()
    if not path.exists():
        return {}
    try:
        with path.open("rb") as f:
            return tomllib.load(f)
    except Exception:
        return {}


def save_config(updates: dict[str, Any]) -> None:
    """Merge `updates` into the on-disk config. Best-effort — errors
    are swallowed so persistence never breaks the foreground TUI."""
    try:
        path = _config_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        current = load_config()
        merged = _deep_merge(current, updates)
        path.write_text(_encode_toml(merged), encoding="utf-8")
    except Exception:
        pass


def get_history(key: str, default: Any = None) -> Any:
    """Return `history.<key>` or `default` if absent."""
    return load_config().get("history", {}).get(key, default)


def set_history(key: str, value: Any) -> None:
    """Persist a single `history.<key>` entry."""
    save_config({"history": {key: value}})


def clear_history() -> None:
    """Wipe the `[history]` section without going through the merge
    path (which would recurse and preserve existing keys). Other
    top-level sections, if we ever add them, are left untouched."""
    try:
        path = _config_path()
        if not path.exists():
            return
        current = load_config()
        current.pop("history", None)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(_encode_toml(current), encoding="utf-8")
    except Exception:
        pass


def _deep_merge(base: dict, overlay: dict) -> dict:
    """Recursive dict merge — overlay wins on scalar collisions."""
    out = dict(base)
    for k, v in overlay.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def _encode_toml(data: dict[str, Any]) -> str:
    """Minimal TOML encoder for our flat-with-one-section shape.

    Handles: top-level scalars, exactly-one-level-deep tables, string
    / int / bool / float values. Anything more exotic (datetimes,
    nested arrays of tables, etc.) is out of scope — we never write
    that shape.
    """
    lines: list[str] = []
    scalars: dict[str, Any] = {k: v for k, v in data.items() if not isinstance(v, dict)}
    tables: dict[str, dict] = {k: v for k, v in data.items() if isinstance(v, dict)}
    for k, v in scalars.items():
        lines.append(f"{k} = {_encode_value(v)}")
    for table_name, table in tables.items():
        if lines:
            lines.append("")
        lines.append(f"[{table_name}]")
        for k, v in table.items():
            lines.append(f"{k} = {_encode_value(v)}")
    return "\n".join(lines) + "\n"


def _encode_value(v: Any) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return str(v)
    if isinstance(v, str):
        # Escape backslash and double-quote per TOML spec; reject control
        # chars below 0x20 silently by mapping to a space (config keys
        # are user-typed shell text, none of these matter in practice).
        escaped = v.replace("\\", "\\\\").replace('"', '\\"')
        escaped = "".join(c if c >= " " or c in ("\t",) else " " for c in escaped)
        return f'"{escaped}"'
    if isinstance(v, list):
        return "[" + ", ".join(_encode_value(x) for x in v) + "]"
    return _encode_value(str(v))
