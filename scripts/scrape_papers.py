#!/usr/bin/env python3
"""
Scrape new ROS / ROS 2 papers from OpenAlex and append them to data/papers.csv.

Queries OpenAlex (no API key needed) for works mentioning the Robot Operating
System, filters out false positives (e.g. reactive oxygen species), dedupes
against existing DOIs/titles, heuristically classifies each paper into the
v26 taxonomy (ROS version, contribution type, research domain/subdomain,
application field/platform, Label_* flags), and appends the new rows.

Usage:
    python scripts/scrape_papers.py [--since YYYY-MM-DD] [--dry-run] [--max N]

Stdlib only — safe to run in CI.
"""
import argparse
import csv
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PAPERS_CSV = ROOT / "data" / "papers.csv"
STATS_JSON = ROOT / "data" / "stats.json"
MAILTO = "aalbatati@psu.edu.sa"
OPENALEX = "https://api.openalex.org/works"

SEARCH_QUERIES = [
    '"robot operating system"',
    '"ROS 2" robot',
    '"ROS2" robot',
]

# ---------------------------------------------------------------- taxonomy

SUBDOMAIN_TO_DOMAIN = {
    "State Estimation": "Perception & World Modeling",
    "Spatial Perception & Mapping": "Perception & World Modeling",
    "Semantic Understanding": "Perception & World Modeling",
    "Shared World Models": "Perception & World Modeling",
    "Motion Planning & Navigation": "Planning & Control",
    "Task & Mission Planning": "Planning & Control",
    "Real-Time Control": "Planning & Control",
    "Multi-Robot Coordination": "Planning & Control",
    "Human-Robot Interaction (HRI)": "Human & System Interaction",
    "Teleoperation": "Human & System Interaction",
    "Shared Autonomy": "Human & System Interaction",
    "Human-System Interfaces": "Human & System Interaction",
    "Software Architecture & Middleware": "Systems & Infrastructure",
    "Communication & QoS": "Systems & Infrastructure",
    "Cloud & Edge Robotics": "Systems & Infrastructure",
    "Hardware Integration": "Systems & Infrastructure",
    "Supervisory, Safety & Reliability Systems": "Systems & Infrastructure",
}

# Keyword patterns per subdomain; first match group wins on tie via order.
SUBDOMAIN_PATTERNS = {
    "Spatial Perception & Mapping": [
        r"\bslam\b", "simultaneous localization", "lidar odometry",
        "visual odometry", "visual-inertial", r"\bvio\b", "3d mapping",
        "occupancy grid", "point cloud registration",
    ],
    "State Estimation": [
        "state estimation", "kalman", r"\bekf\b", r"\bukf\b", "sensor fusion",
        "pose estimation", "localization",
    ],
    "Semantic Understanding": [
        "semantic segmentation", "object detection", "object recognition",
        "scene understanding", "semantic mapping", "instance segmentation",
        "vision-language",
    ],
    "Motion Planning & Navigation": [
        "navigation", "path planning", "motion planning", "obstacle avoidance",
        r"\bnav2\b", "path following", "local planner", "trajectory planning",
        "autonomous exploration",
    ],
    "Task & Mission Planning": [
        "task planning", "mission planning", "behavior tree", "task allocation",
        "task scheduling", "mission management", "high-level planning",
    ],
    "Real-Time Control": [
        "model predictive control", r"\bmpc\b", "trajectory tracking",
        "motion control", "whole-body control", "impedance control",
        "force control", "controller design", r"\bpid\b",
    ],
    "Multi-Robot Coordination": [
        "multi-robot", "multi robot", "swarm", "fleet", "multi-agent",
        "formation control", "cooperative robot",
    ],
    "Human-Robot Interaction (HRI)": [
        "human-robot interaction", "human robot interaction", r"\bhri\b",
        "social robot", "human-robot collaboration", "collaborative robot",
        r"\bcobot\b", "gesture recognition",
    ],
    "Teleoperation": [
        "teleoperation", "telemanipulation", "haptic", "remote operation",
        "remote control of",
    ],
    "Shared Autonomy": [
        "shared autonomy", "shared control", "mixed initiative",
    ],
    "Human-System Interfaces": [
        "user interface", "graphical interface", r"\bgui\b", "web interface",
        "supervisory interface", "mixed reality interface",
        "augmented reality interface", "virtual reality interface",
    ],
    "Software Architecture & Middleware": [
        "middleware", "software architecture", "system architecture",
        r"\bdds\b", "executor", "component-based", "software framework",
        "design pattern", "code generation",
    ],
    "Communication & QoS": [
        "quality of service", r"\bqos\b", "communication performance",
        "network latency", "bandwidth", "message passing", "data distribution",
        "wireless communication", r"\b5g\b",
    ],
    "Cloud & Edge Robotics": [
        "cloud robotics", "edge computing", "cloud computing", "offloading",
        "fog robotics", "edge-cloud",
    ],
    "Hardware Integration": [
        "embedded", "microcontroller", r"\bfpga\b", "micro-ros", r"\bsoc\b",
        "hardware acceleration", "hardware-in-the-loop", "sensor driver",
        "hardware interface", r"\bgpu\b",
    ],
    "Supervisory, Safety & Reliability Systems": [
        "safety", "security", "fault detection", "fault tolerance",
        "formal verification", "runtime verification", "anomaly detection",
        "intrusion", "vulnerability", "reliability", "monitoring system",
        "cybersecurity",
    ],
}

ROS2_SIGNALS = [
    r"\bros\s*2\b", r"\bros2\b", "humble", "jazzy", "foxy", "galactic",
    "iron irwini", "micro-ros", "ros 2 humble", "kilted",
]
ROS1_SIGNALS = [
    r"\bros\s*1\b", r"\bros1\b", "noetic", "melodic", "kinetic", "indigo",
    r"\broscpp\b", r"\brospy\b",
]

APP_FIELD_PATTERNS = {
    "Agricultural Robotics": ["agricultur", "farming", "crop", "harvest", "orchard", "weed"],
    "Medical Robotics": ["surgical", "surgery", "medical robot", "rehabilitation", "healthcare", "clinical"],
    "Logistics & Warehouse Robotics": ["warehouse", "logistics", "order picking", "intralogistics"],
    "Industrial Automation": ["industrial", "manufactur", "factory", "assembly line", "production line", "machine tending"],
    "Marine Robotics": ["underwater", "marine", r"\bauv\b", r"\busv\b", "subsea", "maritime"],
    "Space Robotics": ["spacecraft", "lunar", "planetary", "orbital", "space robot", "mars rover"],
    "Construction & Infrastructure Robotics": ["construction", "infrastructure inspection", "bridge inspection", "tunnel"],
    "Educational Robotics": ["education", "teaching", "student", "curriculum", "classroom"],
    "Public Safety & Emergency Response Robotics": ["search and rescue", "disaster", "emergency response", "firefight"],
    "Transportation & Mobility Robotics": ["autonomous driving", "autonomous vehicle", "self-driving", "traffic", "urban mobility"],
    "Military & Defense Robotics": ["military", "defense", "battlefield"],
    "Environmental Robotics": ["environmental monitoring", "wildlife", "forest", "conservation", "pollution"],
    "Service Robotics": ["service robot", "domestic robot", "household", "hospitality", "cleaning robot"],
    "Human-Robot Interaction": ["human-robot interaction", "social robot"],
}

APP_PLATFORM_PATTERNS = {
    "UAVs": [r"\buavs?\b", "drone", "aerial robot", "aerial vehicle", "quadrotor", "quadcopter", "multirotor"],
    "Self-Driving Cars": ["autonomous driving", "self-driving", "autonomous vehicle", "autonomous car"],
    "Manipulators": ["manipulator", "robotic arm", "robot arm", "pick-and-place", "grasping"],
    "Humanoid Robots": ["humanoid"],
    "Quadrupedal Robots": ["quadruped", "legged robot"],
    "Underwater Robots": ["underwater", r"\bauv\b", r"\brov\b"],
    "Medical Robots": ["surgical robot", "medical robot"],
    "Soft Robots": ["soft robot"],
    "Multi-Robot Systems": ["multi-robot", "swarm", "robot fleet"],
    "Service Robots": ["service robot", "domestic robot"],
    "UGVs": [r"\bugvs?\b", "ground vehicle", "ground robot", "mobile robot", "wheeled robot", r"\bamr\b"],
}

# Extra match patterns for label columns whose name alone is not enough.
LABEL_SYNONYMS = {
    "Label_MRS": ["multi-robot system", "multi robot system"],
    "Label_RL": ["reinforcement learning"],
    "Label_VR": ["virtual reality"],
    "Label_AR": ["augmented reality"],
    "Label_LLM": ["large language model", r"\bllms?\b"],
    "Label_Agentic AI": ["agentic ai", "ai agent"],
    "Label_SLAM": [r"\bslam\b", "simultaneous localization"],
    "Label_HRI": ["human-robot interaction"],
    "Label_Sim2Real": ["sim-to-real", "sim2real"],
    "Label_Real-time": ["real-time", "real time"],
    "Label_ros_control": ["ros_control"],
    "Label_ros2_control": ["ros2_control"],
    "Label_ci/cd": ["continuous integration", "ci/cd"],
}

NEGATIVE_SIGNALS = [
    "reactive oxygen species", "oxidative stress", "antioxidant",
    "rosuvastatin", "apoptosis", "mitochondri",
]
ROBOTICS_CONTEXT = [
    "robot", "robotic", "slam", "gazebo", "moveit", "nav2", "autonomous",
    "teleoperation", "manipulator", "uav", "ugv", "drone",
]


def http_get_json(url, retries=3):
    req = urllib.request.Request(url, headers={"User-Agent": f"awesome-ros-scraper (mailto:{MAILTO})"})
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            if attempt == retries - 1:
                raise
            time.sleep(2 * (attempt + 1))


def reconstruct_abstract(inverted_index):
    if not inverted_index:
        return ""
    positions = {}
    for word, idxs in inverted_index.items():
        for i in idxs:
            positions[i] = word
    return " ".join(positions[i] for i in sorted(positions))[:5000]


def matches_any(text, patterns):
    for p in patterns:
        if p.startswith("\\b") or "\\b" in p:
            if re.search(p, text):
                return True
        elif p in text:
            return True
    return False


def count_matches(text, patterns):
    n = 0
    for p in patterns:
        if "\\b" in p:
            n += len(re.findall(p, text))
        else:
            n += text.count(p)
    return n


def is_relevant(text):
    if matches_any(text, NEGATIVE_SIGNALS):
        return False
    if "robot operating system" in text:
        return True
    has_ros = re.search(r"\bros\s*2?\b", text) is not None
    return has_ros and matches_any(text, ROBOTICS_CONTEXT)


def classify_ros_version(text):
    r2 = matches_any(text, ROS2_SIGNALS)
    r1 = matches_any(text, ROS1_SIGNALS)
    if r2 and r1:
        return "Both"
    if r2:
        return "ROS2"
    if r1:
        return "ROS1"
    return ""


def classify_subdomain(text):
    best, best_score = "", 0
    for sub, patterns in SUBDOMAIN_PATTERNS.items():
        score = count_matches(text, patterns)
        if score > best_score:
            best, best_score = sub, score
    return best


def classify_field(text, patterns_map):
    best, best_score = "", 0
    for label, patterns in patterns_map.items():
        score = count_matches(text, patterns)
        if score > best_score:
            best, best_score = label, score
    return best


def classify_contribution(text, title, subdomain):
    t = title.lower()
    if matches_any(t, ["survey", "review", "systematic mapping", "meta-analysis"]):
        return "ECO", "", "Surveys & Meta-Analyses"
    if matches_any(text, ["benchmark suite", "benchmarking framework", "we benchmark"]) or "benchmark" in t:
        return "ECO", "", "Benchmarks"
    if "dataset" in t:
        return "ECO", "", "Datasets"
    if matches_any(t, ["simulation framework", "simulator for"]):
        return "ECO", "", "Simulation Frameworks"
    if matches_any(t, ["framework for", "toolbox", "toolkit", "open-source package", "open source package"]):
        return "ECO", "", "Frameworks"
    core_map = {
        "Software Architecture & Middleware": "Middleware",
        "Communication & QoS": "Middleware",
        "Cloud & Edge Robotics": "Distributed ROS Infrastructure",
        "Hardware Integration": "Real-Time & Hardware Integration",
        "Supervisory, Safety & Reliability Systems": "Security & Safety Mechanisms",
    }
    # CORE only when the paper is *about* ROS itself rather than an application
    if subdomain in core_map and matches_any(text, [
        "of ros", "in ros", "ros 2 middleware", "ros middleware", "dds",
        "ros 2 executor", "sros", "performance of ros",
    ]):
        return "CORE", core_map[subdomain], ""
    return "APP", "", ""


def classify_labels(text, label_cols):
    matched = []
    for col in label_cols:
        name = col[len("Label_"):].lower()
        patterns = LABEL_SYNONYMS.get(col, [name if len(name) > 3 else rf"\b{re.escape(name)}\b"])
        if matches_any(text, patterns):
            matched.append(col)
    return matched


MANUSCRIPT_TYPE_MAP = {
    "article": "Article",
    "review": "Article",
    "book-chapter": "Book Chapter",
    "preprint": "Preprint",
    "proceedings-article": "Conference",
}


def manuscript_type(work):
    t = work.get("type", "")
    loc = work.get("primary_location") or {}
    src = loc.get("source") or {}
    if src.get("type") == "repository" or t == "preprint":
        return "Preprint"
    if t == "book-chapter":
        return "Book Chapter"
    name = (src.get("display_name") or "").lower()
    if "proceedings" in name or "conference" in name or "workshop" in name or "symposium" in name:
        return "Conference"
    return MANUSCRIPT_TYPE_MAP.get(t, "Article")


def scrape(since, max_results):
    works, seen_ids = [], set()
    for q in SEARCH_QUERIES:
        cursor = "*"
        while cursor:
            params = {
                "search": q,
                "filter": f"from_publication_date:{since},has_doi:true",
                "per-page": "200",
                "cursor": cursor,
                "mailto": MAILTO,
            }
            url = f"{OPENALEX}?{urllib.parse.urlencode(params)}"
            data = http_get_json(url)
            for w in data.get("results", []):
                wid = w.get("id")
                if wid not in seen_ids:
                    seen_ids.add(wid)
                    works.append(w)
            cursor = data.get("meta", {}).get("next_cursor")
            print(f"  query={q!r}: {len(works)} works collected so far")
            if max_results and len(works) >= max_results:
                cursor = None
            time.sleep(0.3)
    return works


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", default="2025-12-01")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--max", type=int, default=0, help="cap collected works per run (0 = no cap)")
    args = ap.parse_args()

    with open(PAPERS_CSV, encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        headers = reader.fieldnames
        existing_dois, existing_titles = set(), set()
        n_existing = 0
        for row in reader:
            n_existing += 1
            doi = (row.get("DOI") or "").strip().lower()
            if doi:
                existing_dois.add(doi)
            title = re.sub(r"[^a-z0-9]+", "", (row.get("Paper Title") or "").lower())
            if title:
                existing_titles.add(title)
    label_cols = [h for h in headers if h.startswith("Label_")]

    print(f"Existing: {n_existing} papers. Scraping OpenAlex since {args.since}...")
    works = scrape(args.since, args.max)
    print(f"Collected {len(works)} unique works. Filtering & classifying...")

    new_rows, skipped_dup, skipped_irrelevant = [], 0, 0
    for w in works:
        doi = (w.get("doi") or "").replace("https://doi.org/", "").strip()
        title = " ".join((w.get("title") or w.get("display_name") or "").split())
        if not doi or not title:
            continue
        norm_title = re.sub(r"[^a-z0-9]+", "", title.lower())
        if doi.lower() in existing_dois or norm_title in existing_titles:
            skipped_dup += 1
            continue
        if w.get("is_retracted") or re.match(
            r"^(retraction|retracted|correction|corrigendum|erratum|withdrawn)\b", title, re.I
        ):
            skipped_irrelevant += 1
            continue
        abstract = reconstruct_abstract(w.get("abstract_inverted_index"))
        text = f"{title} {abstract}".lower()
        if not is_relevant(text):
            skipped_irrelevant += 1
            continue

        ros_version = classify_ros_version(text)
        subdomain = classify_subdomain(text)
        domain = SUBDOMAIN_TO_DOMAIN.get(subdomain, "")
        contribution, core_type, eco_type = classify_contribution(text, title, subdomain)
        app_field = classify_field(text, APP_FIELD_PATTERNS) if contribution == "APP" else ""
        app_platform = classify_field(text, APP_PLATFORM_PATTERNS) if contribution == "APP" else ""
        matched_labels = classify_labels(text, label_cols)

        loc = w.get("primary_location") or {}
        src = loc.get("source") or {}
        authors = "; ".join(
            (a.get("author") or {}).get("display_name", "")
            for a in (w.get("authorships") or [])
        ).strip("; ")

        row = {h: "" for h in headers}
        row.update({
            "Paper Title": title,
            "DOI": doi,
            "Authors": authors,
            "Abstract": abstract,
            "Year": str(w.get("publication_year") or ""),
            "Date of Publication": w.get("publication_date") or "",
            "Venue of Publication": src.get("display_name") or "",
            "Publisher": src.get("host_organization_name") or "",
            "Type of Manuscript": manuscript_type(w),
            "ROS Version": ros_version,
            "Contribution_Type": contribution,
            "Core_type": core_type,
            "Eco_type": eco_type,
            "App_field": app_field,
            "App_platform": app_platform,
            "Research_Domain": domain,
            "Research_Subdomain": subdomain,
            "Keyword_Labels": "; ".join(c[len("Label_"):] for c in matched_labels),
            "URL": f"https://doi.org/{doi}",
        })
        for c in matched_labels:
            row[c] = "TRUE"
        new_rows.append(row)
        existing_dois.add(doi.lower())
        existing_titles.add(norm_title)

    print(f"\nNew: {len(new_rows)} | duplicates skipped: {skipped_dup} | irrelevant skipped: {skipped_irrelevant}")
    if args.dry_run or not new_rows:
        for r in new_rows[:20]:
            print(f"  [{r['Year']}] [{r['ROS Version'] or '?'}] [{r['Contribution_Type']}] {r['Paper Title'][:80]}")
        return

    with open(PAPERS_CSV, "a", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        writer.writerows(new_rows)

    # refresh stats.json
    with open(PAPERS_CSV, encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    years = sorted(int(r["Year"]) for r in rows if (r.get("Year") or "").strip().isdigit())
    ros2 = sum(1 for r in rows if (r.get("ROS Version") or "").strip() in ("ROS2", "Both"))
    ros1 = sum(1 for r in rows if (r.get("ROS Version") or "").strip() == "ROS1")
    STATS_JSON.write_text(json.dumps({
        "total_papers": len(rows),
        "ros2_papers": ros2,
        "ros1_papers": ros1,
        "years_covered": f"{years[0]}-{years[-1]}",
    }, indent=2) + "\n")

    print(f"Appended {len(new_rows)} papers. Total now {len(rows)}.")


if __name__ == "__main__":
    main()
