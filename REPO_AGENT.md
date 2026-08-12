# Guarded Repository Agent

This repository includes a lightweight GitHub Actions–based implementation agent for reviewable background coding tasks.

## Safety model

The agent is intentionally bounded:

- creates a branch and pull request only
- never merges its own PR
- reads `PROJECT_HANDOFF_CURRENT.md` as the authoritative continuation contract
- runs Python compilation and pytest before creating a PR
- blocks edits to `.github/**` and `PROJECT_HANDOFF_CURRENT.md`
- does not have live-trading authority
- must not clear or weaken risk/accounting protections or promote ML execution authority unless a separately reviewed task explicitly authorizes a policy change
- existing human review, CI, Railway validation, accounting integrity, canonical-ledger, and risk controls remain authoritative

## Required secret

Repository owner must add one GitHub Actions secret:

`OPENAI_API_KEY`

GitHub path:

`Settings → Secrets and variables → Actions → New repository secret`

Do not paste the key into an issue, source file, commit, pull request, or chat transcript.

## How to run

### Manual run

1. Open the repository on GitHub.
2. Open **Actions**.
3. Select **repo-agent**.
4. Choose **Run workflow**.
5. Enter a concise implementation instruction.
6. The agent reads the handoff plus relevant repository context, makes a bounded change, runs validation, pushes an `agent/...` branch, and opens a PR.

### Owner issue-comment run

Only comments authored by the repository owner and beginning with `/agent ` trigger the workflow.

Example:

`/agent Add a regression test for the accounting defect described in the current handoff. Do not change trading behavior or risk limits.`

Ordinary issue comments do not trigger the agent.

## Review policy

Every agent PR must be reviewed before merge. Confirm:

1. The diff matches the task.
2. No live-trading authority was introduced.
3. No risk halt or accounting protection was weakened.
4. Tests/validation passed.
5. Existing repository CI is green where applicable.
6. Railway validation is performed when the change affects runtime behavior.

If any of those conditions fail, do not merge the PR.

## Current implementation

The agent uses OpenAI's Responses API. The model defaults to `gpt-5-mini` and can be changed later through `REPO_AGENT_MODEL` if there is a reviewed reason to do so.
