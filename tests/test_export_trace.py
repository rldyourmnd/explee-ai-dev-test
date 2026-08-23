"""Tests for the verbatim trace exporter.

The secret scanner is the part worth testing hardest: a false positive trains
the operator to pass --allow-secrets (which defeats the guard), and a false
negative publishes a credential. Both directions are asserted.
"""
import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _load():
    spec = importlib.util.spec_from_file_location("export_trace", ROOT / "tools" / "export_trace.py")
    assert spec is not None and spec.loader is not None, "exporter must be loadable"
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
    def key(findings):
        return [f.split("  (first seen:")[0] for f in findings]

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


def _fake_projects(tmp_path, layout):
    """Build a fake ~/.claude/projects tree: {slug: [session_stem, ...]}."""
    for slug, sessions in layout.items():
        project = tmp_path / slug
        project.mkdir(parents=True)
        for stem in sessions:
            (project / f"{stem}.jsonl").write_text("{}\n", encoding="utf-8")
    return tmp_path


# The regression this file exists for: an unscoped --list globbed every project
# on the machine, so one call wrote 20 rows of unrelated client project names
# into a trace that publishes verbatim, and the trace had to be quarantined.
def test_list_sessions_never_names_another_project(tmp_path, capsys, monkeypatch):
    monkeypatch.setattr(et, "PROJECTS", _fake_projects(tmp_path, {
        "-Users-dev-work-this-project": ["aaaaaaaa-0000-0000-0000-000000000000"],
        "-Users-dev-work-unrelated-client": ["bbbbbbbb-1111-1111-1111-111111111111"],
    }))

    assert et.list_sessions("-Users-dev-work-this-project") == 0

    captured = capsys.readouterr()
    assert "aaaaaaaa-0000-0000-0000-000000000000" in captured.out
    assert "unrelated-client" not in captured.out + captured.err
    assert "bbbbbbbb" not in captured.out + captured.err


def test_list_sessions_defaults_to_the_current_project(tmp_path, capsys, monkeypatch):
    cwd = tmp_path / "cwd"
    cwd.mkdir()
    monkeypatch.setattr(et, "PROJECTS", _fake_projects(tmp_path / "projects", {
        et.project_slug(cwd): ["cccccccc-2222-2222-2222-222222222222"],
        "-Users-dev-work-unrelated-client": ["bbbbbbbb-1111-1111-1111-111111111111"],
    }))
    monkeypatch.chdir(cwd)

    assert et.list_sessions(None) == 0

    captured = capsys.readouterr()
    assert "cccccccc-2222-2222-2222-222222222222" in captured.out
    assert "unrelated-client" not in captured.out + captured.err


def test_list_sessions_unknown_project_does_not_enumerate_the_others(tmp_path, capsys, monkeypatch):
    # The helpful version of this error - "did you mean one of these?" - would
    # reintroduce the leak on the failure path.
    monkeypatch.setattr(et, "PROJECTS", _fake_projects(tmp_path, {
        "-Users-dev-work-unrelated-client": ["bbbbbbbb-1111-1111-1111-111111111111"],
    }))

    assert et.list_sessions("-Users-dev-work-absent") == 2

    captured = capsys.readouterr()
    assert captured.out == ""
    assert "unrelated-client" not in captured.err
    assert "bbbbbbbb" not in captured.err


def test_project_slug_matches_claude_code_layout():
    assert et.project_slug(Path("/Users/dev/work/proj")) == "-Users-dev-work-proj"


# A trace that drops content while its header claims nothing was dropped is not
# verbatim, whether or not the loss is disclosed inline. Every path that can
# lose content must be recorded so main() can refuse to write the file.
def test_malformed_jsonl_line_is_recorded_not_skipped(tmp_path):
    log = tmp_path / "s.jsonl"
    log.write_text('{"type":"user","message":{}}\n{"type":"assis\n', encoding="utf-8")
    losses = []
    records = et.load(log, losses)
    assert len(records) == 1
    assert any("malformed JSON on line 2" in loss for loss in losses)


def test_invalid_utf8_is_recorded_not_silently_replaced(tmp_path):
    log = tmp_path / "s.jsonl"
    log.write_bytes(b'{"type":"user","message":{"content":"caf\xff"}}\n')
    losses = []
    et.load(log, losses)
    assert any("invalid UTF-8" in loss for loss in losses)


def test_load_without_a_losses_sink_still_raises_on_bad_bytes(tmp_path):
    log = tmp_path / "s.jsonl"
    log.write_bytes(b'\xff\xfe\n')
    with pytest.raises(UnicodeDecodeError):
        et.load(log)


def test_image_block_omission_is_recorded():
    losses = []
    et.render_tool_result([{"type": "image", "source": {}}], losses)
    assert any("image block omitted" in loss for loss in losses)


def test_truncation_is_recorded_as_a_loss():
    records = [_turn("assistant", [{"type": "tool_result", "content": "x" * 5000}])]
    losses = []
    et.build(records, "T", "s", Path("x.jsonl"), 100, losses)
    assert any("4900 characters of tool result truncated" in loss for loss in losses)


def test_lossless_session_records_no_losses():
    records = [_turn("user", [{"type": "text", "text": "hello"}]),
               _turn("assistant", [{"type": "tool_result", "content": "short"}])]
    losses = []
    md, _ = et.build(records, "T", "s", Path("x.jsonl"), None, losses)
    assert losses == []
    assert "not verbatim" not in md


def test_header_retracts_the_verbatim_claim_when_content_was_lost():
    records = [_turn("assistant", [{"type": "tool_result", "content": "x" * 5000}])]
    losses = []
    md, _ = et.build(records, "T", "s", Path("x.jsonl"), 100, losses)
    assert "**This export is not verbatim.**" in md
    # the retraction belongs above the transcript, not buried at the loss site
    assert md.index("not verbatim") < md.index("Tool result")


# The leak that quarantined two traces was a project name, not a credential, so
# the secret scanner never saw it. These assert the direction that matters: a
# foreign slug must block the export, and the project's own slug must not.
THIS = "-Users-dev-work-this-project"
OTHER = "-Users-dev-work-unrelated-client"


def test_foreign_project_slug_is_reported():
    assert et.scan_foreign_slugs(f"listing shows {OTHER} here", THIS) == [
        f"foreign project slug: {OTHER}"]


def test_own_project_slug_is_not_reported():
    assert et.scan_foreign_slugs(f"exporting from {THIS}/abc.jsonl", THIS) == []


def test_a_prefix_of_the_own_slug_is_not_a_foreign_project():
    # the same project named shorter, e.g. a home directory mentioned on its own
    assert et.scan_foreign_slugs("-Users-dev-work", THIS) == []


def test_hyphenated_prose_is_not_mistaken_for_a_slug():
    # false positives here would train the operator to reach for the override
    assert et.scan_foreign_slugs("the -home-page-hero element", THIS) == []


def test_scan_without_a_permitted_slug_reports_nothing():
    assert et.scan_foreign_slugs(f"{OTHER} appears", None) == []


def test_build_blocks_on_a_foreign_slug_in_a_tool_result():
    records = [
        _turn("user", [{"type": "text", "text": "list the sessions"}]),
        _turn("assistant", [{"type": "tool_result",
                             "content": f"2026-08-02 22:12  1410K  aaaa  {OTHER}"}]),
    ]
    _, findings = et.build(records, "T", "s", Path("x.jsonl"), None, None, THIS)
    assert any(f.startswith(f"foreign project slug: {OTHER}") and "turn 2" in f
               for f in findings), findings


def test_build_reports_nothing_for_a_trace_naming_only_this_project():
    records = [_turn("user", [{"type": "tool_result",
                               "content": f"2026-08-02 22:12  1410K  aaaa  {THIS}"}])]
    _, findings = et.build(records, "T", "s", Path("x.jsonl"), None, None, THIS)
    assert findings == []


def test_deep_slug_under_another_account_is_still_reported():
    # not this operator's home, but far too deep to be prose
    other = "-home-someone-else-clients-acme-backend"
    assert et.scan_foreign_slugs(other, THIS) == [f"foreign project slug: {other}"]


def test_shallow_slug_under_another_account_is_a_known_miss():
    # documents the stated limit rather than pretending coverage is total:
    # a different user's shallow project is indistinguishable from prose here
    assert et.scan_foreign_slugs("-home-bob-proj", THIS) == []


# A block type this exporter has never seen must be reported as lost. The old
# if/elif chain had no else, so a future Claude Code block type would vanish
# while the header still claimed nothing was dropped.
def test_unknown_block_type_is_recorded_as_a_loss():
    records = [_turn("assistant", [{"type": "server_tool_use", "id": "x"}])]
    losses = []
    et.build(records, "T", "s", Path("x.jsonl"), None, losses)
    assert any("unsupported content block type 'server_tool_use'" in x for x in losses), losses


def test_non_dict_block_is_recorded_as_a_loss():
    records = [_turn("assistant", ["a bare string", 42])]
    losses = []
    et.build(records, "T", "s", Path("x.jsonl"), None, losses)
    assert sum("not an object" in x for x in losses) == 2, losses


def test_scalar_message_content_is_recorded_as_a_loss():
    records = [_turn("assistant", [])]
    records[0]["message"]["content"] = 7
    losses = []
    et.build(records, "T", "s", Path("x.jsonl"), None, losses)
    assert any("message.content was int" in x for x in losses), losses


def test_null_message_content_is_recorded_as_a_loss():
    records = [_turn("assistant", [])]
    records[0]["message"]["content"] = None
    losses = []
    et.build(records, "T", "s", Path("x.jsonl"), None, losses)
    assert any("message.content was NoneType" in x for x in losses), losses


def test_mixed_valid_and_invalid_blocks_renders_the_valid_and_records_the_rest():
    records = [_turn("assistant", [
        {"type": "text", "text": "kept"},
        None,
        {"type": "future_kind"},
    ])]
    losses = []
    md, _ = et.build(records, "T", "s", Path("x.jsonl"), None, losses)
    assert "kept" in md, "a valid block must still render"
    assert any("not an object" in x for x in losses)
    assert any("future_kind" in x for x in losses)
    assert "**This export is not verbatim.**" in md


def test_known_block_types_are_not_reported_as_unsupported():
    records = [_turn("assistant", [
        {"type": "thinking", "thinking": "t"},
        {"type": "tool_use", "name": "Bash", "input": {}},
        {"type": "tool_result", "content": "ok"},
        {"type": "text", "text": "done"},
    ])]
    losses = []
    et.build(records, "T", "s", Path("x.jsonl"), None, losses)
    assert losses == [], losses


def _session(tmp_path, blocks, slug="-Users-dev-work-this-project"):
    """Write a one-turn session under a fake PROJECTS root; return (root, uuid)."""
    import json as _json
    uid = "aaaaaaaa-1111-2222-3333-444444444444"
    proj = tmp_path / slug
    proj.mkdir(parents=True, exist_ok=True)
    rec = {"type": "assistant", "timestamp": "2026-08-23T16:00:00.000Z", "cwd": "/tmp",
           "version": "1", "message": {"role": "assistant", "model": "m", "content": blocks}}
    (proj / f"{uid}.jsonl").write_text(_json.dumps(rec) + "\n", encoding="utf-8")
    return tmp_path, uid


def _run(monkeypatch, tmp_path, root, uid, *argv):
    monkeypatch.setattr(et, "PROJECTS", root)
    monkeypatch.setattr("sys.argv", ["export_trace.py", "--session", uid,
                                     "--out", str(tmp_path / "OUT.md"), *argv])
    return et.main()


FIXTURE_KEY = "ghp_A1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6Q7r8"  # pragma: allowlist secret
FOREIGN = "-Users-dev-work-unrelated-client"


def test_allow_secrets_does_not_wave_through_a_foreign_slug(tmp_path, monkeypatch, capsys):
    # the whole point of separating them: a synthetic credential is routine to
    # acknowledge, another client's directory name is not
    root, uid = _session(tmp_path, [{"type": "text", "text": f"{FIXTURE_KEY} and {FOREIGN}"}])
    assert _run(monkeypatch, tmp_path, root, uid, "--allow-secrets") == 3
    assert not (tmp_path / "OUT.md").exists()
    assert "does not cover project slugs" in capsys.readouterr().err


def test_allow_secrets_still_waves_through_a_credential_alone(tmp_path, monkeypatch):
    root, uid = _session(tmp_path, [{"type": "text", "text": FIXTURE_KEY}])
    assert _run(monkeypatch, tmp_path, root, uid, "--allow-secrets") == 0
    assert (tmp_path / "OUT.md").exists()


def test_submission_mode_refuses_every_override(tmp_path, monkeypatch, capsys):
    root, uid = _session(tmp_path, [{"type": "text", "text": "clean"}])
    for flag in (["--allow-lossy"], ["--allow-secrets"], ["--max-result", "10"],
                 ["--allow-finding", "whatever"]):
        assert _run(monkeypatch, tmp_path, root, uid, "--submission", *flag) == 5
        assert "A published trace is verbatim and clean" in capsys.readouterr().err


def test_submission_mode_exports_a_clean_session(tmp_path, monkeypatch):
    root, uid = _session(tmp_path, [{"type": "text", "text": "nothing to hide"}])
    assert _run(monkeypatch, tmp_path, root, uid, "--submission") == 0
    assert "nothing to hide" in (tmp_path / "OUT.md").read_text()


# Excision: remove one contaminated tool result, leave a generated marker. The
# alternative is withholding a whole trace over one block, which scores as a
# missing deliverable rather than as discretion.
def _call_and_result(turn_blocks_id, output):
    use = {"type": "tool_use", "id": turn_blocks_id, "name": "ListAgents", "input": {}}
    res = {"type": "tool_result", "tool_use_id": turn_blocks_id, "content": output}
    return use, res


def test_excision_by_turn_replaces_the_result_with_a_generated_marker():
    use, res = _call_and_result("tu_1", "alpha\nbeta\ngamma")
    records = [_turn("assistant", [use]), _turn("user", [res])]
    md, _ = et.build(records, "T", "s", Path("x.jsonl"), None, None, None, {"2"})
    assert "alpha" not in md and "gamma" not in md, "excised content must not survive"
    assert "[EXPORTER] Tool result removed." in md
    assert "3 lines removed" in md
    assert "ListAgents" in md, "the marker names what produced the result"


def test_excision_by_tool_use_id_is_equivalent():
    use, res = _call_and_result("tu_42", "one\ntwo")
    records = [_turn("assistant", [use]), _turn("user", [res])]
    md, _ = et.build(records, "T", "s", Path("x.jsonl"), None, None, None, {"tu_42"})
    assert "2 lines removed" in md and "one" not in md


def test_excision_declares_itself_in_the_header():
    use, res = _call_and_result("tu_1", "x\ny")
    records = [_turn("assistant", [use]), _turn("user", [res])]
    md, _ = et.build(records, "T", "s", Path("x.jsonl"), None, None, None, {"2"})
    assert "Verbatim except for 1 documented excision." in md
    assert md.index("Verbatim except") < md.index("[EXPORTER]"), "header states it first"


def test_excision_takes_only_the_named_result():
    u1, r1 = _call_and_result("tu_1", "leaked\nnames")
    u2, r2 = _call_and_result("tu_2", "keep this result")
    records = [_turn("assistant", [u1, u2]), _turn("user", [r1]), _turn("user", [r2])]
    md, _ = et.build(records, "T", "s", Path("x.jsonl"), None, None, None, {"tu_1"})
    assert "leaked" not in md
    assert "keep this result" in md, "excision must not take more than addressed"


def test_excised_content_no_longer_blocks_the_export():
    # excising the leak must also clear the finding that made it necessary
    use, res = _call_and_result("tu_1", "-Users-dev-work-unrelated-client")
    records = [_turn("assistant", [use]), _turn("user", [res])]
    _, before = et.build(records, "T", "s", Path("x.jsonl"), None, None,
                         "-Users-dev-work-this-project")
    _, after = et.build(records, "T", "s", Path("x.jsonl"), None, None,
                        "-Users-dev-work-this-project", {"tu_1"})
    assert any("foreign project slug" in f for f in before)
    assert not any("foreign project slug" in f for f in after)


# Scan by source, not content: a session listing prints bare names, so there is
# no pattern to match until after the name has leaked.
def test_enumerating_call_is_flagged_by_its_source_not_its_output():
    use, res = _call_and_result("tu_1", "perfectly innocent looking text")
    records = [_turn("assistant", [use]), _turn("user", [res])]
    _, findings = et.build(records, "T", "s", Path("x.jsonl"), None)
    assert any(f.startswith("enumerating call (session listing)") for f in findings), findings


def test_enumerating_bash_commands_are_flagged():
    for cmd, label in [("docker ps -a", "container listing"),
                       ("gh repo list someorg", "repository listing"),
                       ("cat ~/.ssh/config", "host configuration"),
                       ("modal app list", "container listing")]:
        assert et.enumerating_reason("Bash", cmd) == label, cmd


def test_ordinary_in_project_commands_are_not_flagged():
    # a guard that fires on every ls gets switched off
    for cmd in ["ls -la task3-harness-artifact/", "grep -rn foo tools/",
                "git status --short", "ls ~/.claude/skills"]:
        assert et.enumerating_reason("Bash", cmd) is None, cmd


def test_excision_never_touches_reasoning_messages_or_other_blocks():
    """Excising by turn takes the tool results in it and nothing else.

    docs/TASK.md wants every message and every correction. An excision removes
    output from a command that should not have been run - never a turn's
    thinking, text, or the tool call itself.
    """
    use, res = _call_and_result("tu_1", "listing\nlines")
    records = [
        _turn("assistant", [{"type": "thinking", "thinking": "why I did it"},
                            {"type": "text", "text": "a correction I made"}, use]),
        _turn("user", [res]),
    ]
    md, _ = et.build(records, "T", "s", Path("x.jsonl"), None, None, None, {"1", "2"})
    assert "why I did it" in md, "reasoning must survive"
    assert "a correction I made" in md, "messages and corrections must survive"
    assert "Tool call — `ListAgents`" in md, "the call itself stays; only its result goes"
    assert "listing" not in md


def test_excision_removes_the_whole_result_not_the_matching_lines():
    # 4 bad names inside 52 lines: leaving 48 would invite the question of what
    # the rest contained, so the unit of removal is the whole result
    body = "\n".join(["clean"] * 48 + ["-Users-dev-work-unrelated-client"] * 4)
    use, res = _call_and_result("tu_1", body)
    records = [_turn("assistant", [use]), _turn("user", [res])]
    md, _ = et.build(records, "T", "s", Path("x.jsonl"), None, None, None, {"tu_1"})
    assert "clean" not in md, "the whole result goes, not just the matching lines"
    assert "52 lines removed" in md


# Four false positives reported from task 2's real session. A guard that cries
# wolf gets routed around, so each is pinned here with the command that produced
# it, alongside the true positive it must not stop catching.
import json as _json


def _bash(cmd, description="check modal container listing settings"):
    return _json.dumps({"command": cmd, "description": description})


def test_grep_of_own_source_is_not_a_container_listing():
    # matched the word max_containerS; nothing was listed
    cmd = 'grep -n "max_containers|scaledown_window|gpu=" task2-stt-benchmark/modal_app/*.py'
    assert et.enumerating_reason("Bash", _bash(cmd)) is None


def test_help_output_is_not_an_enumeration():
    # the exporter's own help text describes --list; describing is not listing
    assert et.enumerating_reason("Bash", _bash("uv run tools/export_trace.py --help")) is None


def test_project_scoped_list_is_native():
    # this is the fix for the original unscoped listing, not a new instance of it
    assert et.enumerating_reason("Bash", _bash("uv run tools/export_trace.py --list")) is None


def test_list_pointed_at_another_project_still_flags():
    cmd = "uv run tools/export_trace.py --list --project -Users-someone-else-thing"
    assert et.enumerating_reason("Bash", _bash(cmd)) == "project listing"


def test_the_projects_own_slug_with_trailing_punctuation_is_native():
    own = "-Users-dev-work-this-project"
    assert et.scan_foreign_slugs(f"exported from {own}.", own) == []
    assert et.scan_foreign_slugs(f"({own})", own) == []


def test_agent_prose_does_not_trigger_enumeration_flags():
    # the description is what the agent wrote about the call, not the call
    payload = _json.dumps({"command": "git status --short",
                           "description": "list every docker container and session"})
    assert et.enumerating_reason("Bash", payload) is None


def test_real_enumerators_are_still_caught_after_narrowing():
    for cmd, expected in [("docker ps -a", "container listing"),
                          ("modal app list", "container listing"),
                          ("gh repo list someorg", "repository listing"),
                          ("cat ~/.ssh/config", "host configuration"),
                          ("ls ~/Developer", "home directory listing"),
                          ("cd /tmp && docker ps", "container listing")]:
        assert et.enumerating_reason("Bash", _bash(cmd, "")) == expected, cmd
    assert et.enumerating_reason("ListAgents", "{}") == "session listing"
