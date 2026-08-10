#!/usr/bin/env python3
"""Link each ecosystem package to the paper that *introduced* it.

The loose approach -- any \\cite{} in a sentence mentioning the tool -- produced
27 links for Nav2, almost all of which merely *use* Nav2. That is a different
relation and it drowns the real one. Only high-precision channels are kept:

  curated  the survey's own targeted citation for a named tool (bib key -> DOI)
  repo     papers.csv 'Github Repo' == the package's repo
  title    the package name appears in the paper title (contribution papers
           are overwhelmingly named "X: a ..." after the thing they introduce)
"""
import csv, json, os, re, unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PAPER_DIR = Path(os.environ.get("PAPER_DIR", ROOT.parent / "ROS_2_Proof"))
BIB = PAPER_DIR / "References" / "references.bib"
PAPERS = ROOT / "data" / "papers.csv"
FRAMEWORKS = ROOT / "data" / "frameworks.csv"
OUT = ROOT / "data" / "paper_links.json"

# Extracted from the survey's own prose, where it cites the canonical paper for
# a named tool. These are the cases where no string match could work --
# "The Marathon 2" contains no occurrence of "Nav2".
# Keys are the canonical frameworks.csv package names, so a link built from
# this file lands on a real entry. Aliases ("Nav2") would search for nothing.
CURATED = {
    "Navigation2": ["2020_Marathon2_macenskia", "2023_DesksROS_macenski",
                    "2025_OpenSourceCostAware_macenski"],
    "moveit2": ["2023_ExtendingMotion_malvidofresnillo"],
    "micro-ROS": ["2023_MicroROS_belsare"],
    "BehaviorTree.CPP": ["2022_BehaviorTrees_ribeaud"],
    "PlanSys2": ["2021_PlanSys2Planning_martin"],
    "SkiROS2": ["2023_SkiROS2SkillBased_mayr"],
    "Space_ROS": ["2023_SpaceROS_probe"],
    "UUV_simulator": ["2016_UUVSimulator_manhaes"],
    "HuNavSim": ["2023_HuNavSimROS_perez-higueras"],
    "LunarSim": ["2023_LunarSimLunar_pieczynski"],
    "MVSim": ["2023_MultiVehicleSimulator_blanco-claraco"],
    "F1TenthGym": ["2020_F1TENTHOpensource_okelly", "2025_AdvancingAutonomous_charles"],
    "LGSVL_Simulator": ["2020_LGSVLSimulator_rong"],
    "MAES": ["2023_MAESROS_andreasen"],
    "CARLA": ["2017_CARLAOpen_dosovitskiy"],
    "VECTOR": ["2025_VECTORVelocityEnhanced_nacar"],
}

# A repo named after the paper that introduced a *different* package is a
# coincidence, not a contribution link.
TITLE_BLOCKLIST = {"The_Marathon_2"}

GENERIC = {"control","navigation","perception","simulation","robot","vision","planning",
           "launch","urdf","demo","test","core","base","tools","teleop","image","camera",
           "driver","bridge","interface","message","system","server","client","common",
           "genesis","seed","dolly","angles","joy","marker","vector"}


def norm(t):
    return re.sub(r"[^a-z0-9]+","",unicodedata.normalize("NFKD",t or "").lower())


def parse_bib():
    txt = BIB.read_text(encoding="utf-8", errors="replace")
    out={}
    for m in re.finditer(r"@\w+\{([^,]+),(.*?)\n\}", txt, re.S):
        key, body = m.group(1).strip(), m.group(2)
        def f(n):
            fm=re.search(rf"\n\s*{n}\s*=\s*[{{\"]?(.+?)[}}\"]?,?\s*\n", body, re.S|re.I)
            return re.sub(r"[{}]","",fm.group(1)).strip() if fm else ""
        out[key]={"title":f("title"),"doi":f("doi").lower()}
    return out


def main():
    if not BIB.exists():
        print(f"bibliography not found at {BIB}; set PAPER_DIR")
        return
    bib=parse_bib()
    papers=list(csv.DictReader(open(PAPERS,encoding="utf-8")))
    by_doi,by_title={},{}
    for p in papers:
        d=(p.get("DOI") or "").strip().lower()
        if d: by_doi.setdefault(d,p)
        by_title.setdefault(norm(p.get("Paper Title")),p)
    fw=list(csv.DictReader(open(FRAMEWORKS,newline="",encoding="utf-8")))

    links={}
    def add(pkg,paper,via):
        rec={"doi":(paper.get("DOI") or "").strip(),
             "title":(paper.get("Paper Title") or "").strip(),
             "year":(paper.get("Year") or "").strip(),"via":via}
        cur=links.setdefault(pkg,[])
        if not any(c["title"]==rec["title"] for c in cur): cur.append(rec)

    # 1. curated
    for pkg,keys in CURATED.items():
        for k in keys:
            e=bib.get(k)
            if not e: print(f"  ! bib key missing: {k}"); continue
            p=by_doi.get(e["doi"]) or by_title.get(norm(e["title"]))
            if p: add(pkg,p,"curated")
            else: print(f"  ! not in papers.csv: {e['title'][:60]}")

    # 2. shared repo
    def slug(u):
        m=re.search(r"github\.com/([\w.\-]+)/([\w.\-]+?)(?:\.git)?/?$",(u or "").strip(),re.I)
        return f"{m.group(1)}/{m.group(2)}".lower() if m else None
    fslug={slug(r["package url"]):r["file name"] for r in fw if slug(r["package url"])}
    for p in papers:
        s=slug(p.get("Github Repo"))
        if s and s in fslug: add(fslug[s],p,"repo")

    # 3. package name in title
    for r in fw:
        n=r["file name"]
        if len(n)<5 or n.lower() in GENERIC or n in TITLE_BLOCKLIST: continue
        # underscores/hyphens are often spaces or absent in prose titles
        variants={n, n.replace("_"," "), n.replace("_",""), n.replace("-"," ")}
        pat=re.compile("|".join(rf"(?<![\w-]){re.escape(v)}(?![\w-])" for v in variants),re.I)
        for p in papers:
            t=p.get("Paper Title") or ""
            m=pat.search(t)
            if not m: continue
            # Contribution papers are named after the thing they introduce:
            # "CARET: Chain-Aware...", "HuNavSim: A ROS 2...". A mention later
            # in the title is a paper that *uses* the package, not one that
            # introduces it -- a different relation, and far more common.
            head=t.split(":")[0]
            if m.start()==0 or (m.start()<len(head) and len(head)<60):
                add(n,p,"title")

    OUT.write_text(json.dumps(links,ensure_ascii=False,indent=1)+"\n")
    ch={}
    for v in links.values():
        for x in v: ch[x["via"]]=ch.get(x["via"],0)+1
    print(f"\n{len(links)} packages -> {sum(len(v) for v in links.values())} papers  {ch}")
    print("\nspot check:")
    for k in ["Nav2","MoveIt 2","HuNavSim","CARET","micro-ROS","slam_toolbox","VECTOR"]:
        for r in links.get(k,[])[:2]:
            print(f"  {k:<14} [{r['via']:<7}] {r['year']} {r['title'][:62]}")

main()
