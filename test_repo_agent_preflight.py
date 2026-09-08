from pathlib import Path

import pytest

import scripts.repo_agent as repo_agent


def test_repo_agent_protects_authority_files():
    protected = [
        "PROJECT_HANDOFF_CURRENT.md",
        ".github/workflows/repo-agent.yml",
    ]
    for raw in protected:
        try:
            repo_agent.validate_path(raw)
        except RuntimeError:
            pass
        else:
            raise AssertionError(f"protected path was writable: {raw}")


def test_repo_agent_allows_safe_repo_file():
    path = repo_agent.validate_path("REPO_AGENT_TEST.md")
    assert path == (Path.cwd() / "REPO_AGENT_TEST.md").resolve()


def test_repo_agent_uses_bounded_handoff_append_mode(tmp_path, monkeypatch):
    monkeypatch.setattr(repo_agent, "ROOT", tmp_path.resolve())
    handoff = tmp_path / repo_agent.HANDOFF_PATH
    original = b"existing handoff\n"
    handoff.write_bytes(original)

    changed = repo_agent.apply_files(
        {
            "handoff_append": "## New audit\nPASS",
            "pr_title": "Append audit",
            "pr_body": "Append continuity evidence.",
            "summary": "Audit continuity update.",
        },
        "Append a documentation-only continuity update to PROJECT_HANDOFF_CURRENT.md.",
    )

    assert changed == [repo_agent.HANDOFF_PATH]
    updated = handoff.read_bytes()
    assert updated.startswith(original)
    assert updated == original + b"\n## New audit\nPASS\n"


def test_repo_agent_handoff_mode_rejects_file_replacement(tmp_path, monkeypatch):
    monkeypatch.setattr(repo_agent, "ROOT", tmp_path.resolve())
    handoff = tmp_path / repo_agent.HANDOFF_PATH
    handoff.write_text("existing handoff\n", encoding="utf-8")

    with pytest.raises(RuntimeError, match="does not permit code/file edit"):
        repo_agent.apply_files(
            {
                "handoff_append": "## New audit\nPASS",
                "files": [{"path": repo_agent.HANDOFF_PATH, "content": "replacement"}],
            },
            "Append a documentation-only continuity update to PROJECT_HANDOFF_CURRENT.md.",
        )


def test_repo_agent_handoff_mode_requires_heading(tmp_path, monkeypatch):
    monkeypatch.setattr(repo_agent, "ROOT", tmp_path.resolve())
    handoff = tmp_path / repo_agent.HANDOFF_PATH
    handoff.write_text("existing handoff\n", encoding="utf-8")

    with pytest.raises(RuntimeError, match="level-2 Markdown heading"):
        repo_agent.apply_files(
            {"handoff_append": "not a section heading"},
            "Append a documentation-only continuity update to PROJECT_HANDOFF_CURRENT.md.",
        )


def test_repo_agent_handoff_mode_rejects_unexpected_keys(tmp_path, monkeypatch):
    monkeypatch.setattr(repo_agent, "ROOT", tmp_path.resolve())
    handoff = tmp_path / repo_agent.HANDOFF_PATH
    handoff.write_text("existing handoff\n", encoding="utf-8")

    with pytest.raises(RuntimeError, match="unexpected keys"):
        repo_agent.apply_files(
            {"handoff_append": "## New audit\nPASS", "other_file": "unexpected"},
            "Append a documentation-only continuity update to PROJECT_HANDOFF_CURRENT.md.",
        )


def test_repo_agent_handoff_mode_requires_existing_handoff(tmp_path, monkeypatch):
    monkeypatch.setattr(repo_agent, "ROOT", tmp_path.resolve())

    with pytest.raises(RuntimeError, match="missing or empty"):
        repo_agent.apply_files(
            {"handoff_append": "## New audit\nPASS"},
            "Append a documentation-only continuity update to PROJECT_HANDOFF_CURRENT.md.",
        )


def test_repo_agent_exact_patch_updates_existing_file_once(tmp_path, monkeypatch):
    monkeypatch.setattr(repo_agent, "ROOT", tmp_path.resolve())
    target = tmp_path / "large_runtime.py"
    target.write_text("before\nneedle\nafter\n", encoding="utf-8")

    changed = repo_agent.apply_files(
        {"patches": [{"path": "large_runtime.py", "old": "needle", "new": "replacement"}]},
        "Apply a surgical runtime fix.",
    )

    assert changed == ["large_runtime.py"]
    assert target.read_text(encoding="utf-8") == "before\nreplacement\nafter\n"


def test_repo_agent_exact_patch_rejects_zero_or_multiple_matches(tmp_path, monkeypatch):
    monkeypatch.setattr(repo_agent, "ROOT", tmp_path.resolve())
    target = tmp_path / "runtime.py"
    target.write_text("same\nsame\n", encoding="utf-8")

    with pytest.raises(RuntimeError, match="matched 2 times"):
        repo_agent.apply_files(
            {"patches": [{"path": "runtime.py", "old": "same", "new": "different"}]},
            "Apply a surgical runtime fix.",
        )

    with pytest.raises(RuntimeError, match="matched 0 times"):
        repo_agent.apply_files(
            {"patches": [{"path": "runtime.py", "old": "missing", "new": "different"}]},
            "Apply a surgical runtime fix.",
        )


def test_repo_agent_exact_patch_can_add_small_new_file(tmp_path, monkeypatch):
    monkeypatch.setattr(repo_agent, "ROOT", tmp_path.resolve())
    target = tmp_path / "runtime.py"
    target.write_text("old\n", encoding="utf-8")

    changed = repo_agent.apply_files(
        {
            "patches": [{"path": "runtime.py", "old": "old", "new": "new"}],
            "files": [{"path": "helper.py", "content": "VALUE = 1\n"}],
        },
        "Apply a surgical runtime fix and add helper.",
    )

    assert changed == ["runtime.py", "helper.py"]
    assert target.read_text(encoding="utf-8") == "new\n"
    assert (tmp_path / "helper.py").read_text(encoding="utf-8") == "VALUE = 1\n"
