#!/usr/bin/env python3
"""Derive the ROS 2 desktop_full package closure from ros2/variants.

The survey's Core Libraries table was hand-written and does not match reality:
joint_state_publisher is not in desktop_full at all, DDS-Security is marked
optional (contradicting "installed by default"), and launch / ament_cmake /
common_interfaces -- which every user touches -- are missing. This derives the
list mechanically instead, and records which variant layer pulls each package
in, so the Core tab can show ROS 2's actual layering.

Usage: python scripts/build_core_closure.py [--distro rolling]
"""
import argparse, json, re, urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "ros2_desktop_full.json"
VARIANTS = "https://raw.githubusercontent.com/ros2/variants/{branch}/{v}/package.xml"
ROSDISTRO = "https://raw.githubusercontent.com/ros/rosdistro/master/{distro}/distribution.yaml"

# order matters: a package is attributed to the innermost layer that pulls it in
LAYERS = ["ros_core", "ros_base", "desktop", "perception", "simulation", "desktop_full"]


def fetch(url):
    return urllib.request.urlopen(url, timeout=60).read().decode("utf-8")


def variant_deps(v, branch):
    xml = fetch(VARIANTS.format(branch=branch, v=v))
    return re.findall(r"<exec_depend>([^<]+)</exec_depend>", xml)


def package_to_repo(distro):
    """package name -> source repo url, parsed from rosdistro's release blocks."""
    lines = fetch(ROSDISTRO.format(distro=distro)).splitlines()
    out, repo, src, pkgs, in_pkgs = {}, None, None, [], False

    def flush():
        if repo:
            url = src or ""
            url = re.sub(r"\.git$", "", url)
            url = re.sub(r"-release$", "", url)
            for p in (pkgs or [repo]):
                out.setdefault(p, url or None)

    for ln in lines:
        m = re.match(r"^  ([\w\-.]+):\s*$", ln)     # 2-space indent = a repository
        if m:
            flush()
            repo, src, pkgs, in_pkgs = m.group(1), None, [], False
            continue
        if repo is None:
            continue
        if re.match(r"^\s+packages:\s*$", ln):
            in_pkgs = True
            continue
        if in_pkgs:
            pm = re.match(r"^\s+-\s+(\S+)\s*$", ln)
            if pm:
                pkgs.append(pm.group(1))
                continue
            in_pkgs = False
        um = re.match(r"^\s+url:\s*(\S+)\s*$", ln)
        if um and src is None and "github.com" in um.group(1):
            src = um.group(1)
    flush()
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--distro", default="rolling")
    ap.add_argument("--branch", default="rolling")
    args = ap.parse_args()

    raw = {v: variant_deps(v, args.branch) for v in LAYERS}
    # expand: a variant may depend on another variant
    layer_of = {}
    for layer in LAYERS:
        for dep in raw[layer]:
            if dep in raw:          # it's a nested variant, not a package
                continue
            layer_of.setdefault(dep, layer)

    p2r = package_to_repo(args.distro)
    missing = [p for p in layer_of if p not in p2r]
    entries = [{"package": p, "layer": l, "repo": p2r.get(p)}
               for p, l in sorted(layer_of.items())]
    OUT.write_text(json.dumps(
        {"distro": args.distro, "generated_from": "ros2/variants + ros/rosdistro",
         "packages": entries}, indent=1) + "\n")

    from collections import Counter
    print(f"desktop_full closure: {len(entries)} packages")
    for k, v in Counter(e["layer"] for e in entries).most_common():
        print(f"  {k:<12} {v}")
    print(f"without a resolved repo: {len(missing)}")
    print(f"wrote {OUT.name}")


if __name__ == "__main__":
    main()
