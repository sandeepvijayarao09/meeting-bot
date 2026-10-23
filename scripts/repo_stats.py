#!/usr/bin/env python3
"""Internal reach dashboard: who is looking, who is cloning, who is downloading.

Reads what GitHub already counts. Nothing is instrumented and no third-party
analytics are involved — which matters for a product whose pitch is that it does
not phone home. Run it whenever you want a read; there is nothing to keep running.

    python3 scripts/repo_stats.py            # or: make stats
    python3 scripts/repo_stats.py --json     # same numbers, for a spreadsheet

Traffic (views, clones, referrers, paths) needs push access on the repo and is a
**rolling 14-day window** that GitHub does not let you backfill — so if you care
about the launch period, capture it before it ages out:

    make stats-snapshot        # appends today's numbers to .stats/history.jsonl

Download counts are cumulative for the life of each release asset, not windowed.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

REPO = "sandeepvijayarao09/meeting-bot"
HISTORY = Path(__file__).resolve().parent.parent / ".stats" / "history.jsonl"


def gh(endpoint: str) -> Any:
    """GET a GitHub API endpoint through the `gh` CLI, so it uses your login."""
    try:
        out = subprocess.run(
            ["gh", "api", endpoint],
            capture_output=True,
            text=True,
            check=True,
            timeout=30,
        ).stdout
    except FileNotFoundError:
        sys.exit("gh is not installed — see https://cli.github.com")
    except subprocess.TimeoutExpired:
        sys.exit(f"timed out reading {endpoint}")
    except subprocess.CalledProcessError as e:
        detail = (e.stderr or "").strip().splitlines()
        hint = detail[-1] if detail else f"exit {e.returncode}"
        if "404" in hint or "403" in hint:
            hint += "  (traffic data needs push access on the repo)"
        sys.exit(f"GitHub API failed for {endpoint}: {hint}")
    return json.loads(out)


def collect(repo: str) -> dict[str, Any]:
    """Every number in one dict, so --json and the printout cannot disagree."""
    views = gh(f"repos/{repo}/traffic/views")
    clones = gh(f"repos/{repo}/traffic/clones")
    releases = gh(f"repos/{repo}/releases")
    meta = gh(f"repos/{repo}")

    downloads = [
        {
            "tag": r["tag_name"],
            "published": (r.get("published_at") or "")[:10],
            "assets": [
                {"name": a["name"], "count": a["download_count"], "size": a["size"]}
                for a in r["assets"]
            ],
            "total": sum(a["download_count"] for a in r["assets"]),
        }
        for r in releases
    ]
    return {
        "repo": repo,
        "stars": meta.get("stargazers_count", 0),
        "forks": meta.get("forks_count", 0),
        "watchers": meta.get("subscribers_count", 0),
        # GitHub counts PRs in open_issues_count, so this is "open issues + PRs".
        "open_items": meta.get("open_issues_count", 0),
        "views_14d": {"total": views.get("count", 0), "unique": views.get("uniques", 0)},
        "clones_14d": {"total": clones.get("count", 0), "unique": clones.get("uniques", 0)},
        "referrers": gh(f"repos/{repo}/traffic/popular/referrers")[:5],
        "paths": gh(f"repos/{repo}/traffic/popular/paths")[:5],
        "releases": downloads,
        "downloads_total": sum(r["total"] for r in downloads),
    }


def _bar(value: int, peak: int, width: int = 24) -> str:
    return "█" * max(1, round(value / peak * width)) if value and peak else ""


def render(s: dict[str, Any]) -> str:
    out: list[str] = []
    add = out.append
    add(f"\n  {s['repo']}")
    add(
        f"  {s['stars']} stars · {s['forks']} forks · "
        f"{s['watchers']} watching · {s['open_items']} open issues+PRs\n"
    )

    add("  Last 14 days (GitHub's window; older data is gone)")
    add(f"    page views   {s['views_14d']['total']:>6}   ({s['views_14d']['unique']} unique)")
    add(f"    clones       {s['clones_14d']['total']:>6}   ({s['clones_14d']['unique']} unique)")

    # Views at zero while clones are high usually means automation, not people.
    if s["clones_14d"]["total"] > 0 and s["views_14d"]["total"] == 0:
        add("    note: clones with no page views are usually CI or mirrors, not readers")

    if s["referrers"]:
        add("\n  Where views came from")
        peak = max(r["count"] for r in s["referrers"])
        for r in s["referrers"]:
            add(f"    {r['referrer'][:22]:<22} {r['count']:>5}  {_bar(r['count'], peak)}")

    if s["paths"]:
        add("\n  Most-viewed pages")
        peak = max(p["count"] for p in s["paths"])
        for p in s["paths"]:
            label = p["path"].replace(f"/{s['repo']}", "") or "/"
            add(f"    {label[:22]:<22} {p['count']:>5}  {_bar(p['count'], peak)}")

    add(f"\n  Downloads (cumulative, all time) — {s['downloads_total']} total")
    for r in s["releases"]:
        add(f"    {r['tag']}  ({r['published']})")
        for a in r["assets"]:
            add(f"      {a['name'][:34]:<34} {a['count']:>5}")
        if not r["assets"]:
            add("      (no assets)")
    return "\n".join(out) + "\n"


def snapshot(s: dict[str, Any]) -> Path:
    """Append today's numbers, so the 14-day window stops being lossy."""
    import datetime as dt

    HISTORY.parent.mkdir(parents=True, exist_ok=True)
    row = {"date": dt.date.today().isoformat(), **s}
    with HISTORY.open("a") as f:
        f.write(json.dumps(row) + "\n")
    return HISTORY


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--repo", default=REPO)
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    ap.add_argument(
        "--snapshot",
        action="store_true",
        help="also append to .stats/history.jsonl, beating the 14-day window",
    )
    args = ap.parse_args()

    stats = collect(args.repo)
    print(json.dumps(stats, indent=2) if args.json else render(stats), end="")
    if args.snapshot:
        print(f"  snapshot appended → {snapshot(stats)}\n")


if __name__ == "__main__":
    main()
