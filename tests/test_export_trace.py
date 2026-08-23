"""Tests for the verbatim trace exporter.

The secret scanner is the part worth testing hardest: a false positive trains
the operator to pass --allow-secrets (which defeats the guard), and a false
negative publishes a credential. Both directions are asserted.
"""
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _load():
    spec = importlib.util.spec_from_file_location("export_trace", ROOT / "tools" / "export_trace.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


et = _load()


@pytest.mark.parametrize("text", [
    "commit 8484a43bfe8348d95bed63468d36b268e924a88b",
    'digest: "sha256:f9f9787082b9f3b25ba11ec267f28c58a5d00a61e"',
    "Token: gho_************************************",
    "the password reset flow needs a test",
    "export DEEPGRAM_API_KEY  # value comes from the environment",
    "https://jobs.explee.com/ai-native-developer/test/api/providers",
])
def test_scanner_ignores_benign_text(text):
    assert et.scan_secrets(text) == [], f"false positive on: {text!r}"


@pytest.mark.parametrize("text,expected", [
    ("ghp_A1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6Q7r8", "github token"),  # pragma: allowlist secret
    ("sk-proj-abcdefghijklmnopqrstuvwxyz0123456789ABCD", "openai key"),  # pragma: allowlist secret
    ("sk-ant-api03-abcdefghijklmnopqrstuvwxyz012345", "anthropic key"),  # pragma: allowlist secret
    ("AKIAIOSFODNN7EXAMPLE", "aws access key"),  # pragma: allowlist secret
    ('DEEPGRAM_API_KEY="a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0"', "assigned api key"),  # pragma: allowlist secret
    ("  api_key: AbCdEfGhIjKlMnOpQrStUvWx", "assigned api key"),  # pragma: allowlist secret
    ("Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9abc", "bearer token"),  # pragma: allowlist secret
    ("-----BEGIN OPENSSH PRIVATE KEY-----", "private key block"),
])
def test_scanner_catches_credentials(text, expected):
    assert any(f.startswith(expected + ":") for f in et.scan_secrets(text)), \
        f"expected a {expected!r} finding, got {et.scan_secrets(text)}"


def test_fingerprint_is_stable_across_turn_renumbering():
    """The ack key must not depend on where in the session the match appeared.

    A live session grows while it is being worked on, so turn indices shift and
    any turn-numbered acknowledgement goes stale within minutes.
    """
    secret = "ghp_A1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6Q7r8"  # pragma: allowlist secret
    early = [_turn("user", [{"type": "text", "text": secret}])]
    later = [_turn("user", [{"type": "text", "text": "filler"}]) for _ in range(5)] + early
    _, first = et.build(early, "T", "s", Path("x.jsonl"), None)
    _, second = et.build(later, "T", "s", Path("x.jsonl"), None)
    key = lambda fs: [f.split("  (first seen:")[0] for f in fs]
    assert key(first) == key(second), "fingerprint must survive renumbering"
    assert "turn 1" in first[0] and "turn 6" in second[0], "turn is still reported for humans"


def test_fingerprint_distinguishes_different_secrets():
    a = et.scan_secrets("ghp_A1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6Q7r8")  # pragma: allowlist secret
    b = et.scan_secrets("ghp_Z9y8X7w6V5u4T3s2R1q0P9o8N7m6L5k4J3i2")  # pragma: allowlist secret
    assert a != b, "two different tokens must not share one acknowledgement"


def test_fence_survives_backticks_in_payload():
    body = "here is ```a fenced block``` inside"
    out = et.fence(body)
    bar = out.split("\n")[0]
    assert len(bar) >= 4, "fence must be longer than the longest inner run"
    assert out.endswith(bar)


def _turn(role, blocks, ts="2026-08-23T16:00:00.000Z", **extra):
    return {"type": role, "timestamp": ts, "cwd": "/tmp", "version": "1.0",
            "message": {"role": role, "content": blocks,
                        **({"model": "claude-opus-5"} if role == "assistant" else {})},
            **extra}


def test_build_renders_every_turn_and_block_kind():
    records = [
        _turn("user", [{"type": "text", "text": "do the thing"}]),
        _turn("assistant", [
            {"type": "thinking", "thinking": "weighing options"},
            {"type": "text", "text": "on it"},
            {"type": "tool_use", "name": "Bash", "input": {"command": "ls"}},
        ]),
        _turn("user", [{"type": "tool_result", "content": "file.txt"}]),
        _turn("assistant", [{"type": "text", "text": "done"}], isSidechain=True),
    ]
    md, findings = et.build(records, "T", "sess-1", Path("x.jsonl"), None)
    assert findings == []
    assert "weighing options" in md, "reasoning must be preserved verbatim"
    assert "do the thing" in md and "on it" in md and "done" in md
    assert '"command": "ls"' in md, "tool inputs must be preserved verbatim"
    assert "file.txt" in md, "tool results must be preserved verbatim"
    assert "Assistant (subagent)" in md, "subagent turns must be labelled"
    assert md.count("## [") == 4, "every turn gets its own section"


def test_build_truncation_is_visible_not_silent():
    long_output = "x" * 5000
    records = [_turn("user", [{"type": "tool_result", "content": long_output}])]
    md, _ = et.build(records, "T", "s", Path("x.jsonl"), 100)
    assert "truncated by --max-result" in md, "truncation must announce itself"
    assert "4900 characters truncated" in md


def test_build_without_max_result_keeps_full_output():
    long_output = "y" * 5000
    records = [_turn("user", [{"type": "tool_result", "content": long_output}])]
    md, _ = et.build(records, "T", "s", Path("x.jsonl"), None)
    assert long_output in md
    assert "truncated" not in md


def test_allowlist_pragma_exempts_only_its_own_line():
    vouched = 'KEY = "ghp_A1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6Q7r8"  # pragma: allowlist secret'
    assert et.scan_secrets(vouched) == []
    # the exemption must not bleed into neighbouring lines
    mixed = vouched + "\nleaked = ghp_Z9y8X7w6V5u4T3s2R1q0P9o8N7m6L5k4J3i2"
    assert any(f.startswith("github token:") for f in et.scan_secrets(mixed))


def test_build_surfaces_secrets_as_findings_with_turn_number():
    records = [
        _turn("user", [{"type": "text", "text": "hello"}]),
        _turn("assistant", [{"type": "text", "text": "ghp_A1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6Q7r8"}]),
    ]
    _, findings = et.build(records, "T", "s", Path("x.jsonl"), None)
    assert any("turn 2" in f and f.startswith("github token:") for f in findings)


def test_build_rejects_a_session_with_no_turns():
    with pytest.raises(SystemExit):
        et.build([{"type": "mode", "mode": "x"}], "T", "s", Path("x.jsonl"), None)


def test_tool_result_list_content_is_flattened():
    blocks = [{"type": "text", "text": "line one"}, {"type": "image", "source": {}}]
    out = et.render_tool_result(blocks)
    assert "line one" in out and "image omitted" in out
