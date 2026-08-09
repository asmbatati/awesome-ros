#!/usr/bin/env python3
"""
Ingest officially-released ROS 2 packages from ros/rosdistro into frameworks.csv.

Why this exists: discovery via `topic:ros2 stars:>200` finds popular repos, not
important ones. rclcpp, rclpy, moveit2 and image_pipeline do not carry the
`ros2` GitHub topic at all, so no star threshold could ever surface them.
rosdistro is the authoritative registry of released ROS 2 packages -- being in
it means someone wrote a package.xml and passed the build farm, which is a
quality signal independent of popularity.

Categories are assigned heuristically from repo name/description/topics using
the vocabulary already present in frameworks.csv. They are best-effort and
meant to be reviewed, exactly like the paper scraper's taxonomy guesses.

Usage:
  GITHUB_TOKEN=$(gh auth token) python scripts/rosdistro_ingest.py \
      [--distro jazzy] [--dry-run] [--min-stars N] [--limit N]
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

sys.path.insert(0, str(Path(__file__).resolve().parent))
import github_meta as gm

ROOT = Path(__file__).resolve().parent.parent
FRAMEWORKS_CSV = ROOT / "data" / "frameworks.csv"
ROSDISTRO_SOURCES = ROOT / "data" / "rosdistro_sources.json"
ROSDISTRO = "https://raw.githubusercontent.com/ros/rosdistro/master/{distro}/distribution.yaml"

# ---------------------------------------------------------------- vocabulary
GROUND = "Ground Robots (UGVs legged wheeled)"
AERIAL = "Aerial Robots (UAVs)"
AUTOV = "Autonomous Vehicles (cars, trucks, delivery robots)"
INDUS = "Industrial Robots"
EDU = "Robots for Education & Research"
UNDER = "Underwater Robots (UUVs)"
SPACE = "Aerospace & Space Robotics"
HEALTH = "Healthcare & Assistive Robotics"

SLAM = "Localization and Mapping (SLAM, LIO, VIO, LIVO)"
ML = "Machine Learning (RL, Adaptive, etc)"
TASK = "Task-Level Planning & Reasoning"
NAV = "Motion Planning & Navigation (global, local, path following)"
DETECT = "Object Detection & Semantic Understanding"
HRI = "HRI - Human–Robot Interfaces (speech, vision-language, wearable sensors)"
CTRL = "Classical Control (PID, MPC, etc.)"
MPLAN = "Motion Planning (global)"
STATE = "State Estimation"
SENSE = "Sensing & Raw Data Processing (camera, lidar, sonar, radar)"

SIMS = "Simulators & Playgrounds"
INTEROP = "Interfacing & Interoperability (bridges, wrappers, APIs)"
DRIVERS = "Hardware Drivers & Interfaces"
EMBED = "Embedded Systems & Accelerators"
RT = "Real-Time Execution & Scheduling"
BENCH = "Analyzing, Testing, Benchmarking & Profiling"
VIZ = "Visualization, Monitoring & Data Tools"
SEC = "Security, Safety & Verification"
MIDDLE = "Middleware & Communication"
MULTI = "Multi-Robot Systems"
SYNTH = "Synthetic Data & Dataset Generation"
BUILD = "Build & Development Tools"
CLOUD = "Cloud/Edge Deployment & Orchestration"

# (regex, value) — every match contributes; order within a facet is preserved
PLATFORM_RULES = [
    (r"\b(uav|drone|quadcopter|quadrotor|multirotor|px4|ardupilot|mavlink|mavros)\b", AERIAL),
    (r"\b(legged|quadruped|humanoid|biped|wheeled|differential.?drive|turtlebot|amr|agv|mobile robot|husky|jackal)\b", GROUND),
    (r"\b(autonomous driving|self.?driving|autoware|carla|automotive|vehicle|road|lane)\b", AUTOV),
    (r"\b(manipulator|robot arm|gripper|industrial|cobot|ur5|ur10|universal.?robot|kuka|franka|panda|abb|fanuc|moveit)\b", INDUS),
    (r"\b(underwater|auv|uuv|marine|subsea|bluerov|maritime)\b", UNDER),
    (r"\b(space|satellite|spacecraft|lunar|martian|aerospace|orbital)\b", SPACE),
    (r"\b(medical|surgical|assistive|healthcare|rehabilitation|prosthe)\b", HEALTH),
    (r"\b(tutorial|example|demo|teaching|course|learning material|educational)\b", EDU),
]
STACK_RULES = [
    (r"\b(slam|localization|localisation|mapping|odometry|lio|vio|livo|amcl|loop closure|cartographer)\b", SLAM),
    (r"\b(reinforcement learning|deep learning|neural|imitation learning|\brl\b|policy learning|transformer)\b", ML),
    (r"\b(behavio(u)?r tree|task planning|symbolic|pddl|mission|state machine|reasoning)\b", TASK),
    (r"\b(navigation|nav2|path following|waypoint|costmap|global planner|local planner)\b", NAV),
    (r"\b(detection|segmentation|recognition|yolo|classifier|semantic|apriltag|aruco|fiducial|tracking)\b", DETECT),
    (r"\b(speech|voice|teleoperat|teleop|gesture|haptic|joystick|gamepad|vision.?language|\bllm\b|human.?robot)\b", HRI),
    (r"\b(controller|control|\bpid\b|\bmpc\b|servo|actuation|admittance|impedance)\b", CTRL),
    (r"\b(motion planning|trajectory|\bompl\b|kinematics|inverse kinematics|grasp)\b", MPLAN),
    (r"\b(kalman|estimation|state estimat|sensor fusion|\bimu\b|filter|ekf|ukf)\b", STATE),
    (r"\b(camera|lidar|laser|radar|sonar|depth|point.?cloud|pointcloud|sensor|encoder|gnss|\bgps\b)\b", SENSE),
]
INFRA_RULES = [
    (r"\b(simulat|gazebo|ignition|isaac sim|mujoco|webots|unity|coppelia|pybullet)\b", SIMS),
    (r"\b(bridge|wrapper|binding|\bapi\b|interface|interoperab|ros1_bridge|adapter)\b", INTEROP),
    (r"\b(driver|hardware|firmware|serial|\bcan\b|ethercat|modbus|usb|gpio|\bi2c\b|\bspi\b)\b", DRIVERS),
    (r"\b(jetson|embedded|fpga|\bgpu\b|cuda|tensorrt|microcontroller|micro.?ros|arduino|raspberry)\b", EMBED),
    (r"\b(real.?time|realtime|scheduling|deterministic|latency|executor|preempt)\b", RT),
    (r"\b(test|testing|benchmark|profil|diagnostic|analysis|coverage|\bci\b|lint)\b", BENCH),
    (r"\b(visuali[sz]|rviz|rqt|plot|dashboard|monitor|\bgui\b|foxglove|display|marker)\b", VIZ),
    (r"\b(security|safety|verification|certif|formal|fault|watchdog)\b", SEC),
    (r"\b(\bdds\b|middleware|communication|message|transport|\bqos\b|\brmw\b|zenoh|serializ)\b", MIDDLE),
    (r"\b(multi.?robot|swarm|fleet|multi.?agent)\b", MULTI),
    (r"\b(dataset|synthetic data|data generation|rosbag|\bbag\b|recording|mcap)\b", SYNTH),
    (r"\b(build|colcon|ament|cmake|packaging|tooling|template|generator|\bcli\b|command.?line)\b", BUILD),
    (r"\b(cloud|edge|docker|kubernetes|deployment|orchestrat|container)\b", CLOUD),
]


def classify(text, rules, limit=3):
    """Return up to `limit` vocabulary values whose pattern matches `text`."""
    hits = []
    for pattern, value in rules:
        if value in hits:
            continue
        if re.search(pattern, text, re.I):
            hits.append(value)
        if len(hits) >= limit:
            break
    return "; ".join(hits)


def rosdistro_repos(distro):
    """Yield (name, github_slug) for every source repo released in `distro`."""
    url = ROSDISTRO.format(distro=distro)
    txt = urllib.request.urlopen(url, timeout=60).read().decode("utf-8")
    out = {}
    # distribution.yaml is deep YAML; the source urls are what we need and a
    # targeted regex avoids taking a PyYAML dependency into CI.
    for m in re.finditer(r"url:\s*(https://github\.com/[^\s]+?)(?:\.git)?\s*$", txt, re.M):
        u = m.group(1)
        sm = re.search(r"github\.com/([\w.\-]+)/([\w.\-]+?)/?$", u)
        if not sm:
            continue
        slug = f"{sm.group(1)}/{sm.group(2)}"
        if slug.endswith("-release") or slug.endswith("-gbp"):
            continue          # bloom packaging mirrors, not source
        out[slug.lower()] = slug
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--distro", default="jazzy")
    ap.add_argument("--min-stars", type=int, default=0)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    with open(FRAMEWORKS_CSV, encoding="utf-8", newline="") as f:
        header, *rows = list(csv.reader(f))
    have_slugs, have_names = set(), set()
    for r in rows:
        s = gm.repo_slug(r[1])
        if s:
            have_slugs.add(s.lower())
        have_names.add(r[0].lower())

    found = rosdistro_repos(args.distro)
    # Record provenance. A repo listed in rosdistro is the canonical target by
    # definition -- it is what the build farm builds -- even when it is a fork
    # (ros2/urdf, clalancette/sophus). Without this the fork guardrail fires on
    # hundreds of legitimate rows and stops being worth reading.
    if not args.dry_run:
        ROSDISTRO_SOURCES.write_text(
            json.dumps(sorted(found.keys()), indent=0) + "\n")
        print(f"wrote {ROSDISTRO_SOURCES.name}: {len(found)} authoritative slugs")
    todo = {k: v for k, v in found.items() if k not in have_slugs}
    print(f"rosdistro {args.distro}: {len(found)} source repos, "
          f"{len(found) - len(todo)} already present, {len(todo)} to fetch")
    if args.limit:
        todo = dict(list(todo.items())[:args.limit])

    added, skipped_stars, gone, uncategorised = [], 0, 0, 0
    for i, (_, slug) in enumerate(sorted(todo.items(), key=lambda kv: kv[1].lower())):
        rec, err = gm.fetch_repo(slug)
        if err:
            gone += 1
            time.sleep(0.1)
            continue
        if rec["stars"] < args.min_stars:
            skipped_stars += 1
            time.sleep(0.1)
            continue

        # resolve redirects/renames to the canonical name before dedup
        canonical = rec["repo"]
        if canonical.lower() in have_slugs:
            time.sleep(0.1)
            continue
        name = canonical.split("/")[1]
        if name.lower() in have_names:
            name = f"{name}_{canonical.split('/')[0]}"
            if name.lower() in have_names:
                time.sleep(0.1)
                continue

        # name + description + GitHub topics; many released packages have a
        # terse or empty description, and topics carry real signal
        blob = " ".join([canonical.replace("_", " ").replace("-", " "),
                         rec.get("description") or "",
                         " ".join(rec.get("topics") or []).replace("-", " ")])
        plat = classify(blob, PLATFORM_RULES, limit=2)
        stack = classify(blob, STACK_RULES, limit=3)
        infra = classify(blob, INFRA_RULES, limit=3)
        if not (plat or stack or infra):
            uncategorised += 1

        added.append([name, f"https://github.com/{canonical}", plat, stack, infra])
        have_slugs.add(canonical.lower())
        have_names.add(name.lower())
        if (i + 1) % 100 == 0:
            print(f"  {i + 1}/{len(todo)} fetched, {len(added)} queued...")
        time.sleep(0.12)

    print(f"\nnew rows        {len(added)}")
    print(f"unreachable     {gone}")
    print(f"below min-stars {skipped_stars}")
    print(f"no category hit {uncategorised} ({uncategorised * 100 // max(len(added), 1)}%)")

    if args.dry_run:
        print("\n--dry-run: not writing")
        for r in added[:15]:
            print("  ", r[0], "|", r[2] or "-", "|", r[3] or "-", "|", r[4] or "-")
        return

    for row in added:
        pos = next((i for i, r in enumerate(rows) if r[0].lower() > row[0].lower()), len(rows))
        rows.insert(pos, row)
    with open(FRAMEWORKS_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\r\n")   # file is CRLF throughout
        w.writerow(header)
        w.writerows(rows)
    print(f"\nframeworks.csv now {len(rows)} rows")


if __name__ == "__main__":
    main()
