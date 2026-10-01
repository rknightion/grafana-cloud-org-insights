# Security

## Read-only by construction, not by convention

The scanning credential is read-only by scope, and deployments run only against organisations that
have explicitly consented to the declared read capabilities. Read-only does not mean metadata-only:
`logs:read` is a full Loki read scope and can return log content. It is retained deliberately because
the label inventory requires it and no narrower Grafana Cloud scope reaches label names and values.

The collector's HTTP client **rejects every method except GET**. Its org-reader Loki sources call fixed
label and effective-limit routes, not ruler or log query endpoints. The org reader still declares
`rules:read` and `alerts:read`, but no executable source calls the ruler or Alertmanager routes.
Those unused grants retain their breadth and must be included in deployment consent. Stack-local
Grafana rule and receiver inventory uses the separate stack reader. Usage insights separately runs
bounded aggregate LogQL reads through each stack's datasource proxy. These restraints are reviewed
implementation properties, not credential properties. Fleet list APIs use read-only Connect-RPC
POSTs outside that client. The bounded daily label-risk
source alone may POST native Pyroscope `LabelNames` and `LabelValues` on inventory `hpInstanceUrl`,
using `hpInstanceId`; no other native Pyroscope path or method is granted. These read exceptions do
not weaken the general GET-only client.

`traces:read` and `profiles:read` are not credential-enforced metadata boundaries either: isolated
stack-realm probes returned trace and profile content. The collector keeps to its approved label/tag
routes. Consent must consider credential breadth, not just the current call sites.

Source HTTP deadlines fence caller waits through DNS and complete reads. They do not terminate
surviving daemon transports or bound response memory. The fixed pool accounts for survivors, which
can retain credentials and transient response bytes until they finish or the process exits.
Loki/Mimir publishers are outside this read-source fence.

Nothing is installed on any scanned stack. The collector runs in your AWS account and talks to `grafana.com` and to each stack's own API over HTTPS.

The collector never mutates customer dashboards, alert rules, service accounts or access policies.
It publishes S3 objects and uses a runtime writer scoped to one nominated stack for Mimir and Loki.
The opt-in provisioner is a separate write task with a separate secret key; dashboard and alert
publication tools are also explicit build-time write paths. The provisioner runs daily by module
default, with deployment overrides possible; see the [operator timetable](https://github.com/rknightion/grafana-cloud-org-insights/blob/main/RUNBOOK.md#scheduled-jobs). See [Credentials and permissions](credentials.md) for every identity and its scopes.

## No defaulted identifiers

`GCINSIGHT_ORG_ID`, `GCINSIGHT_WRITE_STACK`, both signal endpoints, both tenants and the bucket have no defaults, and that is a security property rather than an inconvenience. A defaulted tenant fails silently: the scan authenticates, succeeds, and writes a plausible set of series into somebody else's tenant.

## Cardinality is not privacy acceptance

Identities, metric names, dashboard uids, rule names and service-account names **never** become metric labels.

This is absolute and independent of the deploying organisation's data policy. Identity-bearing
S3 and Loki detail requires explicit acceptance plus minimisation, reader access control, encryption
and retention. A cardinality guard proves none of those. A metric label is a different matter,
because a series persists for the retention period and cannot be selectively deleted.

The bounded daily label-risk sample is a narrower exception: full classified matches are approved
only in `risk_label_hygiene` and the private `label_risk` hydration input. They never enter Loki,
stdout, diagnostic `--out`, errors or metric labels. Ordinary/unmatched values and decoded JWT
claims are transient. Partial sampling is not an exhaustive privacy audit or proof of absence.

Two payloads are treated as radioactive:

- **The raw Alertmanager configuration** reachable through the declared but unused `alerts:read` grant, returned in `config.original` by `/alertmanager/api/v2/status`, `http_config` included. Where contact points live in Alertmanager rather than in Grafana, that YAML can carry webhook URLs and tokens. The collector does not call this route; nothing derived from that body may be stored, logged or emitted beyond bounded counts.
- **`accessToken` on a public dashboard**, which is the live public URL. It is never stored, logged or emitted.

The Prometheus firing-instance route reachable through the declared but unused `rules:read` grant
carries full customer label sets. The collector does not call it. Any future consumer must count
instances without carrying those label sets into metric labels.

## S3 boundaries

The Infinity reader principal is allowed on `views/*` and denied on `scans/*` and `locks/*`. Prove it with IAM policy simulation rather than by inspecting the policy document.

For `ssm:GetParametersByPath`, simulate the bare path ARN as well as a child ARN - the API authorises the path itself, so a child-only simulation can pass while the real call is denied.

`scan_retention_days` is a positive whole-day lifecycle setting, default 90. Current `scans/`
objects and the reserved full-key prefix `views/risk_label_hygiene.json` become eligible for expiry
since last publication. Hydration republishes and resets that age. Noncurrent versions expire after
seven days, with asynchronous AWS processing; this is not strict erasure 90 days from observation.
Other last-good views do not expire. Long-term history lives in Mimir, not in the archive.

For adopted buckets (`create_bucket = false`), verify equivalent targeted retention in the existing
lifecycle policy, versioning, encryption and effective reader access before raw-match publication.
Also verify a fresh effective bucket policy denying non-TLS access; a missing policy blocks that
publication. Lifecycle authority does not authorise adding a bucket policy or a competing lifecycle
configuration. The view's raw-match content is visible to the `views/*` reader, so that access must
be explicitly accepted rather than assumed safe because scans are private.

## Alert rules publish inert

New rules publish **paused and unrouted**. Activation requires naming a receiver, because an unpaused rule with no `notification_settings` inherits the write stack's notification policy - and that stack is a real stack whose policy may route hundreds of rules that are not yours, some to production ticketing.

## Credential handling

Read and write tokens, plus the provisioner token when that task is enabled, live as separate JSON
keys in one Secrets Manager secret and are injected by the ECS agent. They never appear in Terraform state, in a plan diff, or in the task role's permissions. The module contains the secret; it never manages the values.

Per-stack reader tokens are SSM `SecureString` values below the configured prefix.

Build-time Grafana credentials are separate from runtime credentials and should be short-lived. The dashboard build token is not a runtime secret.

Reader-token replacement must be explicitly authorised and recorded: confirm the new SSM value
works before deleting the old token. The reconciliation CLI has no general `--rotate` flag; a
permission repair must preserve a working credential. Token names are organisation-wide unique, so an unnecessary mint can create a timestamped credential and orphan the original.

## Supply chain

Release images are signed with Sigstore keyless signing and carry GitHub build provenance plus SPDX and CycloneDX SBOMs. A deployment resolves a reviewed tag to its immutable manifest digest and pins the digest - a moving tag does not change an existing task definition, and neither does a Git push.

## Fixtures

The repository contains **synthetic fixtures only**. A live compose-input export must be written outside the committed fixture path and anonymised before use.
