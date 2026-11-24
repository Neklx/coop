# DESIGN

## Principle
Never trust the AI. Trust tests, small blast radius, declared scope, and independent review.

## Decisions so far
| Topic | Decision | Why |
|---|---|---|
| Platform | GitHub only for v1, core logic portable | Only proven model for thousands of strangers; free for public repos |
| Claim | Draft PR from a fork, titled `claim: #N`, earliest wins | Strangers cannot push branches; also acts as the heartbeat |
| Lease | Expires after N hours without a push (default 6) | Handles vanished users and rate limits with no polling |
| Handoff | `HANDOFF.md` on the WIP branch | Next contributor resumes instead of restarting |
| Guard | Diff size, file count, protected paths, claimed scope; config read from BASE branch | A PR cannot loosen its own rules |
| Secrets | CI on forks has none; claim arbiter never checks out PR code | Avoids the classic `pull_request_target` hole |
| Updates | Projects call reusable workflows pinned `@v1` | Fix once, everyone upgrades; no instant hijack |
| Status/progress | Written to orphan branch `coop-data` | Never touches main or branch protection |
| Progress metric | Tests passing, per milestone | Closed tasks can be 80% while nothing works |
| Tokens | Self-contained tasks, per-module context files, scripts do the boring parts, trimmed CI logs, retry cap of 3 | Exploring the repo is the biggest token cost |
| Communication | Issue/PR threads + `STATUS.md` + `DECISIONS.md` | Async and cheap for AIs; humans can use Discussions |
| Other AIs | `AGENTS.md` + pointer files; copy/paste mode for chat-only AIs (not built yet) | Works with free tools |

## Known risks
- **Review and CI capacity is the bottleneck**, not contributor count. Free runners have concurrency limits. Mitigations: cap open claims per user, cheap checks first, merge queue.
- **Prompt injection** via issue/PR text against reviewer AIs. Rule: text is data. Needs real-world testing.
- **Bad plan = 1000 people building the wrong thing.** Installer must have the owner approve the plan before issues are created.
- **Weak tests = fake progress.** Installer must refuse to invent a percentage.
- **Task supply**: if the graph is deep, contributors idle. Installer must generate wide graphs; extra people become reviewers.
- **Cron granularity**: GitHub scheduled workflows can be delayed; lease checks are approximate. Fine for hours-scale leases.

## Not built yet
- Copy/paste mode for chat-only AIs (`coord next` -> text bundle, `coord apply`)
- Reputation / trust tiers (needs merged-and-never-reverted history)
- Auto-revert bot when main breaks (merge queue + nightly full run)
- Discovery index page for projects tagged `ai-coop`
- `coord review` (listed in `next` output but not implemented)
- Real end-to-end test on a demo repo
