# Review backlog: auto-classified papers from the OpenAlex scrape

The June 2026 scrape appended **533 papers** (rows 8,034–8,566 of `papers.csv`)
with heuristic classifications from `scripts/scrape_papers.py`. Coverage of the
auto-assigned fields:

| Field | Missing | Share |
|-------|--------:|------:|
| ROS Version | 165 | 31% |
| Research Domain / Subdomain | 101 | 19% |
| Keyword labels | 35 | 7% |
| Abstract (not available in OpenAlex) | 34 | 6% |
| Contribution type | 0 | 0% |

## Suggested review passes

1. **ROS version blanks** — papers that mention only generic "ROS"; many recent
   ones are likely ROS 2 but need a human (or LLM-assisted) check against the
   title/abstract before assigning.
2. **Domain blanks** — no subdomain keyword matched; assign manually from the
   taxonomy in `schema/papers.schema.json`.
3. **Spot-check assigned labels** — heuristics are keyword-based; verify a
   sample (~50 papers) for precision before treating the cohort as curated.

The cohort is identifiable by ISO-format `Date of Publication` (YYYY-MM-DD)
in rows appended after 8,033. Future scrapes arrive as PRs via `scrape.yml`,
so this is a one-time backlog for the initial cohort.
