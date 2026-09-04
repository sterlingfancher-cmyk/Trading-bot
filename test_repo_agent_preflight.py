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

    with pytest.raises(RuntimeError, match="does not permit file replacement"):
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
