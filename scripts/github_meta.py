#!/usr/bin/env python3
"""
Enrich data/frameworks.csv with live GitHub metadata, and optionally discover
new candidate packages.

Enrich (default): for every package whose URL is a GitHub repo, fetch stars,
description, last-push date, and archived flag; write data/github_meta.json
(consumed by the website's generate_static_data.py).

Discover (--discover): search GitHub for popular ros2-topic repositories not
already in the dataset and write data/CANDIDATES.md for human review.

Auth: uses the GITHUB_TOKEN env var (or anonymous at 60 req/h — too low for a
full run; CI always passes the token).

Usage:
  GITHUB_TOKEN=$(gh auth token) python scripts/github_meta.py [--discover]
"""
import csv
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FRAMEWORKS_CSV = ROOT / "data" / "frameworks.csv"
META_JSON = ROOT / "data" / "github_meta.json"
CANDIDATES_MD = ROOT / "data" / "CANDIDATES.md"
API = "https://api.github.com"

TOKEN = os.environ.get("GITHUB_TOKEN", "")


def api_get(path):
    req = urllib.request.Request(f"{API}{path}", headers={
        "Accept": "application/vnd.github+json",
        "User-Agent": "awesome-ros-meta",
        **({"Authorization": f"Bearer {TOKEN}"} if TOKEN else {}),
    })
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8")), None
    except urllib.error.HTTPError as e:
        return None, e.code
    except Exception as e:
        return None, str(e)


def repo_slug(url):
    m = re.search(r"github\.com/([\w.-]+)/([\w.-]+)", url or "")
    if not m:
        return None
    return f"{m.group(1)}/{m.group(2).removesuffix('.git')}"


def enrich():
    with open(FRAMEWORKS_CSV, encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))

    meta, misses = {}, []
    for i, r in enumerate(rows):
        name = (r.get("file name") or "").strip()
        slug = repo_slug(r.get("package url"))
        if not slug:
            continue
        data, err = api_get(f"/repos/{urllib.parse.quote(slug)}")
        if err:
            misses.append(f"{name} ({slug}): {err}")
            continue
        meta[name] = {
            "repo": data.get("full_name", slug),
            "stars": data.get("stargazers_count", 0),
            "description": (data.get("description") or "")[:220],
            "pushed_at": (data.get("pushed_at") or "")[:10],
            "archived": bool(data.get("archived")),
        }
        if (i + 1) % 25 == 0:
            print(f"  {i + 1}/{len(rows)} packages…")
        time.sleep(0.15)

    META_JSON.write_text(json.dumps(meta, ensure_ascii=False, indent=1) + "\n")
    print(f"Wrote {META_JSON.name}: {len(meta)} repos enriched, {len(misses)} missed")
    for m in misses[:15]:
        print("  miss:", m)


def discover(limit=40):
    existing = set()
    with open(FRAMEWORKS_CSV, encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            slug = repo_slug(r.get("package url"))
            if slug:
                existing.add(slug.lower())

    candidates = []
    for query in ("topic:ros2", "topic:ros2 topic:robotics"):
        q = urllib.parse.quote(f"{query} stars:>200 archived:false")
        data, err = api_get(f"/search/repositories?q={q}&sort=stars&order=desc&per_page=100")
        if err:
            print("search error:", err)
            continue
        for repo in data.get("items", []):
            slug = repo["full_name"].lower()
            if slug in existing or any(c["full_name"].lower() == slug for c in candidates):
                continue
            candidates.append({
                "full_name": repo["full_name"],
                "html_url": repo["html_url"],
                "stars": repo["stargazers_count"],
                "description": (repo.get("description") or "")[:160],
            })
        time.sleep(1)

    candidates.sort(key=lambda c: -c["stars"])
    candidates = candidates[:limit]
    lines = [
        "# Candidate packages discovered on GitHub",
        "",
        "Popular `ros2`-topic repositories not yet in `frameworks.csv`.",
        "Review and add the relevant ones (this file is informational, not data).",
        "",
        "| Stars | Repository | Description |",
        "|------:|------------|-------------|",
    ]
    for c in candidates:
        lines.append(f"| {c['stars']:,} | [{c['full_name']}]({c['html_url']}) | {c['description']} |")
    CANDIDATES_MD.write_text("\n".join(lines) + "\n")
    print(f"Wrote {CANDIDATES_MD.name}: {len(candidates)} candidates")


if __name__ == "__main__":
    if not TOKEN:
        print("WARNING: no GITHUB_TOKEN — anonymous rate limits will likely fail a full run")
    if "--discover" in sys.argv:
        discover()
    else:
        enrich()
