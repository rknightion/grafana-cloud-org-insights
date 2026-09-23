---
id: GCI-0033
title: >-
  Bring the README and docs site up to date with dashboard screenshots and a
  plain statement of what the platform can and cannot observe
status: Done
assignee: []
created_date: '2026-09-23 17:50'
updated_date: '2026-09-23 19:52'
labels:
  - docs
dependencies: []
references:
  - README.md
  - docs/dashboards.md
  - docs.toml
  - collector/dashboards/build.py
priority: medium
type: docs
ordinal: 43000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
## Why

The platform now answers a lot of questions that nobody outside the repo can discover without reading code. `README.md` has no screenshots and no plain statement of what a deploying org can observe. A question like "can anyone track overall Grafana feature usage?" should be answerable from the README in a minute: yes for these things, partly for these, and not at all for these.

This is a standalone docs task. It has no dependency on any collector or dashboard build task and changes no source code. Document what is built and rendered at the time the work is done, and never document planned features. When later features land, a refresh is a new docs task.

## What to build

**README.md**
- A "What you can observe" section led by questions, not features. One short table per dashboard (the `DASHBOARDS` registry in `collector/dashboards/build.py` is the authoritative list: Estate, Cost, Usage, Maturity, Risk, Value, Operations, Commercial, AI usage, Dashboard usage, Coverage). Columns: question it answers, source, cadence/window, fidelity (configured / producing / used by people).
- A "What it cannot see" section, stated as plainly. Examples: usage insights records only dashboard opens and query runs, so page visits that run no query are invisible; installed or provisioned is not used. If GCI-0032's matrix doc exists, take its "not visible to any source" list from there. This section stops the platform being over-sold, so keep it honest.
- One screenshot per dashboard, linked to the docs page for that dashboard.
- Check every existing README claim against current code: dashboard count, pillars, tiers and cadences, credential model and deployment steps. Remove or fix anything stale. Retire references to features that were dropped.

**Docs site (`docs/`, built by Zensical from `docs.toml`)**
- `docs/dashboards.md`: a section per dashboard with its screenshot, what each row answers, the data source behind each panel group, and the caveats the dashboard banners carry (source populations, windows, "absent is not zero").
- `docs/index.md` and `docs/getting-started.md`: consistent with the README's "what you can observe".
- Link from each dashboard section to the relevant `docs/traps.md` entries where a panel's reading is non-obvious.

**Screenshots**
- Take them from an authorised development deployment rendering synthetic or anonymised data. **No real customer stack slugs, org names, user names, dashboard names or figures in any image.** Treat that as the same boundary as fixture hygiene in AGENTS.md. If only live data is available, stop and ask rather than blur.
- Store them under `docs/assets/screenshots/` (or wherever Zensical's config expects assets; check `docs.toml`). Use stable file names per dashboard uid so a refresh replaces rather than accumulates.
- Consistent size and theme. Capture full dashboards plus a crop of the most important panel group where the full view is unreadable.
- Scripted capture is preferred if it is cheap: `gcx dashboards snapshot` or the Grafana image renderer against the dev deployment, wired as a `just` recipe (for example `just screenshots`). It must be `[confirm]`-gated or read-only, and it must never run in `just check`. If scripting costs more than it saves, capture manually and say so in the task notes.

## Rules

- Never hand-edit `BUDGET.md`; it is generated.
- No em dashes, en dashes or double hyphens (`just no-em-dashes`).
- `just check-identifiers` must stay clean. It exists to keep deployment identifiers out of the repo, and screenshots count as content for that purpose even though the checker cannot read images. Review them by eye.
- Do not document a panel or view that does not exist in the built dashboards; the coverage gate is the source of truth for what is rendered.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 README has a question-led 'What you can observe' section covering every dashboard in the DASHBOARDS registry, and a 'What it cannot see' section
- [x] #2 Every existing README claim checked against current code; stale claims fixed or removed
- [x] #3 One screenshot per dashboard from synthetic or anonymised data, reviewed by eye for identifiers, stored under stable names
- [x] #4 docs/dashboards.md has a section per dashboard with screenshot, questions answered, source and caveats; index and getting-started consistent with the README
- [x] #5 Only built and rendered features are documented; no source code changed
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [x] #1 just test
- [x] #2 just tf-validate
- [ ] #3 just check-identifiers and just no-em-dashes both return clean
<!-- DOD:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
README and docs cover all 11 registry dashboards with source, cadence, fidelity and caveats. Eleven 1600x1100 light-theme PNGs were rendered from robknight staff dev over 24h after T4, inspected individually for names, emails, logins and customer material, and committed at 7aeb451. User Wave 1 goal explicitly authorised staff-org screenshots. Exact-SHA CI 35911835378 passed pytest, tofu and current-file identifier checks. Isolated exact-SHA worktree passed just no-em-dashes and current-file identifier scan. Local root just check is red from unrelated uncommitted retention tests and the historical identifier gate includes eight pre-wave commits; DoD3 remains unchecked for that literal history check. Zensical is unavailable locally, so a site build is unverified.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Updated README and docs for all 11 built dashboards and committed eleven reviewed dev screenshots. Verified registry links and PNG format, independent Grafana readback, and exact-SHA hosted CI 35911835378. No source code changed.
<!-- SECTION:FINAL_SUMMARY:END -->
