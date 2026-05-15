"""OpenTelemetry sidecar export (DESIGN_FORENSIC_UX §8.3).

Emits per-session / per-turn / per-tool spans so an organisation's
existing OTel collector can ingest AOT data without AOT needing to host
a backend. The bridge is:

  - **default off** — `aot config set bridges.otel.enabled true` to
    opt in
  - **redaction-default-on** — `log_user_prompt` and
    `log_raw_tool_response` both default False
  - **batch only in D-6** — streaming export is Phase E candidate (OQ3)

Because `opentelemetry-sdk` is an optional dependency, the module is
written to gracefully degrade: when the package isn't installed,
`is_available()` returns False and the export function raises a clear
ImportError.
"""

from __future__ import annotations

from collections.abc import Iterable


def is_available() -> bool:
    try:
        import opentelemetry  # noqa: F401
        from opentelemetry.sdk.trace import TracerProvider  # noqa: F401
    except ImportError:
        return False
    return True


# --- span model (engine-neutral payload regardless of whether OTel is wired) ---


def build_spans(
    events: list[dict],
    metadata: dict | None,
    *,
    log_user_prompt: bool = False,
    log_raw_tool_response: bool = False,
) -> list[dict]:
    """Build the structured span payload AOT wants to publish.

    Returns a list of `{name, parent, attributes, start_ts, end_ts}`
    dicts. Tests and console exporters can consume this directly; the
    real OTel exporter wraps it (see `export_spans`).
    """
    meta = metadata or {}
    sid = meta.get("session_id") or (events[0]["session_id"] if events else "?")
    spans: list[dict] = []

    session_span = {
        "name": "aot.session",
        "parent": None,
        "attributes": {
            "session_id_short": sid[:12],
            "engine": meta.get("engine"),
            "engine_version": meta.get("engine_version"),
            "ts_start": meta.get("ts_start"),
            "ts_end": meta.get("ts_end"),
            "tool_calls_total": meta.get("tool_calls_total"),
            "anomaly_counters": meta.get("anomaly_counters", {}),
        },
        "start_ts": meta.get("ts_start"),
        "end_ts": meta.get("ts_end"),
    }
    spans.append(session_span)

    # turns are keyed by correlation_id
    turn_by_id: dict[str, dict] = {}
    for ev in events:
        cid = ev.get("correlation_id") or ev.get("turn_id")
        if not cid:
            continue
        if cid not in turn_by_id:
            turn_by_id[cid] = {
                "name": "aot.turn",
                "parent": "aot.session",
                "attributes": {
                    "correlation_id": cid,
                    "user_prompt_present": False,
                    "agent_response_present": False,
                },
                "start_ts": ev.get("ts"),
                "end_ts": ev.get("ts"),
            }
        turn = turn_by_id[cid]
        if ev.get("ts"):
            if not turn["start_ts"] or ev["ts"] < turn["start_ts"]:
                turn["start_ts"] = ev["ts"]
            if not turn["end_ts"] or ev["ts"] > turn["end_ts"]:
                turn["end_ts"] = ev["ts"]
        if ev.get("event_type") == "user_prompt":
            turn["attributes"]["user_prompt_present"] = True
        if ev.get("event_type") == "agent_response":
            turn["attributes"]["agent_response_present"] = True
    spans.extend(turn_by_id.values())

    for ev in events:
        et = ev.get("event_type")
        if et != "pre_tool" and et != "post_tool":
            continue
        cid = ev.get("correlation_id") or ev.get("turn_id")
        attrs = {
            "tool_name": ev.get("tool_name"),
            "paths_count": len(ev.get("paths") or []),
            "response_size_bytes": ev.get("response_size_bytes") or ev.get("result_bytes"),
            "response_sha256": ev.get("response_sha256"),
            "duration_ms": ev.get("duration_ms"),
            "permission_mode": ev.get("permission_mode"),
        }
        if log_raw_tool_response and ev.get("tool_response"):
            attrs["tool_response_preview"] = ev["tool_response"][:512]
        spans.append(
            {
                "name": "aot.tool",
                "parent": "aot.turn",
                "correlation_id": cid,
                "attributes": {k: v for k, v in attrs.items() if v is not None},
                "start_ts": ev.get("ts"),
                "end_ts": ev.get("ts"),
            }
        )

    for finding in meta.get("findings", []) or []:
        spans.append(
            {
                "name": "aot.finding",
                "parent": "aot.session",
                "attributes": {
                    "kind": finding.get("kind"),
                    "event_idx": finding.get("event_idx"),
                    "steps": finding.get("steps"),
                },
                "start_ts": finding.get("ts"),
                "end_ts": finding.get("ts"),
            }
        )

    if log_user_prompt:
        for ev in events:
            if ev.get("event_type") == "user_prompt":
                spans.append(
                    {
                        "name": "aot.user_prompt",
                        "parent": "aot.session",
                        "attributes": {
                            "text": (ev.get("user_prompt_text") or "")[:1024],
                        },
                        "start_ts": ev.get("ts"),
                        "end_ts": ev.get("ts"),
                    }
                )

    return spans


def export_spans(spans: Iterable[dict], *, exporter: str = "console") -> None:
    """Hand the prebuilt spans off to OTel.

    `exporter`:
      - `console`: just dump them to stdout via the SDK's console exporter
      - `otlp-http` / `otlp-grpc`: requires the matching exporter package

    Raises ImportError if OTel isn't installed.
    """
    if not is_available():
        raise ImportError(
            "opentelemetry-sdk is not installed. "
            "Install with: pip install 'agent-output-tracer[otel]' "
            "(or use the console exporter target for a dry run)."
        )
    # Lazy imports below — only happen when the user opted in.
    from opentelemetry import trace
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import ConsoleSpanExporter, SimpleSpanProcessor

    provider = TracerProvider()
    if exporter == "console":
        provider.add_span_processor(SimpleSpanProcessor(ConsoleSpanExporter()))
    else:
        raise ValueError(f"exporter {exporter!r} is not implemented in D-6 (console only).")
    trace.set_tracer_provider(provider)
    tracer = trace.get_tracer("aot")
    for span in spans:
        with tracer.start_as_current_span(span["name"]) as otel_span:
            for k, v in (span.get("attributes") or {}).items():
                if v is None:
                    continue
                try:
                    otel_span.set_attribute(
                        k, v if isinstance(v, (str, int, float, bool)) else str(v)
                    )
                except Exception:
                    pass
