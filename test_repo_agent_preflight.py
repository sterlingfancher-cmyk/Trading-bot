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


def test_repo_agent_allows_explicit_handoff_only_append(tmp_path, monkeypatch):
    monkeypatch.setattr(repo_agent, "ROOT", tmp_path.resolve())
    handoff = tmp_path / repo_agent.HANDOFF_PATH
    handoff.write_text("existing handoff\n", encoding="utf-8")

    changed = repo_agent.apply_files(
        {
            "files": [
                {
                    "path": repo_agent.HANDOFF_PATH,
                    "content": "existing handoff\n\n## New audit\nPASS\n",
                }
            ]
        },
        "Append a documentation-only continuity update to PROJECT_HANDOFF_CURRENT.md.",
    )

    assert changed == [repo_agent.HANDOFF_PATH]
    assert handoff.read_text(encoding="utf-8") == "existing handoff\n\n## New audit\nPASS\n"


def test_repo_agent_rejects_handoff_rewrite_even_when_requested(tmp_path, monkeypatch):
    monkeypatch.setattr(repo_agent, "ROOT", tmp_path.resolve())
    handoff = tmp_path / repo_agent.HANDOFF_PATH
    handoff.write_text("existing handoff\n", encoding="utf-8")

    with pytest.raises(RuntimeError, match="append only"):
        repo_agent.apply_files(
            {"files": [{"path": repo_agent.HANDOFF_PATH, "content": "rewritten handoff\n"}]},
            "Append a documentation-only continuity update to PROJECT_HANDOFF_CURRENT.md.",
        )


def test_repo_agent_rejects_handoff_mixed_with_other_files(tmp_path, monkeypatch):
    monkeypatch.setattr(repo_agent, "ROOT", tmp_path.resolve())
    handoff = tmp_path / repo_agent.HANDOFF_PATH
    handoff.write_text("existing handoff\n", encoding="utf-8")

    with pytest.raises(RuntimeError, match="handoff-only"):
        repo_agent.apply_files(
            {
                "files": [
                    {"path": repo_agent.HANDOFF_PATH, "content": "existing handoff\nnew audit\n"},
                    {"path": "OTHER.md", "content": "unexpected\n"},
                ]
            },
            "Append a documentation-only continuity update to PROJECT_HANDOFF_CURRENT.md.",
        )
