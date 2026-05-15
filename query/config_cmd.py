"""`aot config` — operate on a user TOML config without hand-editing.

Phase D-1 scope: get / set / unset / list of scalar values stored at
`~/.config/agent-output-tracer/config.toml`. Schema for richer keys
(bridges, find vocab) lands in later phases.

The file is written with a tiny TOML emitter (no third-party dep): we
own every value we write, so quoting rules stay simple. Reads use the
stdlib `tomllib` (Python 3.11+) — the CLI surface already requires
3.11+, so this is safe.
"""

from __future__ import annotations

import os
import sys
import tomllib
from pathlib import Path
from typing import IO

DEFAULTS: dict[str, object] = {
    "defaults.density": "full",  # 'brief' | 'full' | 'raw' | 'json'
    "defaults.color": "auto",  # 'auto' | 'always' | 'never'
    "user.name": "",
}

VALID_DENSITY = ("brief", "full", "raw", "json")
VALID_COLOR = ("auto", "always", "never")


def config_path() -> Path:
    base = os.environ.get("AOT_CONFIG_DIR")
    if base:
        return Path(base) / "config.toml"
    return Path.home() / ".config" / "agent-output-tracer" / "config.toml"


def load_config() -> dict:
    p = config_path()
    if not p.exists():
        return {}
    return tomllib.loads(p.read_text(encoding="utf-8"))


def _flatten(d: dict, prefix: str = "") -> dict[str, object]:
    out: dict[str, object] = {}
    for k, v in d.items():
        key = f"{prefix}.{k}" if prefix else k
        if isinstance(v, dict):
            out.update(_flatten(v, key))
        else:
            out[key] = v
    return out


def _unflatten(flat: dict[str, object]) -> dict:
    root: dict = {}
    for key, val in flat.items():
        parts = key.split(".")
        cur = root
        for part in parts[:-1]:
            cur = cur.setdefault(part, {})
        cur[parts[-1]] = val
    return root


def _validate(key: str, value: str) -> object:
    """Return the (typed) value to store, or raise ValueError."""
    if key == "defaults.density":
        if value not in VALID_DENSITY:
            raise ValueError(
                f"defaults.density must be one of {', '.join(VALID_DENSITY)}, got {value!r}"
            )
        return value
    if key == "defaults.color":
        if value not in VALID_COLOR:
            raise ValueError(
                f"defaults.color must be one of {', '.join(VALID_COLOR)}, got {value!r}"
            )
        return value
    if key == "user.name":
        return value
    raise ValueError(
        f"unknown config key {key!r}. Valid keys: {', '.join(sorted(DEFAULTS))}"
    )


def _emit_toml(tree: dict) -> str:
    """Tiny TOML writer for the keys we own.

    Restrictions accepted because we control every value:
      - only scalar leaves (str / int / float / bool)
      - one level of nesting (matches our schema)
      - strings written with a basic-string quote pass
    """

    def fmt(v: object) -> str:
        if isinstance(v, bool):
            return "true" if v else "false"
        if isinstance(v, (int, float)):
            return str(v)
        if isinstance(v, str):
            escaped = v.replace("\\", "\\\\").replace('"', '\\"')
            return f'"{escaped}"'
        raise TypeError(f"can't serialize {type(v).__name__} to TOML")

    sections: dict[str, list[tuple[str, object]]] = {"": []}
    for section, body in tree.items():
        if isinstance(body, dict):
            sections[section] = list(body.items())
        else:
            sections[""].append((section, body))

    out: list[str] = []
    if sections[""]:
        for k, v in sections[""]:
            out.append(f"{k} = {fmt(v)}")
        out.append("")
    for section, entries in sections.items():
        if not section:
            continue
        out.append(f"[{section}]")
        for k, v in entries:
            out.append(f"{k} = {fmt(v)}")
        out.append("")
    return "\n".join(out).rstrip() + "\n"


def _save(tree: dict) -> None:
    p = config_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(_emit_toml(tree), encoding="utf-8")


# ----- subcommand entry points -----


def config_get(key: str, *, stream: IO[str] | None = None) -> int:
    if stream is None:
        stream = sys.stdout
    flat = _flatten(load_config())
    if key in flat:
        stream.write(f"{flat[key]}\n")
        return 0
    if key in DEFAULTS:
        stream.write(f"{DEFAULTS[key]}\n")
        return 0
    raise ValueError(
        f"unknown config key {key!r}. Valid keys: {', '.join(sorted(DEFAULTS))}"
    )


def config_set(key: str, value: str) -> int:
    typed = _validate(key, value)
    flat = _flatten(load_config())
    flat[key] = typed
    _save(_unflatten(flat))
    return 0


def config_unset(key: str) -> int:
    if key not in DEFAULTS:
        raise ValueError(
            f"unknown config key {key!r}. Valid keys: {', '.join(sorted(DEFAULTS))}"
        )
    flat = _flatten(load_config())
    flat.pop(key, None)
    _save(_unflatten(flat))
    return 0


def config_list(*, stream: IO[str] | None = None) -> int:
    """Print every known key with `value (source)`."""
    if stream is None:
        stream = sys.stdout
    flat = _flatten(load_config())
    for key in sorted(DEFAULTS):
        if key in flat:
            stream.write(f"{key} = {flat[key]!r}  (user)\n")
        else:
            stream.write(f"{key} = {DEFAULTS[key]!r}  (default)\n")
    return 0
