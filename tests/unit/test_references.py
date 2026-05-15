"""Unit tests for core.references — path-like token extraction and
self-paste filtering used by the hallucination detectors."""

from __future__ import annotations

from core.references import extract_path_tokens, is_grounded, strip_tracer_output

# ---------- extract_path_tokens — happy paths ----------


def test_absolute_path():
    assert "/proj/foo.md" in extract_path_tokens("see /proj/foo.md please")


def test_home_relative_path():
    assert "~/proj/hooks" in extract_path_tokens("look in ~/proj/hooks")


def test_relative_path():
    out = extract_path_tokens("run ./scripts/build.sh now")
    assert "./scripts/build.sh" in out


def test_bare_basename_with_extension():
    assert "README.md" in extract_path_tokens("update README.md please")


def test_trailing_punctuation_stripped():
    """`foo.md.` (sentence-ending period) becomes `foo.md`."""
    assert "foo.md" in extract_path_tokens("done with foo.md.")


# ---------- B3 regression: Japanese / non-ASCII rejection ----------


def test_japanese_path_like_substring_rejected():
    """`/電話/長い` is free-form Japanese prose, not a path."""
    out = extract_path_tokens("メール/電話/長い hex token をマスクします")
    assert not any("電話" in tok or "長い" in tok for tok in out), out


def test_japanese_basename_rejected():
    """`日本語.md` should not be extracted — ASCII-only base names."""
    out = extract_path_tokens("see 日本語.md for details")
    assert "日本語.md" not in out


def test_japanese_mixed_with_ascii_still_extracts_ascii():
    out = extract_path_tokens("日本語の説明と /proj/spec.md")
    assert "/proj/spec.md" in out


# ---------- B4 regression: URL scheme preservation ----------


def test_url_keeps_scheme():
    out = extract_path_tokens(
        "clone https://github.com/itosdad/agent-output-tracer.git@main please"
    )
    # The whole URL up to whitespace must survive as one token.
    assert "https://github.com/itosdad/agent-output-tracer.git@main" in out


def test_url_does_not_leak_scheme_into_separate_token():
    out = extract_path_tokens("see https://github.com/foo")
    # No degenerate `//github.com/foo` token without the scheme.
    assert "//github.com/foo" not in out


def test_http_url_also_captured():
    out = extract_path_tokens("legacy http://example.com/foo bar")
    assert "http://example.com/foo" in out


# ---------- strip_tracer_output (B2 helper) ----------


def test_strip_find_output_block():
    text = (
        "before\n"
        "find 'hallucinations': 2 match(es)\n"
        "  [18:10:06] event 1 token=/proj/ghost.md\n"
        "  [18:11:00] event 5 token=/tmp/x\n"
        "after"
    )
    stripped = strip_tracer_output(text)
    assert "/proj/ghost.md" not in stripped
    assert "/tmp/x" not in stripped
    assert "before" in stripped and "after" in stripped


def test_strip_find_nomatch_line():
    text = "before\nNo matches for find vocab 'hallucinations'.\nafter"
    stripped = strip_tracer_output(text)
    assert "hallucinations" not in stripped
    assert "before" in stripped and "after" in stripped


def test_strip_mentioned_but_not_read_output_block():
    text = (
        "see this:\n"
        "Session: abc-123\n\n"
        "Hallucination candidates (mentioned in agent response, no visible source):\n"
        "  - /proj/x.md    [first seen at 2026-01-01T00:00:01]\n"
        "  - /proj/y.md    [first seen at 2026-01-01T00:00:02]\n"
        "tail"
    )
    stripped = strip_tracer_output(text)
    assert "/proj/x.md" not in stripped
    assert "/proj/y.md" not in stripped
    assert "see this" in stripped and "tail" in stripped


def test_strip_tracer_output_handles_empty():
    assert strip_tracer_output("") == ""
    assert strip_tracer_output(None) is None


def test_strip_tracer_output_passes_through_plain_text():
    text = "user wrote /proj/spec.md and asked a question"
    assert strip_tracer_output(text) == text


# ---------- is_grounded ----------


def test_is_grounded_full_match():
    assert is_grounded("/proj/foo.md", "Please read /proj/foo.md")


def test_is_grounded_basename_match():
    assert is_grounded("/proj/foo.md", "open foo.md")


def test_is_grounded_trailing_slash_handled():
    assert is_grounded("~/proj/hooks/", "list ~/proj/hooks files")


def test_is_grounded_no_match():
    assert not is_grounded("/proj/ghost.md", "totally unrelated text")


def test_is_grounded_handles_empty_corpora():
    assert not is_grounded("/proj/foo.md", "", None, "")


def test_is_grounded_multiple_corpora():
    """Any of the corpora containing the token is sufficient."""
    assert is_grounded("/proj/foo.md", "no match here", "found /proj/foo.md in tool")
