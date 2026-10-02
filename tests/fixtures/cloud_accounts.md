# Synthetic AWS account schema

`cloud_accounts.json` is invented offline, not a live export or estate measurement. It records
only the admitted schema: an object with exactly `data`, whose list entries have nonempty string
IDs. The synthetic ID is transient during parsing and never appears in the projected count.

Admission evidence supplied by the campaign root recorded exact basic-None CSP read/plugin-access
pairs and matching positive reader/Admin count, plus witness cleanup. A separate Admin schema
control established the data-only array and nonempty string IDs. This staff evidence does not
establish universal visibility, customer rollout approval, strict minimality, or backend write
isolation of the credential. Only the fixed AWS accounts GET is approved; other providers are
unknown, not zero. No credential-field exception is permitted on this route.

The public-boundary test augments this fixture with private-content sentinels in arbitrary account
details and verifies that only counts survive source, scan, compose, diagnostic, summary and S3
publication paths. Credential-shaped fields are rejected by the unchanged structural guard.

`bin/make_compose_fixture.py --synthetic-cloud` appends only minimized synthetic CSP count records
to the existing compose fixture, preserving existing data and formatting. Counts use the active
fixture stack index modulo three so the new input is observable in dependency derivation. Existing
Synthetic, IRM, Faro, ML and segment projections are not regenerated or modified.
