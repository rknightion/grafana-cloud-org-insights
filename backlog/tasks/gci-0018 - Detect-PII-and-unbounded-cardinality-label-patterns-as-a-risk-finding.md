---
id: GCI-0018
title: Detect PII and unbounded-cardinality label patterns as a risk finding
status: To Do
assignee: []
created_date: '2026-08-25 13:12'
labels:
  - risk
  - privacy
  - cardinality
dependencies: []
priority: high
type: enhancement
ordinal: 26000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
A signal-label sweep across a real estate found an agent CLI exporting a per-person email address as a METRIC LABEL. That is two defects in one series: personal identity in a metrics store that has no access model for it, and an unbounded-cardinality label that grows with headcount. Neither is visible anywhere in this platform today, and both are exactly the kind of finding the risk surface exists to raise.

The signal-label inventory added for Pillar K already reads label NAMES per stack. Detecting these patterns is therefore nearly free - it is a classification pass over data the collector now holds, not a new read.

## What to detect

**Identity-bearing label NAMES.** Match the label key, never the value, against a versioned pattern set. Candidates, all generic and none derived from any one estate:

```
email, e_mail, mail, user_email, useremail, owner_email
user, username, user_name, user_id, userid, login, account, account_name
person, employee, employee_id, staff_id, upn, principal, subject
full_name, first_name, last_name, given_name, surname, display_name
phone, mobile, msisdn, telephone
ip, ip_address, client_ip, remote_addr, source_ip, x_forwarded_for
session, session_id, cookie, token, api_key, authorization, secret, password
patient, patient_id, mrn, nhs_number, ssn, national_id, dob, date_of_birth
customer_email, customer_name, tenant_email
```

**Unbounded-cardinality label names**, a separate and overlapping class: `uuid`, `guid`, `trace_id`, `span_id`, `request_id`, `correlation_id`, `run_id`, `job_id`, `build_id`, `pod_template_hash`, `container_id`, `task_id`, `pid`, `timestamp`, `epoch`, `url`, `path`, `query`, `full_path`, `endpoint` where unparameterised.

## Absolute rules

- **Match on the label KEY only. Never read, store, log, emit or sample a label VALUE for this purpose.** The whole point is to report that identity-shaped data exists, not to collect it. A finding that quotes an example value has become the leak it was reporting.
- **Never emit a label name as a metric label.** Label names are unbounded. The finding is a per-stack COUNT plus a per-class enum; the offending label names go to a `views/` table and Loki, exactly as metric names already do.
- **Publish a confidence tier.** `email` as a label key is near-certain; `account` and `subject` are frequently legitimate infrastructure labels. Report high-confidence and possible separately and never merge them into one number an operator cannot defend.
- **This is a report, never a remediation.** The platform must not propose dropping a label, and must not touch an Adaptive Metrics rule to do it. Surfacing is the deliverable.
- **The pattern set is a versioned data file with a test**, like the technology registry, and it must contain nothing derived from a specific customer estate. Generic patterns only. A test asserts no pattern is a bare single letter and that the set carries no identifier resembling a real organisation, person or stack.

## Where it lands

Pillar E, risk and hygiene, alongside the existing public-dashboard and access-policy findings. It is the same shape: an inventory the org almost certainly cannot see, surfaced with its measured-stack denominator so an unreadable stack is never a clean zero.

New output:
- `views/risk_label_hygiene` - stack, label name, class, confidence tier, which signal it was seen on.
- Bounded metrics: findings per class and per confidence tier, plus stacks measured as the denominator. No label name and no stack-by-label cross product in Mimir.
- A risk dashboard row leading with the high-confidence identity count and the measured-stack denominator beside it.

## Why it is worth the space

An estate owner cannot grep their own label space at this scale, and the two consequences land on different teams: the privacy exposure is a compliance conversation and the cardinality is a cost conversation. One inventory serves both. It also strengthens the coverage surface indirectly, because a label carrying per-person identity is a strong hint that a service identity is machine-generated rather than a real application.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Detection matches label keys only; no label value is read, stored, logged or emitted
- [ ] #2 Label names never become metric labels; they go to a view and Loki
- [ ] #3 High-confidence and possible findings are reported separately
- [ ] #4 Pattern set is a versioned data file with a test and contains nothing estate-specific
- [ ] #5 Findings carry a measured-stack denominator
- [ ] #6 The platform reports only and never proposes or performs remediation
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 python3 -m pytest tests -q
- [ ] #2 tofu fmt -check -recursive terraform; tofu init -backend=false and tofu validate pass for terraform/ and terraform/examples/standalone/
- [ ] #3 customer-identifier and shipped-text gates from .github/workflows/ci.yml return clean
<!-- DOD:END -->
