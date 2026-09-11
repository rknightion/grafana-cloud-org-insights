---
id: GCI-0026
title: >-
  Validate the Loki retention surface against an authorised development
  deployment
status: Parked
assignee: []
created_date: '2026-09-11 14:15'
updated_date: '2026-09-11 15:25'
labels:
  - retention
  - validation
dependencies: []
priority: medium
type: task
ordinal: 35000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
GCI-0022 shipped the Loki retention surface with every acceptance criterion met against source and CI, and explicitly did not claim a populated live render or a live collector run. This task closes that gap.

Authorised by the operator on 2026-09-11 for wave 2.

## What to observe

- One read-only collector execution against an authorised development deployment. Read-only: `collector/httpclient.py` refuses any method other than GET, and that property is what makes this safe to run.
- The three retention view artifacts retained on the bucket: `risk_retention_change_requests`, `risk_retention_stream` and `risk_retention_policy_gaps`.
- One fixed-label Loki event confirmed present, with stream labels exactly `tier`, `pillar=E` and `event=change`, and the change author and message in the line body rather than in a label.
- A populated render of the five Operations retention elements: measured denominator, modal global retention, candidate divergence count, divergent-stack table and trend.

## Constraints

- **A limited run cannot publish.** `--limit` and `--stack` compose estate rollups over a subset, so `scan.py` refuses every S3, Mimir and Loki write unless `--dry-run` is also set. Run the full estate or accept that nothing is written.
- **Confirm the identity-bearing detail landed where it was designed to land and nowhere else.** Author and message belong in the Loki line body and the S3 view. Neither may appear in a metric label.
- **An empty change-request list is not a finding of no override.** It means no self-serve request exists. Record it as that.
- **A failed plugin or dataplane read is unreadable, never zero.** Check that an unreadable stack is excluded from the policy comparison and still visible in the measured denominator.
- **This repository is public.** No stack slug, account identifier, log-group name or other deployment-specific detail enters any file, the gitignored `codex/` directory included - the customer-identifier gate scans the working tree, not the index.
- Report what was observed. A render that shows no rows because the estate genuinely has no divergence is a valid result and must not be reported as a defect.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 One read-only full-estate collector execution completes against an authorised development deployment
- [ ] #2 All three retention view artifacts are observed retained on the bucket
- [ ] #3 One Loki change event is observed with stream labels exactly tier, pillar=E and event=change, and identity detail only in the line body
- [ ] #4 The five Operations retention elements are observed rendering against populated data
- [ ] #5 No identity-bearing content is found in any metric label, and no deployment-specific detail reaches any file
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [x] #1 just test
- [x] #2 just tf-validate
- [x] #3 just check-identifiers and just no-em-dashes both return clean
<!-- DOD:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Wave 2 attended validation did not run because the operator did not supply the development-deployment identity. No deployment or bucket was inferred, and no collector, S3, Loki, metric-label or dashboard observation was made.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Parked without a live collector run. The development deployment was not supplied, so the three retention artifacts, fixed-label Loki change event, identity placement and five populated Operations elements remain unproved.
<!-- SECTION:FINAL_SUMMARY:END -->
