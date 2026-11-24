# coop

Turn any GitHub repo into a **public multiplayer project for AI-assisted contributors**.
No servers. Nothing to buy. Works with any AI that can read files and run commands
(Gemini CLI, opencode, Claude Code, Cursor, ...) and, in a copy/paste mode, with plain chatbots.

> Status: v0 skeleton. `guard` and `progress` are tested offline. The GitHub-facing commands
> (`next`, `claim`, `handoff`, `status`, `reap`) and the workflows are written but still need a
> real end-to-end run on a demo repo.

## For a project owner
Tell your AI:

> Set up my repo for public AI collaboration using https://github.com/YOUR-ORG/coop . Read INSTALL.md and follow it.

It scans your repo, asks a few questions, and opens a setup PR (never a direct push).

## For a contributor
Tell your AI:

> Help with this project: https://github.com/OWNER/REPO . Read AGENTS.md and follow it.

## How it works (short)
- **Claim = draft PR** titled `claim: #N` from your fork. First one wins. Every push renews the lease.
- **Lease expires** (default 6h, no activity) -> claim closes, task reopens, next person resumes from the WIP branch.
- **Rate limit or stuck?** `coord handoff "notes"` pushes your state and stops.
- **Guard (CI, no secrets)** rejects PRs that touch protected paths (tests, CI, rules), leave their declared scope, or are too big. Rules come from the BASE branch, so a PR cannot loosen them.
- **Tests are the only truth.** Progress % = tests passing, never "tasks closed".
- **Communication** = issue/PR threads + an auto-generated `STATUS.md` (about 500 tokens) + `DECISIONS.md`. No chat needed.
- **Free**: GitHub Actions + a `coop-data` branch for status and progress charts. Each contributor uses their own AI account.

See [DESIGN.md](DESIGN.md) for the reasoning, risks and open questions.

## Layout
```
coord/coord.py                 CLI (stdlib Python)
.github/workflows/*.yml        reusable workflows (guard, claim, maintain)
templates/                     files the installer copies into a project
INSTALL.md                     the installer prompt (for AIs)
```
