# Contributing to Awesome ROS

Thank you for helping grow the ROS research database! This guide explains how to add papers, frameworks, or fix errors.

---

## Adding a Paper

### Option A: Open an Issue (easiest)

1. Go to [Issues → New Paper](../../issues/new?template=new-paper.yml)
2. Paste the DOI — a maintainer will enrich and classify it

### Option B: Submit a Pull Request

1. **Fork** this repository
2. Edit `data/papers.csv` and append a new row at the end
3. **Required fields**: `Paper Title`, `DOI`, `Year`, `ROS Version`, `Contribution_Type`, `Research_Domain`
4. Leave taxonomy columns empty if unsure — the CI or a maintainer will classify it
5. Submit a PR using the [pull request template](.github/pull_request_template.md)

#### Example row (minimal)

```csv
"My Great ROS 2 Paper","10.1109/ICRA.2025.1234567","Author A; Author B","Abstract text here","2025","","","IEEE","Conference","ROS2","APP","","","","UAVs","Planning & Control","Motion Planning & Navigation","",""
```

### Taxonomy Reference

| Field | Allowed Values |
|-------|---------------|
| `ROS Version` | `ROS1`, `ROS2`, `Both` |
| `Contribution_Type` | `APP`, `CORE`, `ECO` |
| `Core_type` | `Middleware`, `Distributed ROS Infrastructure`, `Real-Time & Hardware Integration`, `Security & Safety Mechanisms` |
| `Eco_type` | `Datasets`, `Frameworks`, `Open-Source Packages`, `Benchmarks`, `Simulation Frameworks`, `Surveys & Meta-Analyses` |
| `Research_Domain` | `Perception & World Modeling`, `Planning & Control`, `Human & System Interaction`, `Systems & Infrastructure` |

See [`schema/papers.schema.json`](schema/papers.schema.json) for the full list of allowed values.

---

## Adding a Framework / Package

1. Edit `data/frameworks.csv`
2. Fill in: `file name`, `package url`, `robot platforms`, `robot stack`, `infrastructure`
3. Submit a PR

---

## Fixing an Error

- **Wrong metadata?** Open a [Data Correction issue](../../issues/new?template=data-correction.yml) or submit a PR fixing the row
- **Duplicate entry?** Note the DOI of both rows in your issue/PR

---

## Rules

- **Do not rename or reorder columns** — the CI pipeline validates headers
- **DOIs must be unique** — the CI will reject duplicate DOIs
- **Use UTF-8 encoding** and standard CSV quoting (double-quote fields containing commas)
- **One paper per row** — do not merge entries
- Keep the CSV sorted by Year (descending) when practical

---

## CI Validation

Every PR is automatically checked by GitHub Actions:

- CSV header and format validation
- Required field presence
- Enum value validation (ROS Version, Contribution_Type, etc.)
- Duplicate DOI detection

Fix any CI failures before requesting review.
