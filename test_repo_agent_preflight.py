from pathlib import Path

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
