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
ROSDISTRO_SOURCES = ROOT / "data" / "rosdistro_sources.json"
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


HF_RE = re.compile(r"huggingface\.co/(datasets|models|spaces)?/?([\w.\-]+/[\w.\-]+)", re.I)
GH_OWNER_RE = re.compile(r"github\.com/([\w.\-]+)/?(?:[?#].*)?$", re.I)

# Forks we have reviewed and deliberately kept. A warning that fires every
# week on known-good rows is a warning nobody reads, so record the reason.
REVIEWED_FORKS = {
    # upstream is more starred but last shipped 2024-03; the ros2 fork is the
    # maintained ROS 2 port, which is what this dataset is about
    "cartographer",
    # fork chain roots at hku-mars/FAST_LIO, a different package; this row is
    # specifically the ROS 2 port of FAST_LIO_SLAM
    "FAST_LIO_SLAM_ros2",
}

ORG_REPO_PAGES = 3      # cap aggregation at 300 repos per org
FORK_STAR_RATIO = 3     # upstream this many x more popular => probably wrong target


def http_json(url):
    """GET arbitrary JSON. Used for huggingface.co, which is not the GitHub API."""
    req = urllib.request.Request(url, headers={
        "Accept": "application/json",
        "User-Agent": "awesome-ros-meta",
    })
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8")), None
    except urllib.error.HTTPError as e:
        return None, e.code
    except Exception as e:
        return None, str(e)


def classify_url(url):
    """Return (kind, identifier).

    Not every catalogued artefact is a single repository. Mega-projects are
    published as whole GitHub organizations (micro-ROS, ros-industrial,
    space-ros) and datasets/models live on HuggingFace. Treating those as
    repos meant repo_slug() returned None and the row silently got no
    metadata at all -- no stars, no description, no date, forever.
    """
    url = (url or "").strip()
    slug = repo_slug(url)
    if slug:
        return "repo", slug
    m = HF_RE.search(url)
    if m:
        section = (m.group(1) or "models").lower()
        return ("hf-dataset" if section == "datasets" else "hf-model"), m.group(2)
    m = GH_OWNER_RE.search(url)
    if m:
        return "org", m.group(1)
    return "other", url


def fetch_repo(slug):
    data, err = api_get(f"/repos/{urllib.parse.quote(slug)}")
    if err:
        return None, err
    rec = {
        "kind": "repo",
        "repo": data.get("full_name", slug),
        "stars": data.get("stargazers_count", 0),
        "description": (data.get("description") or "")[:220],
        "pushed_at": (data.get("pushed_at") or "")[:10],
        "archived": bool(data.get("archived")),
        "fork": bool(data.get("fork")),
        "topics": (data.get("topics") or [])[:12],
    }
    # `source` is the root of the fork chain, `parent` the immediate one
    src = data.get("source") or data.get("parent")
    if src:
        rec["source"] = {
            "repo": src.get("full_name"),
            "stars": src.get("stargazers_count", 0),
        }
    return rec, None


def fetch_org(owner):
    """Aggregate a whole GitHub org/user: total stars, repo count, flagship repo."""
    info, err = api_get(f"/orgs/{urllib.parse.quote(owner)}")
    scope = "orgs"
    if err:
        info, err = api_get(f"/users/{urllib.parse.quote(owner)}")
        scope = "users"
        if err:
            return None, err

    repos = []
    for page in range(1, ORG_REPO_PAGES + 1):
        batch, err = api_get(
            f"/{scope}/{urllib.parse.quote(owner)}/repos?per_page=100&page={page}")
        if err or not batch:
            break
        repos.extend(r for r in batch if not r.get("private"))
        if len(batch) < 100:
            break
        time.sleep(0.15)

    live = [r for r in repos if not r.get("archived")]
    top = max(repos, key=lambda r: r.get("stargazers_count", 0), default=None)
    return {
        "kind": "org",
        "org": info.get("login", owner),
        "repo": top.get("full_name") if top else None,
        "stars": sum(r.get("stargazers_count", 0) for r in repos),
        "top_stars": top.get("stargazers_count", 0) if top else 0,
        "repos": len(repos),
        "description": (info.get("description")
                        or (top or {}).get("description") or "")[:220],
        "pushed_at": max((r.get("pushed_at") or "" for r in repos), default="")[:10],
        "archived": bool(repos) and not live,
    }, None


def fetch_hf(kind, hf_id):
    section = "datasets" if kind == "hf-dataset" else "models"
    data, err = http_json(
        f"https://huggingface.co/api/{section}/{urllib.parse.quote(hf_id)}")
    if err:
        return None, err
    card = data.get("cardData") or {}
    # Prefer the model/dataset card text; fall back to curated tags. Never the
    # license -- "mit" is not a description.
    desc = " ".join((data.get("description") or "").split())
    if not desc:
        pretty = str(card.get("pretty_name") or "")
        desc = pretty if len(pretty) > 3 else ""
    if not desc:
        desc = ", ".join(str(t) for t in (card.get("tags") or [])[:6])
    if not desc:
        # bare topical tags only; the API prefixes the machine-readable ones
        skip = ("license:", "region:", "format:", "library:", "modality:",
                "size_categories:", "language:", "doi:", "dataset:", "arxiv:")
        desc = ", ".join(t for t in data.get("tags", [])
                         if not t.startswith(skip))[:220]
    return {
        "kind": kind,
        "repo": data.get("id", hf_id),
        "stars": data.get("likes", 0),          # HF "likes" is the star analogue
        "downloads": data.get("downloads", 0),
        "description": str(desc)[:220],
        "pushed_at": (data.get("lastModified") or "")[:10],
        "archived": bool(data.get("disabled")),
    }, None


def enrich():
    with open(FRAMEWORKS_CSV, encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))

    # slugs released through rosdistro are canonical even when they are forks
    try:
        authoritative = set(json.loads(ROSDISTRO_SOURCES.read_text()))
    except Exception:
        authoritative = set()

    meta, misses, suspect = {}, [], []
    for i, r in enumerate(rows):
        name = (r.get("file name") or "").strip()
        url = r.get("package url")
        kind, ident = classify_url(url)

        if kind == "repo":
            rec, err = fetch_repo(ident)
        elif kind == "org":
            rec, err = fetch_org(ident)
        elif kind in ("hf-dataset", "hf-model"):
            rec, err = fetch_hf(kind, ident)
        else:
            misses.append(f"{name}: unrecognised URL {url!r}")
            continue

        if err:
            misses.append(f"{name} ({ident}): {err}")
            continue

        # Flag rows that resolve to something other than the canonical project.
        # Without this a fork or a bloom release repo is indistinguishable from
        # an unpopular project -- which is how slam_toolbox sat on a 4-star
        # release repo while the real one had 2.6k.
        if kind == "repo":
            if rec["repo"].endswith("-release"):
                suspect.append(f"{name}: {rec['repo']} is a bloom release repo, not source")
            src = rec.get("source")
            if (src and name not in REVIEWED_FORKS
                    and ident.lower() not in authoritative
                    and src.get("stars", 0) > max(FORK_STAR_RATIO * rec["stars"], 50)):
                suspect.append(
                    f"{name}: fork {rec['repo']} (*{rec['stars']}) vs upstream "
                    f"{src['repo']} (*{src['stars']})")
            if rec["repo"].lower() != ident.lower():
                suspect.append(f"{name}: {ident} redirects to {rec['repo']}")

        meta[name] = rec
        if (i + 1) % 25 == 0:
            print(f"  {i + 1}/{len(rows)} packages...")
        time.sleep(0.15)

    META_JSON.write_text(json.dumps(meta, ensure_ascii=False, indent=1) + "\n")
    kinds = {}
    for v in meta.values():
        kinds[v["kind"]] = kinds.get(v["kind"], 0) + 1
    print(f"Wrote {META_JSON.name}: {len(meta)} entries "
          f"({', '.join(f'{v} {k}' for k, v in sorted(kinds.items()))}), "
          f"{len(misses)} missed")
    for m in misses[:15]:
        print("  miss:", m)
    if suspect:
        print(f"\n  {len(suspect)} row(s) may point at the wrong target:")
        for sline in suspect:
            print("    !", sline)


SEARCH_QUERIES = ("topic:ros2", "topic:ros2 topic:robotics")
STAR_FLOOR = 200
PER_PAGE = 100
MAX_PAGES = 10  # GitHub caps search results at 1000 per query (10 x 100)


def search_repos(query):
    """Return (repos, total_count) for one search, following pagination.

    The single-page version of this silently lost everything past the first
    100 hits: `topic:ros2` alone reports ~165 matches above the star floor, so
    the tail could never appear in CANDIDATES.md no matter how many candidates
    were absorbed into frameworks.csv -- the exclusion happens after the fetch.
    """
    repos, total = [], None
    q = urllib.parse.quote(f"{query} stars:>{STAR_FLOOR} archived:false")
    for page in range(1, MAX_PAGES + 1):
        data, err = api_get(
            f"/search/repositories?q={q}&sort=stars&order=desc"
            f"&per_page={PER_PAGE}&page={page}"
        )
        if err:
            print(f"  search error ({query!r} page {page}):", err)
            break
        if total is None:
            total = data.get("total_count", 0)
        items = data.get("items", [])
        repos.extend(items)
        if len(items) < PER_PAGE or len(repos) >= total:
            break
        time.sleep(1)  # search API allows 30 req/min authenticated
    total = total or 0
    if total > MAX_PAGES * PER_PAGE:
        print(f"  NOTE: {query!r} has {total} matches; API caps retrieval at "
              f"{MAX_PAGES * PER_PAGE}")
    print(f"  {query!r}: fetched {len(repos)} of {total}")
    return repos, total


def discover(limit=60):
    existing = set()
    with open(FRAMEWORKS_CSV, encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            slug = repo_slug(r.get("package url"))
            if slug:
                existing.add(slug.lower())

    pool, candidates = {}, []
    for query in SEARCH_QUERIES:
        repos, _ = search_repos(query)
        for repo in repos:
            pool.setdefault(repo["full_name"].lower(), repo)
        time.sleep(1)

    for slug, repo in pool.items():
        if slug in existing:
            continue
        candidates.append({
            "full_name": repo["full_name"],
            "html_url": repo["html_url"],
            "stars": repo["stargazers_count"],
            "description": (repo.get("description") or "")[:160],
        })

    candidates.sort(key=lambda c: -c["stars"])
    n_found = len(candidates)
    shown = candidates[:limit]
    lines = [
        "# Candidate packages discovered on GitHub",
        "",
        f"`ros2`-topic repositories with >{STAR_FLOOR} stars, not archived, and "
        "not yet in `frameworks.csv`.",
        "Review and add the relevant ones (this file is informational, not data).",
        "",
        f"Searched {len(pool)} unique repositories; {len(pool) - n_found} are "
        f"already in the dataset, leaving **{n_found}** candidates.",
    ]
    # never let a cap look like an empty backlog
    if n_found > len(shown):
        lines.append(f"Showing the top {len(shown)} by stars — "
                     f"{n_found - len(shown)} more are not listed here.")
    lines += [
        "",
        "| Stars | Repository | Description |",
        "|------:|------------|-------------|",
    ]
    for c in shown:
        lines.append(f"| {c['stars']:,} | [{c['full_name']}]({c['html_url']}) | {c['description']} |")
    CANDIDATES_MD.write_text("\n".join(lines) + "\n")
    print(f"Wrote {CANDIDATES_MD.name}: {len(shown)} shown of {n_found} candidates "
          f"({len(pool)} unique repos searched)")


if __name__ == "__main__":
    if not TOKEN:
        print("WARNING: no GITHUB_TOKEN — anonymous rate limits will likely fail a full run")
    if "--discover" in sys.argv:
        discover()
    else:
        enrich()
