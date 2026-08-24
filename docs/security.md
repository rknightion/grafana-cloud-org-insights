# Security

## Read-only by construction, not by convention

The scanning credential is read-only by scope, and the collector's HTTP client **rejects every method except GET**. Some Grafana Cloud read APIs are implemented as Connect-RPC POSTs; those calls live outside the collector HTTP client and are authorised by read scopes.

Nothing is installed on any scanned stack. The collector runs in your AWS account and talks to `grafana.com` and to each stack's own API over HTTPS.

The collector never mutates customer dashboards, alert rules, service accounts or access policies. The only write path in the whole platform is the runtime writer, whose realm is a single nominated stack, and the daily provisioner, which is a separate scheduled task with a separate secret key. See [Credentials and permissions](credentials.md) for every identity and its scopes.

## No defaulted identifiers

`GCINSIGHT_ORG_ID`, `GCINSIGHT_WRITE_STACK`, both signal endpoints, both tenants and the bucket have no defaults, and that is a security property rather than an inconvenience. A defaulted tenant fails silently: the scan authenticates, succeeds, and writes a plausible set of series into somebody else's tenant.

## Cardinality as a privacy control

Identities, metric names, dashboard uids, rule names and service-account names **never** become metric labels.

This is absolute and independent of the deploying organisation's data policy. Identities may be stored in clear in S3 and Loki where that organisation has approved it; a metric label is a different matter, because a series persists for the retention period and cannot be selectively deleted.

Two payloads are treated as radioactive:

- **The raw Alertmanager configuration** returned in `config.original` by `/alertmanager/api/v2/status`, `http_config` included. Where contact points live in Alertmanager rather than in Grafana, that YAML can carry webhook URLs and tokens. Nothing derived from it is stored, logged or emitted beyond bounded counts.
- **`accessToken` on a public dashboard**, which is the live public URL. It is never stored, logged or emitted.

Firing alert instances carry full customer label sets. They are counted, never carried into a label.

## S3 boundaries

The Infinity reader principal is allowed on `views/*` and denied on `scans/*` and `locks/*`. Prove it with IAM policy simulation rather than by inspecting the policy document.

For `ssm:GetParametersByPath`, simulate the bare path ARN as well as a child ARN — the API authorises the path itself, so a child-only simulation can pass while the real call is denied.

Raw scans expire by lifecycle policy. `views/` is permanent; long-term history lives in Mimir, not in the archive.

## Alert rules publish inert

New rules publish **paused and unrouted**. Activation requires naming a receiver, because an unpaused rule with no `notification_settings` inherits the write stack's notification policy — and that stack is a real stack whose policy may route hundreds of rules that are not yours, some to production ticketing.

## Credential handling

Both Grafana Cloud tokens live as JSON keys in one Secrets Manager secret and are injected by the ECS agent. They never appear in Terraform state, in a plan diff, or in the task role's permissions. The module contains the secret; it never manages the values.

Per-stack reader tokens are SSM `SecureString` values below the configured prefix.

Build-time Grafana credentials are separate from runtime credentials and should be short-lived. The dashboard build token is not a runtime secret.

Rotation is an explicit provisioner operation: confirm the new SSM value works before deleting the old token. Token names are organisation-wide unique, so an unnecessary mint can create a timestamped credential and orphan the original.

## Supply chain

Release images are signed with Sigstore keyless signing and carry GitHub build provenance plus SPDX and CycloneDX SBOMs. A deployment resolves a reviewed tag to its immutable manifest digest and pins the digest — a moving tag does not change an existing task definition, and neither does a Git push.

## Fixtures

The repository contains **synthetic fixtures only**. A live compose-input export must be written outside the committed fixture path and anonymised before use.
