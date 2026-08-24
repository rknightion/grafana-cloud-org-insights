---
id: GCI-0003
title: Record runtime and OCI provenance
status: Done
assignee:
  - '@codex'
created_date: '2026-08-24 12:02'
updated_date: '2026-08-24 12:50'
labels: []
dependencies: []
references:
  - >-
    backlog/docs/doc-0003 -
    Consumer-manifest-provenance-and-immutable-upgrade-contract.md
priority: high
type: enhancement
ordinal: 3000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Historical delivery: make a built deployment candidate attest the immutable product source, deployment revision, overlay digest, and exact runtime projection contract.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Images record immutable product and deployment revisions plus overlay digest
- [x] #2 Runtime projections fail closed on digest mismatch
- [x] #3 A local build cannot silently publish or move a registry tag
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [x] #1 python3 -m pytest tests -q
- [x] #2 tofu fmt -check -recursive terraform; tofu init -backend=false and tofu validate pass for terraform/ and terraform/examples/standalone/
- [x] #3 customer-identifier and shipped-text gates from .github/workflows/ci.yml return clean
<!-- DOD:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Re-verified during the ownership-boundary migration: 1,331 passed, 2 skipped, 6,570 subtests; fresh module and standalone OpenTofu validation succeeded; format, customer-identifier, and shipped-text gates are clean.

Later ownership-boundary candidate validation supersedes the 1,331 count: 1,333 passed, 2 skipped, 6,570 subtests using PATH=/opt/homebrew/opt/python@3.13/libexec/bin:/opt/homebrew/bin:/opt/homebrew/sbin:/usr/local/bin:/System/Cryptexes/App/usr/bin:/usr/bin:/bin:/usr/sbin:/sbin:/var/run/com.apple.security.cryptexd/codex.system/bootstrap/usr/local/bin:/var/run/com.apple.security.cryptexd/codex.system/bootstrap/usr/bin:/var/run/com.apple.security.cryptexd/codex.system/bootstrap/usr/appleinternal/bin:/pkg/env/global/bin:/Library/Apple/usr/bin:/Users/rob/.codex-work/packages/standalone/releases/0.149.0-aarch64-apple-darwin/codex-path:/Users/rob/.codex-work/tmp/arg0/codex-arg03R8UBy:/opt/homebrew/opt/python@3.13/libexec/bin:/Users/rob/.bun/bin:/Users/rob/go/bin:/opt/homebrew/opt/go/libexec/bin:/Applications/iTerm.app/Contents/Resources/utilities:/Users/rob/.orbstack/bin:/Users/rob/.local/bin:/opt/homebrew/opt/fzf/bin:/Users/rob/.orbstack/bin:/Users/rob/.local/bin python3 -m pytest tests -q. Exact containing revision will be appended after commit.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Completed before Backlog adoption. Provenance labels and runtime projection checks were validated in the migration baseline.
<!-- SECTION:FINAL_SUMMARY:END -->
