#!/usr/bin/env python3
"""Guarded GitHub Actions repository agent.

This is intentionally a PR-only implementation helper. It never merges its own
work and it does not receive live-trading authority. The repository handoff and
existing CI/risk controls remain authoritative.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path.cwd().resolve()
MODEL = os.getenv("REPO_AGENT_MODEL", "gpt-5-mini")
MAX_INSTRUCTION = 4000
MAX_CONTEXT_CHARS = 80000
MAX_FILES = 8
MAX_FILE_CHARS = 120000

# The first version is deliberately unable to rewrite its own authority,
# repository workflows, or the authoritative project handoff.
PROTECTED_EXACT = {
    "PROJECT_HANDOFF_CURRENT.md",
}
PROTECTED_PREFIXES = (
    ".github/",
    ".git/",
)

SYSTEM_POLICY = """You are a bounded implementation agent for a PAPER-ONLY automated trading repository.
Read and obey PROJECT_HANDOFF_CURRENT.md as the authoritative continuation contract.
Your job is to make the smallest code/test change necessary for the user's instruction.

Non-negotiable boundaries:
- Never enable live trading or broker order authority.
- Never clear or weaken a risk halt, stop-loss, trailing-stop, daily-loss, drawdown, or accounting-integrity protection unless the user instruction explicitly requests a separately reviewed risk-policy change.
- Never grant ML/AI execution authority.
- Never fabricate trades, execution-ledger rows, accounting history, prices, fills, or test evidence.
- Never bypass the canonical execution ledger/accounting pipeline.
- Prefer regression tests for correctness defects.
- Do not edit GitHub workflows or PROJECT_HANDOFF_CURRENT.md; those are protected by the runner too.
- Produce reviewable changes only. A human and CI decide whether to merge.

Return exactly one JSON object with:
{
  "files": [{"path": "relative/path", "content": "complete replacement file contents"}],
  "pr_title": "short title",
  "pr_body": "what changed, why, tests, and safety boundaries",
  "summary": "one-paragraph summary"
}
Return JSON only, with no markdown fences.
"""


def run(args: list[str], *, check: bool = True, capture: bool = False) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        cwd=ROOT,
        check=check,
        text=True,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.STDOUT if capture else None,
    )


def read_event_instruction() -> str:
    manual = (os.getenv("AGENT_MANUAL_INSTRUCTION") or "").strip()
    event_path = os.getenv("GITHUB_EVENT_PATH")
    event: dict[str, Any] = {}
    if event_path and Path(event_path).exists():
        event = json.loads(Path(event_path).read_text(encoding="utf-8"))

    comment = str((event.get("comment") or {}).get("body") or "").strip()
    if comment.startswith("/agent "):
        instruction = comment[len("/agent ") :].strip()
    else:
        instruction = manual

    if not instruction:
        raise RuntimeError("No agent instruction was supplied.")
    if len(instruction) > MAX_INSTRUCTION:
        raise RuntimeError(f"Instruction exceeds {MAX_INSTRUCTION} characters.")
    return instruction


def safe_text_file(path: Path) -> bool:
    if not path.is_file():
        return False
    rel = path.relative_to(ROOT).as_posix()
    if rel.startswith((".git/", ".venv/", "venv/", "node_modules/", "__pycache__/")):
        return False
    if path.suffix.lower() not in {".py", ".md", ".txt", ".json", ".toml", ".yaml", ".yml"}:
        return False
    try:
        return path.stat().st_size <= 250_000
    except OSError:
        return False


def keywords(instruction: str) -> list[str]:
    words = re.findall(r"[A-Za-z_][A-Za-z0-9_]{2,}", instruction.lower())
    stop = {"the", "and", "for", "with", "that", "this", "from", "into", "please", "fix", "add", "update", "change"}
    return list(dict.fromkeys(w for w in words if w not in stop))[:30]


def build_context(instruction: str) -> str:
    pieces: list[str] = []
    total = 0

    handoff = ROOT / "PROJECT_HANDOFF_CURRENT.md"
    if handoff.exists():
        text = handoff.read_text(encoding="utf-8", errors="replace")
        text = text[:30000]
        pieces.append(f"\n===== PROJECT_HANDOFF_CURRENT.md =====\n{text}")
        total += len(text)

    keys = keywords(instruction)
    ranked: list[tuple[int, str, str]] = []
    for path in ROOT.rglob("*"):
        if not safe_text_file(path):
            continue
        rel = path.relative_to(ROOT).as_posix()
        if rel == "PROJECT_HANDOFF_CURRENT.md":
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        hay = (rel + "\n" + text[:160000]).lower()
        score = sum(hay.count(k) for k in keys)
        if score > 0:
            ranked.append((score, rel, text))

    ranked.sort(key=lambda row: (-row[0], row[1]))
    for _, rel, text in ranked[:12]:
        remaining = MAX_CONTEXT_CHARS - total
        if remaining <= 1000:
            break
        clipped = text[: min(remaining, 15000)]
        pieces.append(f"\n===== {rel} =====\n{clipped}")
        total += len(clipped)

    return "".join(pieces)


def extract_output_text(payload: dict[str, Any]) -> str:
    direct = payload.get("output_text")
    if isinstance(direct, str) and direct.strip():
        return direct.strip()
    chunks: list[str] = []
    for item in payload.get("output") or []:
        if not isinstance(item, dict):
            continue
        for content in item.get("content") or []:
            if not isinstance(content, dict):
                continue
            text = content.get("text")
            if isinstance(text, str):
                chunks.append(text)
    return "".join(chunks).strip()


def call_openai(instruction: str, context: str) -> dict[str, Any]:
    key = os.getenv("OPENAI_API_KEY")
    if not key:
        raise RuntimeError("OPENAI_API_KEY GitHub Actions secret is missing.")

    body = {
        "model": MODEL,
        "input": [
            {"role": "system", "content": SYSTEM_POLICY},
            {
                "role": "user",
                "content": f"Instruction:\n{instruction}\n\nRepository context:\n{context}",
            },
        ],
        "max_output_tokens": 24000,
    }
    request = urllib.request.Request(
        "https://api.openai.com/v1/responses",
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=180) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"OpenAI API HTTP {exc.code}: {detail[:2000]}") from exc

    text = extract_output_text(payload)
    if not text:
        raise RuntimeError("OpenAI response contained no output text.")
    try:
        result = json.loads(text)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Agent returned invalid JSON: {text[:2000]}") from exc
    if not isinstance(result, dict):
        raise RuntimeError("Agent response must be a JSON object.")
    return result


def validate_path(raw: str) -> Path:
    raw = raw.replace("\\", "/").strip()
    if not raw or raw.startswith("/") or ".." in Path(raw).parts:
        raise RuntimeError(f"Unsafe path from agent: {raw!r}")
    if raw in PROTECTED_EXACT or raw.startswith(PROTECTED_PREFIXES):
        raise RuntimeError(f"Agent attempted to modify protected path: {raw}")
    path = (ROOT / raw).resolve()
    if ROOT not in path.parents and path != ROOT:
        raise RuntimeError(f"Path escaped repository: {raw}")
    return path


def apply_files(result: dict[str, Any]) -> list[str]:
    files = result.get("files") or []
    if not isinstance(files, list) or not files:
        raise RuntimeError("Agent proposed no files.")
    if len(files) > MAX_FILES:
        raise RuntimeError(f"Agent proposed {len(files)} files; maximum is {MAX_FILES}.")

    changed: list[str] = []
    for item in files:
        if not isinstance(item, dict):
            raise RuntimeError("Invalid file item in agent response.")
        rel = str(item.get("path") or "")
        content = item.get("content")
        if not isinstance(content, str):
            raise RuntimeError(f"Agent did not provide string content for {rel!r}.")
        if len(content) > MAX_FILE_CHARS:
            raise RuntimeError(f"Agent output for {rel} exceeds size limit.")
        path = validate_path(rel)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        changed.append(path.relative_to(ROOT).as_posix())
    return changed


def validate_changes() -> None:
    run([sys.executable, "-m", "compileall", "-q", "."])
    tests = list(ROOT.glob("test_*.py")) + list((ROOT / "tests").glob("test_*.py")) if (ROOT / "tests").exists() else list(ROOT.glob("test_*.py"))
    if tests:
        proc = subprocess.run(
            ["timeout", "240", sys.executable, "-m", "pytest", "-q"],
            cwd=ROOT,
            text=True,
        )
        if proc.returncode != 0:
            raise RuntimeError(f"pytest failed with exit code {proc.returncode}; PR will not be created.")


def create_pr(result: dict[str, Any], changed: list[str], instruction: str) -> None:
    status = run(["git", "status", "--porcelain"], capture=True).stdout.strip()
    if not status:
        raise RuntimeError("Agent produced no git changes.")

    branch = f"agent/{int(time.time())}"
    title = str(result.get("pr_title") or "Repo agent proposed change")[:120]
    body = str(result.get("pr_body") or result.get("summary") or "Automated repo-agent proposal.")
    body += (
        "\n\n---\nRepo-agent safety: PR-only; no auto-merge. "
        "Human review and repository validation remain required.\n\n"
        f"Instruction: `{instruction[:500]}`\n"
        f"Changed files: {', '.join(changed)}"
    )

    run(["git", "config", "user.name", os.getenv("GIT_USER_NAME", "repo-agent[bot]")])
    run(["git", "config", "user.email", os.getenv("GIT_USER_EMAIL", "repo-agent@users.noreply.github.com")])
    run(["git", "checkout", "-b", branch])
    run(["git", "add", "--", *changed])
    run(["git", "commit", "-m", title])
    run(["git", "push", "origin", branch])

    env = os.environ.copy()
    env["GH_TOKEN"] = os.getenv("GITHUB_TOKEN", "")
    subprocess.run(
        ["gh", "pr", "create", "--base", "main", "--head", branch, "--title", title, "--body", body],
        cwd=ROOT,
        env=env,
        check=True,
        text=True,
    )


def main() -> None:
    instruction = read_event_instruction()
    print(f"Repo agent task: {instruction}")
    context = build_context(instruction)
    print(f"Grounded context size: {len(context)} characters")
    result = call_openai(instruction, context)
    changed = apply_files(result)
    print("Agent proposed:", ", ".join(changed))
    validate_changes()
    create_pr(result, changed, instruction)
    print("Repo agent completed successfully; review the created PR before merging.")


if __name__ == "__main__":
    main()
