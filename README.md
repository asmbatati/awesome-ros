# Awesome ROS

[![License: CC BY 4.0](https://img.shields.io/badge/License-CC_BY_4.0-lightgrey.svg)](https://creativecommons.org/licenses/by/4.0/)
[![Validate CSVs](https://github.com/asmbatati/awesome-ros/actions/workflows/validate.yml/badge.svg)](https://github.com/asmbatati/awesome-ros/actions/workflows/validate.yml)

A curated, community-maintained dataset of **8,000+ ROS & ROS 2 research papers** and **176 community packages**, powering the [ROS Database](https://ric.psu.edu.sa/riotu/ros/) companion website for the ACM Computing Surveys paper *"ROS 2 in a Nutshell: A Survey"*.

---

## Dataset Overview

| File | Records | Description |
|------|---------|-------------|
| [`data/papers.csv`](data/papers.csv) | 8,033 | Research papers with full metadata, multi-dimensional taxonomy, and 139 boolean keyword labels |
| [`data/frameworks.csv`](data/frameworks.csv) | 176 | Curated ROS 2 packages, tools, and frameworks |

### Papers Schema (key columns)

| Column | Description | Example |
|--------|-------------|---------|
| `Paper Title` | Full paper title | "ROS 2 in a Nutshell: A Survey" |
| `DOI` | Digital Object Identifier | `10.1109/ACCESS.2025.1234` |
| `Year` | Publication year | `2024` |
| `ROS Version` | `ROS1`, `ROS2`, or `Both` | `ROS2` |
| `Contribution_Type` | `APP` (Application), `CORE` (Core ROS), `ECO` (Ecosystem) | `APP` |
| `Core_type` | CORE subtype: Middleware, Distributed ROS Infrastructure, Real-Time & Hardware Integration, Security & Safety Mechanisms | `Middleware` |
| `Eco_type` | ECO subtype: Datasets, Frameworks, Open-Source Packages, Benchmarks, Simulation Frameworks, Surveys & Meta-Analyses | `Frameworks` |
| `App_field` | Application domain (14 fields, e.g. Medical Robotics, Agricultural Robotics) | `Industrial Automation` |
| `App_platform` | Robot platform (11 types, e.g. UAVs, Manipulators, UGVs) | `UAVs` |
| `Research_Domain` | Perception & World Modeling, Planning & Control, Human & System Interaction, Systems & Infrastructure | `Planning & Control` |
| `Research_Subdomain` | 17 subdomains (e.g. SLAM, Navigation, HRI, QoS) | `Motion Planning & Navigation` |
| `Keyword_Labels` | Semicolon-separated fine-grained keywords | `SLAM; LiDAR; navigation` |
| `Label_*` | 139 boolean columns for specific topics (e.g. `Label_SLAM`, `Label_Navigation`, `Label_Security`) | `True` / empty |

> Full schema definitions: [`schema/papers.schema.json`](schema/papers.schema.json) and [`schema/frameworks.schema.json`](schema/frameworks.schema.json).

### Taxonomy

The multi-dimensional taxonomy separates:
- **Contribution Type** (APP / CORE / ECO) — how ROS is used or extended
- **Research Domain** — the robotics functionality addressed (Perception, Planning, Interaction, Systems)
- **Application Context** — industry vertical and robot platform (APP papers only)

See [`docs/taxonomy.md`](https://github.com/asmbatati/ros_survey_revision/blob/main/docs/taxonomy.md) for the full classification framework.

---

## Repository Structure

```
awesome-ros/
├── data/
│   ├── papers.csv          # 8,033 research papers
│   └── frameworks.csv      # 176 curated packages
├── schema/
│   ├── papers.schema.json  # JSON Schema for papers
│   └── frameworks.schema.json
├── .github/
│   ├── workflows/
│   │   └── validate.yml    # CI: CSV lint + schema validation
│   ├── ISSUE_TEMPLATE/
│   │   ├── new-paper.yml
│   │   └── data-correction.yml
│   └── pull_request_template.md
├── CONTRIBUTING.md
├── CITATION.cff
├── LICENSE                 # CC-BY-4.0
└── README.md
```

---

## Contributing

We welcome community contributions! You can:

- **Add a paper** — Submit a DOI via [issue template](../../issues/new?template=new-paper.yml) or PR
- **Add a framework/package** — Edit `data/frameworks.csv` and submit a PR
- **Fix an error** — Report via [data correction issue](../../issues/new?template=data-correction.yml) or PR

See [CONTRIBUTING.md](CONTRIBUTING.md) for detailed instructions.

---

## Quick Start

```python
import pandas as pd

papers = pd.read_csv("data/papers.csv")

# ROS 2 papers only
ros2 = papers[papers["ROS Version"] == "ROS2"]
print(f"ROS 2 papers: {len(ros2)}")

# Filter by domain
slam_papers = papers[papers["Label_SLAM"] == True]
print(f"SLAM papers: {len(slam_papers)}")

# Group by contribution type
print(papers["Contribution_Type"].value_counts())
```

---

## Citation

If you use this dataset in your research, please cite:

```bibtex
@article{albatati2025ros2survey,
  author    = {Al-Batati, Abdulrahman and Koubaa, Anis and Abdelkader, Mohamed and Gabr, Khaled and Aloqaily, Hamad},
  title     = {ROS 2 in a Nutshell: A Survey},
  journal   = {ACM Computing Surveys},
  year      = {2025},
  note      = {Under review. Preprint: \url{https://www.preprints.org/manuscript/202410.1204}}
}
```

---

## License

This dataset is licensed under [Creative Commons Attribution 4.0 International (CC BY 4.0)](LICENSE).

---

## Links

- [Project Page](https://asmbatati.github.io/awesome-ros/) — Paper overview and visualizations
- [ROS Database](https://ric.psu.edu.sa/riotu/ros/) — Interactive database browser
- [Preprint](https://www.preprints.org/manuscript/202410.1204) — Full paper
- [RIOTU Lab](https://ric.psu.edu.sa/riotu/) — Robotics & Internet of Things Lab, Prince Sultan University
