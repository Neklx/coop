#!/usr/bin/env python3
"""coord - coordination CLI for coop (AI-assisted public collaboration on GitHub).

Stdlib only. Needs `git` always, and the `gh` CLI for commands that talk to GitHub
(next, claim, handoff, status, reap).

Offline-testable commands: guard, progress.

Design rules:
  * Never trust the AI. Trust tests, small diffs, declared scope.
  * Boring work is done by this script, not by the AI (saves tokens).
  * Output is short and machine-friendly.
"""
import argparse
import fnmatch
import json
import os
import random
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone

CONFIG_PATH = ".coord/config.json"
DEFAULTS = {
    "protected_paths": [".github/**", ".coord/**", "AGENTS.md", "tests/**"],
    "max_diff_lines": 300,
    "max_files": 12,
    "lease_hours": 6,
    "max_open_claims_per_user": 2,
    "test_command": "",
    "progress_file": "progress.json",
    "task_label": "task",
    "claimed_label": "claimed",
}


# ---------- helpers ----------
def run(cmd, check=True, cwd=None):
    r = subprocess.run(cmd, capture_output=True, text=True, cwd=cwd)
    if check and r.returncode != 0:
        sys.exit(f"command failed: {' '.join(cmd)}\n{r.stderr.strip()}")
    return r.stdout.strip()


def load_config(path=CONFIG_PATH):
    cfg = dict(DEFAULTS)
    if os.path.exists(path):
        with open(path) as f:
            cfg.update(json.load(f))
    return cfg


def gh_json(args):
    out = run(["gh"] + args)
    return json.loads(out) if out else []


def match_any(path, patterns):
    return any(fnmatch.fnmatch(path, p) or fnmatch.fnmatch(path, p.replace("/**", "/*"))
               or (p.endswith("/**") and path.startswith(p[:-2])) for p in patterns)


def parse_scope(body):
    """Tasks declare touched files as a line: 'Files: src/a.py, src/b/**'."""
    m = re.search(r"^\s*Files?:\s*(.+)$", body or "", re.M | re.I)
    return [s.strip() for s in m.group(1).split(",")] if m else []


def parse_blockers(body):
    return [int(n) for n in re.findall(r"blocked[- ]by:?\s*#(\d+)", body or "", re.I)]


# ---------- guard (offline) ----------
def cmd_guard(a):
    """Check a diff against config + claimed scope. Exit 1 with reasons if it fails."""
    cfg = load_config(a.config)
    base_cfg = cfg
    if a.base_config:  # use the BASE branch's config, never the PR's (anti-tampering)
        base_cfg = load_config(a.base_config)
    cfg = base_cfg
    files = run(["git", "diff", "--name-only", f"{a.base}...{a.head}"]).splitlines()
    stat = run(["git", "diff", "--numstat", f"{a.base}...{a.head}"]).splitlines()
    lines = 0
    for s in stat:
        add, dele, _ = s.split("\t", 2)
        lines += (0 if add == "-" else int(add)) + (0 if dele == "-" else int(dele))
    scope = [s for s in (a.scope or "").split(",") if s.strip()]
    problems = []
    if not files:
        problems.append("empty diff")
    if len(files) > cfg["max_files"]:
        problems.append(f"too many files: {len(files)} > {cfg['max_files']}")
    if lines > cfg["max_diff_lines"]:
        problems.append(f"diff too large: {lines} > {cfg['max_diff_lines']} lines")
    for f in files:
        if match_any(f, cfg["protected_paths"]) and not a.allow_protected:
            problems.append(f"protected path touched: {f}")
        elif scope and not match_any(f, scope):
            problems.append(f"outside claimed scope: {f}")
    if problems:
        print("GUARD FAILED")
        for p in problems:
            print(f" - {p}")
        return 1
    print(f"GUARD OK ({len(files)} files, {lines} lines)")
    return 0


# ---------- progress (offline) ----------
def badge_svg(label, pct):
    color = "#e05d44" if pct < 25 else "#dfb317" if pct < 60 else "#97ca00" if pct < 90 else "#4c1"
    txt = f"{pct:.0f}%"
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="120" height="20" role="img" aria-label="{label}: {txt}">'
            f'<rect width="75" height="20" fill="#555"/><rect x="75" width="45" height="20" fill="{color}"/>'
            f'<g fill="#fff" font-family="Verdana,sans-serif" font-size="11" text-anchor="middle">'
            f'<text x="37" y="14">{label}</text><text x="97" y="14">{txt}</text></g></svg>')


def bar_svg(milestones, pct):
    """milestones: list of {name, passed, total}. Simple horizontal bars."""
    h = 40 + 28 * len(milestones)
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="520" height="{h}" font-family="Verdana,sans-serif" font-size="12">',
           f'<text x="10" y="22" font-size="14" font-weight="bold">Overall: {pct:.1f}%</text>']
    y = 40
    for m in milestones:
        p = (m["passed"] / m["total"] * 100) if m["total"] else 0
        out.append(f'<text x="10" y="{y+12}">{m["name"]}</text>')
        out.append(f'<rect x="190" y="{y}" width="250" height="14" fill="#ddd"/>')
        out.append(f'<rect x="190" y="{y}" width="{250*p/100:.0f}" height="14" fill="#4c1"/>')
        out.append(f'<text x="448" y="{y+12}">{m["passed"]}/{m["total"]}</text>')
        y += 28
    out.append("</svg>")
    return "\n".join(out)


def cmd_progress(a):
    """Read a results JSON written by the project's test run and render badge + chart.

    Expected progress.json: {"milestones": [{"name": "...", "passed": 3, "total": 10}, ...]}
    Percentage = total passed / total tests. Closed tasks never count (tests are truth).
    """
    cfg = load_config(a.config)
    path = a.results or cfg["progress_file"]
    if not os.path.exists(path):
        print("no results file yet -> 0%")
        data = {"milestones": []}
    else:
        with open(path) as f:
            data = json.load(f)
    ms = data.get("milestones", [])
    passed = sum(m["passed"] for m in ms)
    total = sum(m["total"] for m in ms)
    pct = (passed / total * 100) if total else 0.0
    os.makedirs(a.out, exist_ok=True)
    with open(os.path.join(a.out, "badge.svg"), "w") as f:
        f.write(badge_svg("progress", pct))
    with open(os.path.join(a.out, "chart.svg"), "w") as f:
        f.write(bar_svg(ms, pct))
    with open(os.path.join(a.out, "progress.json"), "w") as f:
        json.dump({"percent": round(pct, 2), "passed": passed, "total": total,
                   "updated": datetime.now(timezone.utc).isoformat()}, f)
    print(f"progress {pct:.1f}% ({passed}/{total})")
    return 0


# ---------- GitHub commands (need gh; not testable offline) ----------
def repo_slug():
    return run(["gh", "repo", "view", "--json", "nameWithOwner", "-q", ".nameWithOwner"])


def open_claim_prs(slug):
    prs = gh_json(["pr", "list", "-R", slug, "--state", "open", "--limit", "200",
                   "--json", "number,title,author,isDraft,updatedAt,headRefName"])
    return [p for p in prs if re.match(r"^claim:\s*#\d+", p["title"], re.I)]


def claimed_issue_numbers(slug):
    return {int(re.search(r"#(\d+)", p["title"]).group(1)) for p in open_claim_prs(slug)}


def cmd_next(a):
    """Pick a free, unblocked task at random among the top priority tier. Print a compact bundle."""
    cfg = load_config()
    slug = repo_slug()
    issues = gh_json(["issue", "list", "-R", slug, "--label", cfg["task_label"], "--state", "open",
                      "--limit", "300", "--json", "number,title,body,labels"])
    taken = claimed_issue_numbers(slug)
    open_nums = {i["number"] for i in issues}
    free = []
    for i in issues:
        labels = {l["name"] for l in i["labels"]}
        if i["number"] in taken or cfg["claimed_label"] in labels:
            continue
        if any(b in open_nums for b in parse_blockers(i["body"])):
            continue
        prio = next((int(l[1:]) for l in labels if re.fullmatch(r"p\d", l)), 5)
        free.append((prio, i))
    if not free:
        print("NO FREE TASKS. Review someone else's open PR instead (gh pr list), or answer a `question` issue.")
        return 0
    best = min(p for p, _ in free)
    pick = random.choice([i for p, i in free if p == best])
    print(f"TASK #{pick['number']}: {pick['title']}\n")
    print(pick["body"] or "(no description)")
    print(f"\nNext: coord claim {pick['number']}")
    return 0


def cmd_claim(a):
    """Fork-friendly claim: push a branch to your fork and open a DRAFT PR titled 'claim: #N'."""
    cfg = load_config()
    slug = repo_slug()
    me = run(["gh", "api", "user", "-q", ".login"])
    mine = [p for p in open_claim_prs(slug) if p["author"]["login"] == me]
    if len(mine) >= cfg["max_open_claims_per_user"]:
        sys.exit(f"you already hold {len(mine)} claims (max {cfg['max_open_claims_per_user']}). Finish or hand off first.")
    if a.issue in claimed_issue_numbers(slug):
        sys.exit(f"#{a.issue} is already claimed. Run `coord next` again.")
    issue = gh_json(["issue", "view", str(a.issue), "-R", slug, "--json", "title,body"])
    branch = f"task-{a.issue}"
    run(["git", "checkout", "-B", branch])
    marker = f".coord/claims/{a.issue}.json"
    os.makedirs(os.path.dirname(marker), exist_ok=True)
    scope = parse_scope(issue["body"])
    with open(marker, "w") as f:
        json.dump({"issue": a.issue, "scope": scope, "started": datetime.now(timezone.utc).isoformat()}, f)
    run(["git", "add", marker])
    run(["git", "commit", "-m", f"claim: #{a.issue}"])
    run(["git", "push", "-u", "origin", branch, "--force-with-lease"])
    run(["gh", "pr", "create", "-R", slug, "--draft", "--title", f"claim: #{a.issue} {issue['title']}",
         "--body", f"Claims #{a.issue}.\n\n```json\n{json.dumps({'issue': a.issue, 'scope': scope})}\n```"])
    print(f"Claimed #{a.issue}. Scope: {', '.join(scope) or '(none declared)'}. Work on branch {branch}.")
    print("Every push renews your lease. When done: mark the PR ready for review.")
    return 0


def cmd_handoff(a):
    """Write HANDOFF.md, push, and comment, so the next contributor resumes from your branch."""
    body = a.note or sys.stdin.read()
    with open("HANDOFF.md", "w") as f:
        f.write(f"# Handoff\n\n{body}\n")
    run(["git", "add", "HANDOFF.md"])
    run(["git", "commit", "-m", "handoff: wip notes"], check=False)
    run(["git", "push", "origin", "HEAD"])
    print("Handoff pushed. The claim will expire on its own; the next contributor starts from your branch.")
    return 0


def cmd_status(a):
    """Render STATUS.md (kept under ~500 tokens): active claims, free tasks, PRs needing review."""
    cfg = load_config()
    slug = repo_slug()
    claims = open_claim_prs(slug)
    taken = {int(re.search(r"#(\d+)", p["title"]).group(1)) for p in claims}
    issues = gh_json(["issue", "list", "-R", slug, "--label", cfg["task_label"], "--state", "open",
                      "--limit", "300", "--json", "number,title"])
    free = [i for i in issues if i["number"] not in taken]
    lines = ["# STATUS (auto-generated, do not edit)", f"_updated {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC_", "",
             f"Free tasks: {len(free)} | Claimed: {len(claims)}", "", "## Claimed"]
    lines += [f"- {p['title']} (@{p['author']['login']})" for p in claims[:30]] or ["- none"]
    lines += ["", "## Next free (top 10)"] + [f"- #{i['number']} {i['title']}" for i in free[:10]]
    out = "\n".join(lines) + "\n"
    open(a.out, "w").write(out)
    print(f"wrote {a.out}")
    return 0


def cmd_reap(a):
    """Close claims with no activity past the lease, so the task reopens. Run on a schedule."""
    cfg = load_config()
    slug = repo_slug()
    limit = datetime.now(timezone.utc) - timedelta(hours=cfg["lease_hours"])
    n = 0
    for p in open_claim_prs(slug):
        updated = datetime.fromisoformat(p["updatedAt"].replace("Z", "+00:00"))
        if updated < limit:
            run(["gh", "pr", "close", str(p["number"]), "-R", slug, "--comment",
                 f"Lease expired ({cfg['lease_hours']}h without activity). Task is open again. "
                 f"Next contributor: resume from branch `{p['headRefName']}` if useful."])
            n += 1
    print(f"reaped {n} stale claims")
    return 0


def main():
    ap = argparse.ArgumentParser(prog="coord")
    sub = ap.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("guard"); g.set_defaults(fn=cmd_guard)
    g.add_argument("--base", default="origin/main"); g.add_argument("--head", default="HEAD")
    g.add_argument("--scope", default=""); g.add_argument("--config", default=CONFIG_PATH)
    g.add_argument("--base-config", default=None, help="config from the BASE branch (trusted)")
    g.add_argument("--allow-protected", action="store_true")
    p = sub.add_parser("progress"); p.set_defaults(fn=cmd_progress)
    p.add_argument("--config", default=CONFIG_PATH); p.add_argument("--results", default=None)
    p.add_argument("--out", default="coord-out")
    sub.add_parser("next").set_defaults(fn=cmd_next)
    c = sub.add_parser("claim"); c.set_defaults(fn=cmd_claim); c.add_argument("issue", type=int)
    h = sub.add_parser("handoff"); h.set_defaults(fn=cmd_handoff); h.add_argument("note", nargs="?")
    s = sub.add_parser("status"); s.set_defaults(fn=cmd_status); s.add_argument("--out", default="STATUS.md")
    sub.add_parser("reap").set_defaults(fn=cmd_reap)
    a = ap.parse_args()
    sys.exit(a.fn(a))


if __name__ == "__main__":
    main()
