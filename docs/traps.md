# Traps

Behaviour that has cost real time. Every item here is a live-verified fact about Grafana Cloud, the
gcom API, Mimir, Loki, Infinity or the v2 dashboard schema. Read the relevant section before writing a
panel, a PromQL expression, an Infinity query or a collector source.

A recurring shape: **a 200 proves nothing.** Several endpoints here answer 200 and return an empty or
wrong-shaped body. Where that is the case it says so.

## gcom and the org-realm token

- **An org-realm token spans every region on the data plane**, despite the region hint in its payload.
 The control plane is a different matter: access policies are stored per region and
 `/v1/accesspolicies` returns only the region asked for. Reading one region of a ten-region estate can
 show you 2% of the policies and look complete. Sweep every region the inventory names, unioned with
 the three control-plane realms (`us`, `eu`, `au`), which are no stack's `regionSlug`.
- **`grafana.com` rate-limits hard. 6 requests per second is a measured ceiling.** Unpaced, a
 ~800-call sweep draws HTTP 429s and silently covers about 70% of the estate. `Retry-After` comes back
 at 8-10 seconds and there are no `X-RateLimit-*` headers to read. The quota is **per credential**, so
 two concurrent scans share it.
- **Paused stacks answer HTTP 409.** They are skipped, not failed. Coverage must be a ratio against
 scannable stacks, never against total, or a handful of paused stacks caps it below 100% for ever and
 trains everyone to ignore the warning.
- **The org token cannot reach a stack's own Grafana API at all.** `https://<slug>.grafana.net/api/…`
 returns 401 `api-key.invalid` for every path, `/api/search` included, so it is not path-specific. The
 gcom proxy 404s anything outside `/api/serviceaccounts*`. Anything needing the stack API needs a
 per-stack service account.
- **Read a stack's hostname, never derive it.** A stack's `regionSlug` and `clusterSlug` can differ, and
 legacy values break string-munging. The `url` field is the only reliable hostname: `name` can be a
 prefixed form that gcom then 409s on, while `slug` is the subdomain.
- **There is no `stack-service-accounts:read` org scope.** The API rejects it as `unsupported scope`.
 Only `:write` exists, so it is not given to the collector. This does not make the inventory
 unreachable: the stack-local `serviceaccounts:read` action reads it through each stack's own API.
- **The gcom proxy does not support PATCH** (405). Create, token, search and delete only.
- **Token minting is `POST /v1/tokens?region=<region>` with `accessPolicyId` in the body.** The
 plausible-looking `/v1/accesspolicies/<id>/tokens` 404s.
- **A failed mint response does not mean the token was not created.** Parse defensively and always
 `GET` the token list before re-minting: token names are unique per organisation, so a retry after a
 mis-parsed success fails with `ErrTokenAlreadyExists` while the first token is live on the stack.
- **`fleet-management:read` covers Fleet Management's Connect-RPC `List*` methods even though they are
 POST.** The scope maps to the method, not the verb. Do not add a write scope to fix a 403 there.
- **Fixed-role assignment to a service account 403s even from an Admin service account.** It holds
 `roles:write` but not `users.roles:write`, which org Admin does not have on Grafana Cloud. Per-stack
 service accounts must use a basic role or a custom role.
- **`/instances/<slug>/dashboards` is always empty**, and `/instances/<slug>/datasources` is partial.
 Use the inventory's own count fields.

## Inventory fields that mislead

- **Stack `id`, `hpInstanceId` and `agentManagementInstanceId` collide** - the same integer, on every
 stack. Disambiguate the signal with `instance_type`, not the id. There are no cross-stack collisions
 though, so a bare id always resolves to exactly one stack.
- **`hmInstanceGraphiteId == hmInstancePromId + 1`** on nearly every stack. A naive per-signal breakdown
 therefore reports Graphite activity on about half the estate when the real number is a handful.
- **`billingActiveUsers` is the only user count valid for money.** `currentActiveUsers` answers a
 different question and runs higher. Never quote the spread as a constant; it moves day to day.
- **`dashboardQuota`, `alertQuota` and `userQuota` can be `-1` estate-wide**, meaning unlimited. Quota
 headroom is then not measurable at all, and a panel showing it renders nonsense.
- **`customAuth`, `customDomain` and `ssl` can be `true` on every stack.** Zero variance, so a panel
 reads 100% everywhere and says nothing.
- **`k6OrgId` is an id-or-null, not a 0/1.** Test truthiness.
- **A feature flag proves the flag is unset, never that the org does not pay for it.** Present a zero as
 an enablement gap at most, never as wasted spend, without the contract in front of you.
- **On many estates `login` IS the email address**, and gcom does not always populate `email`. Anything
 checking for identifying fields must look at `login`.
- **`createdBy` / `updatedBy` are not ownership.** They resolve overwhelmingly to an org-level token or
 to empty, with the vendor's own staff on a handful of stacks.

## `grafanacloud-usage`, the datasource you already have

Provisioned on every Grafana Cloud stack, carrying org-wide billing and usage series. A panel reads it
directly: no service account, no token, no collector code, no series against your budget. **If the data
is already a datasource on the target stack, a panel beats a pipeline.**

- **`id` is the per-SIGNAL instance id, not the stack.** One metric can carry roughly twice as many ids
 as there are stacks. `count(<metric> > 0)` therefore counts series and overstates, badly. Always
 `sum by(stack_id)` or `count by(stack_id)` first. A bare count is only honest on a metric measured
 1:1 per stack, and that is a property to verify per metric rather than assume.
- **`grafanacloud_grafana_instance_info` carries `stack_id` AND `slug`**, one series per stack, so
 naming a stack is a PromQL join:
 `<metric> * on(stack_id) group_left(slug) grafanacloud_grafana_instance_info`. `group_left`, not `+`:
 adding folds the info series' constant 1 into every value. Without the join every panel shows numeric
 ids, because a Grafana panel cannot join across datasources.
- **A `$stack` variable built from your own metrics does not apply here.** This datasource has no slug
 label except via that join, so these panels stay estate-level.
- **Never compare a rate-shaped series to zero instantaneously.** Every `*_per_second` and `*:rate5m`
 series is momentary, so `> 0` asks "is this happening right now", not "does this stack have a
 problem". Wrap it in `max_over_time(...[24h])`, or `min_over_time` where a dip is the defect. Measured
 instant against 24h, the answers differ by factors of two to thirty, and one finding dissolved
 entirely. A persistent condition reads the same either way, which is the control case, not proof the
 wrapper is unnecessary.
- **Units are not implied by the name.** In the same metric family, `..._percentage_complete_traces_flushed`
 is a **ratio 0-1** while `..._spans_more_than_5m_in_past_percent` is a **real percent 0-100**.
 Thresholding the ratio at `< 90` matches every stack that reports and invents an estate-wide outage.
 The ratio can also go slightly negative, because it is a computed difference.
- **Exclude `reason="requested-by-configuration"` from any data-loss count.** That is Adaptive Metrics
 dropping what it was told to drop. Counting it reports a stack as broken for adopting the cost lever
 the cost dashboard recommends.
- **A "write-only stacks" panel counts empty stacks unless you require active ingest.** Join with `and`
 on a positive ingest rate, or the panel is just the inventory again wearing a finding's clothes.
- **The legacy standalone-Incident flag does not mean incident response is unused.** IRM and OnCall do
 not set it. A stack can carry thousands of OnCall alert groups with that flag at zero. For genuine
 entitlement read `grafanacloud_product_activation_status`.
- **`grafanacloud_instance_active_integration_series` carries an `integration` label**, and so does
 `..._active_integration_host_series` at metric-name granularity. The value set is Grafana's own
 integration catalogue, so it is discovered rather than maintained: one live org returned 100 distinct
 values, 79 of them `aws/*` CloudWatch namespaces, plus named technology such as `mysql`, `mssql`,
 `redis`, `mongodb-atlas`, `elasticsearch`, `snowflake`, `temporal`, `vault`, `jvm`, `tomcat`, `iis`,
 `docker`, `kubernetes`, `linuxnode` and `windows`. It is the cheapest named technology inventory the
 platform can publish.
- **The datasource carries far more than the dashboards read** - one live org exposed 311
 `grafanacloud_*` metric names. List the names before building a pipeline for an estate figure.
 Observed-object counters that already exist include `app_observability_service_entity_count`,
 `asserts_instance_active_entities`, `instance_active_target_info_series`,
 `instance_active_kube_node_info_series`, `instance_active_kube_pod_container_info_series`,
 `instance_active_caas_targets_series`, `instance_active_faas_targets_series` and
 `logs_instance_active_streams`.
- **Every one of those counters is a count with no name label.** They answer "how many", never
 "which". Names come from the signal databases' own label APIs, not from here.
- **The per-region usage-insights datasources only see their own region.** A central stack therefore
 cannot provide honest org-wide attribution. Pillar J uses one reader per measured stack and filters the
 regional tenant to that stack; one-stack-per-region would use stack A's identity to read stack B.

## Per-stack reader and usage insights

- **Role drift is action plus scope, not action name.** The same action can be granted at multiple
 plugin scopes, and Grafana adds its own pseudo-folder grants. A name-only comparison can call a role
 complete while one source remains unreadable.
- **`datasources:read` and `datasources:query` are separate.** Wide metadata read does not permit
 querying customer datasources. Keep query scoped to
 `datasources:uid:grafanacloud-usage-insights`.
- **Several list endpoints return 200 with permission-filtered results.** Search, folders, datasources
 and public-dashboard inventory can all return a plausible zero or short list without the matching
 action. Verify the role pair before trusting the count.
- **RBAC propagation can be partial.** The role body may show the new pair before an existing token can
 use every endpoint. Do not repair or re-mint on the first post-patch 403.
- **A working token must not be re-minted during an unrelated repair.** Token names are unique across
 the organisation; an unnecessary mint can create a timestamped token and orphan the original.
- **A usage-insights datasource exposes its whole region.** Every Pillar J selector must contain
 `instance_type="grafana"` and the current stack's `instance_id`. For Grafana events that id is the
 stack's own `id`, not its metrics tenant.
- **Build selectors through the one helper.** The query path refuses a template without the
 `instance_id` guard. A regional total repeated once per stack looks plausible because every event is
 real.
- **Aggregate in Loki.** Raw usage-insights events are high volume; the collector runs bounded scalar
 and top-N LogQL queries rather than downloading event lines.

## Adaptive recommendations and rate cards

- **Adaptive Metrics needs `?verbose=true`.** The default recommendation payload has metric and rule
 shape but no before/after series counts. It looks complete and cannot support savings arithmetic.
- **Remediable means positive marginal reduction.** Sum before minus after for `add` and `update`.
 `keep` changes nothing and `remove` preserves or expands output. Unknown actions or missing count
 pairs make the total absent.
- **One recommendation per metric is an assumption to re-verify.** If duplicates appear, summing them
 can double-count the same series reduction.
- **A rate-card miss is `None`, never zero.** Missing dimensions and partially priced totals must stay
 visibly incomplete. Zero rates are rejected too: omit an unpriced/free dimension rather than letting
 a placeholder manufacture confident zero currency. Mixed currencies are rejected and series prices
 declare their per-1,000 unit. Metrics carries two bases: `base_rate_only` excludes DPM, while
 `dpm_aware` applies `max(active_series, total_dpm / included_dpm)` per stack. A DPM-aware card never
 falls back to the two-input base-series saving.
- **Adaptive Logs volume is residual and windowless.** It ranks pending work but cannot recover applied
 saving or support a monthly conversion. The applied drop rate already exists in
 `grafanacloud-usage` and belongs in a panel.

## Public dashboards and alert routing

- **Enumeration and events answer different questions.** Stack-local enumeration finds configured
 shares nobody opens; usage-insights finds public shares observed in use. Keep both.
- **Never store `accessToken`.** It is the live public URL.
- **An unrouted active alert rule inherits notification policy.** Report inherited routing explicitly,
 and require a named receiver before activating this platform's own rules.

## OnCall response metrics

- **Two OnCall metrics cover different populations, and mixing them is an order-of-magnitude error.**
 The alert-group counter spans every stack with OnCall provisioned; the response histogram spans only
 the stacks that report timing, which is far fewer. Any ratio must restrict its denominator with
 `and on(stack_id)`.
- **A missing histogram observation means no acknowledgement was recorded.** Say exactly that. It is not
 evidence that nobody looked, and the metric cannot prove intent.
- **The buckets top out at 3600s, so `histogram_quantile` saturates.** p90 and p99 both return exactly
 3600, meaning "at least an hour". Only p50 is a real number. Express the tail as a count above the top
 finite bucket instead.
- **`le` label values carry a decimal point.** `le="3600"` matches nothing and renders empty. Use
 `le="3600.0"`.

## Denominators

- **Measure a denominator over the same window as its numerator.** Read instantaneously, "stacks
 ingesting traces" can be a fraction of the 24h figure, because trace ingest is bursty. Using the
 instantaneous count once turned a real 10% adoption gap into an apparent 46% success.
- **A synthetic floor is not adoption.** Many stacks report exactly 2 series for a signal they do not
 use. Thresholding at `> 0` claims near-universal adoption of everything; threshold well above the
 floor.
- **The series denominator for your own footprint is the write stack, never the org.** Every series
 lands on one stack, so the org figure understates it by roughly the number of stacks in the org.
 Measure by querying the stack, not by counting what you sent.
- **Billing-side active-series metrics are an averaging window, not an instantaneous count.** They will
 disagree with a query against the stack. Never quote one as the other.

## Mimir, Loki and the emit path

- **Never emit through the OTLP gateway.** Routing your own telemetry through the org's gateway inflates
 their gateway request counts and corrupts any protocol-adoption measurement you then publish. Push
 natively: Mimir remote_write, Loki push.
- **The remote_write tenant is the stack's `hmInstancePromId`, not the stack id.** The stack id fails as
 a 401 rather than as anything resembling a configuration error. Loki's is `hlInstanceId`.
- **Loki stamps `detected_level=error` on any line without an explicit `level`.** A healthy scan then
 renders as hundreds of errors in Explore Logs. Set `level: info`.
- **Never use an instant PromQL query on a dashboard fed by a periodic collector.** Mimir's
 lookback-delta is 5 minutes and an hourly writer leaves a sample visible for 5 minutes in every 60.
 An instant query returns an empty frame while the same expression over a range returns every point.
 Use a range query with a `lastNotNull` reducer, plus a `reduce` transformation for bar charts.
- **An alert on a sparsely-written series needs `max_over_time`, and its window must exceed its own
 threshold.** Same root cause, one layer up: a bare instant selector evaluates empty, and a window
 shorter than the threshold makes the series vanish exactly when the rule should fire.
- **Alert on an AGE, not on a count.** A `count > 0` condition with a `for` clause never resets while
 new stacks keep appearing, so it eventually fires having never seen a real fault. The age of the
 oldest gap is the honest signal.
- **A gap is an absent series, never a zero.** A tier that cannot compute a metric must not emit it: a
 structural zero written hourly overwrites the real value published by a slower tier, and
 carry-forward cannot rescue it, because carry-forward correctly refuses to republish a series the live
 tier claims to own.
- **Append to the metric list before the cardinality guard and the push.** Appending after either means
 the series is neither checked nor written, and the only symptom is a metric that is quietly always
 absent.
- **Metric labels carry bounded dimensions only.** `stack`, `region`, fixed enums. Metric names,
 dashboard uids, user emails, rule names and version strings go to Loki or S3. A per-stack metric
 should carry at most one other label with a small closed enum: on a 271-stack estate a `{stack,kind}`
 metric with a ten-value enum is 2,710 series, not 271.
- **`snappy` and `protobuf` are not required dependencies.** The Prometheus write request and snappy
 block framing are both short enough to hand-roll, and a single uncompressed literal run is valid
 snappy.

## S3 and the AWS CLI

- **`aws s3api put-object --body -` does not read stdin.** It fails with
 `ParamValidation: Blob values must be a path to a file`. `aws s3 cp s3://… -` *does* stream to stdout,
 so the asymmetry is real and only a live call reveals it.
- **`aws s3 ls <prefix>/` prints the object name, not the full key.** Returning it bare sends the next
 request to the bucket root.
- **The writer IAM policy needs delete on the lock prefix, not just put on scans and views.** Without
 `s3:DeleteObject` there, every run leaves its lock behind and the next run of that tier refuses to
 start, which reads as a scheduling bug and is an IAM one.
- **Prove the reader's scope with `simulate-principal-policy`, not by reading the JSON.** The dashboard
 datasource's credential must be denied on the scan and lock prefixes and allowed on views.
- **Never hardcode the bucket.** A task using a hardcoded default writes where its own role has no
 permission, and fails with an AccessDenied that reads like a broken policy.

## ECS, Fargate and EventBridge Scheduler

- **`ecs_parameters` has no `container_overrides`.** The AWS `EcsParameters` type does not support it,
 so a schedule cannot vary the tier. One task definition per tier is the consequence, not a
 preference.
- **Fargate `platform_version` 1.4.0 is a floor.** Injecting a single JSON key of a Secrets Manager
 secret needs it; 1.3.0 can only inject a whole secret. The grammar is `<secret-arn>:KEY::` and the
 unused trailing positions must still be present as colons, or ECS reads the whole string as a secret
 name.
- **A `deadline_seconds` must be strictly shorter than the tier's interval**, or a slow run overlaps the
 next and both write `latest.json`.
- **Three things are coupled to a tier's cadence.** Changing a schedule is not a cron edit: the
 deadline, the staleness alert threshold, and the carry-forward maximum age all move with it. The
 carry-forward age must stay longer than the alert threshold, so the alert fires before the panels
 blank rather than after.
- **A hand-run `aws ecs run-task` is untagged unless given `--propagate-tags TASK_DEFINITION`.**
 Scheduled runs are fine, because the schedule sets it. Distinguish them by `startedBy`.
- **EventBridge Scheduler schedules are taggable only via their schedule group.** A module using the
 shared `default` group leaves the schedules themselves untagged.

## Cost allocation

- **Only activated cost-allocation tag keys can be grouped by in Cost Explorer.** Every other tag on
 the resource is documentation. `aws ce get-tags` returns the keys that actually work; on a linked
 account `aws ce list-cost-allocation-tags` returns AccessDenied, because activation lives in the
 payer.
- **Cost allocation tags are not retroactive**, and there is roughly a day's lag before values appear.
 Tag before you want the data.
- **The AWS provider has no standalone tag resource for S3.** An adopted bucket can only be tagged out
 of band. Importing the bucket to fix that puts every scan and view in scope for `destroy`, which
 adoption exists to prevent. A secret, unlike a bucket, does have a standalone tag resource.
- **A first apply of standalone secret tags may error on one key while still applying it** - the
 provider's post-create read races the API's consistency. Check the live tags before believing it
 failed, then re-run.
- **`aws logs tag-resource` needs the log-group ARN with the trailing `:*` stripped.**

## The v2 dashboard schema

Target `dashboard.grafana.app/v2`, not classic and not `v2alpha1`, which has a different panel and query
shape. Read the schema at `/openapi/v3/apis/dashboard.grafana.app/v2` rather than inferring it.

- **The envelopes are not guessable, and getting one wrong renders the whole page as "plugin not
 found", not just the panel.**
 - query: `{"kind": "DataQuery", "group": "<plugin id>", "version": "v0", "datasource": {"name": "<uid>"}, "spec": {…}}`.
 `kind` is the literal string `DataQuery`, the plugin id goes in `group`, and the uid goes in
 `datasource.name` - not `uid`, and there is no `type`.
 - viz: `{"kind": "VizConfig", "group": "<panel type>", "version": "", "spec": {…}}`. Not
 `{"kind": "table"}`.
- **A dashboard link is the exception: it is FLAT, with no `kind`/`spec` wrapper.** Wrapping it by
 analogy with the other two is accepted by the API, which then drops the unknown keys and stores empty
 strings - you get header buttons pointing at `about:blank`. Required: `title`, `type`, `icon`,
 `tooltip`, `tags`, `asDropdown`, `targetBlank`, `includeVars`, `keepTime`. `tags` must be a list or it
 stores `null`, and `type` must be `"link"`, because `"dashboards"` ignores `url` and lists by tag.
- **An orphaned entry in `spec.elements` blanks the entire dashboard.** Validate that declared and
 placed elements match before publishing.
- **A `format: "table"` value column is named `Value #<refId>`**, so a `byName: "Value"` override
 silently matches nothing.
- **Forcing `query.kind: "prometheus"` on an Infinity-backed variable renders a 500.**
- **Read the dashboard back and assert the envelopes.** A test written from the implementation cannot
 catch the implementation being wrong about an external contract.

## Infinity

- **A query needs `parser: "backend"` AND an explicit `columns` array AND a `root_selector`. All
 three.** Measured against a real view: all three gives rows; no `parser` key or
 `parser: "simple"` gives 200 with zero rows; no `root_selector` produces one malformed root row.
 Current Infinity versions can infer columns, but the inferred alphabetical schema loses explicit
 selection, types and stable display order.
- **Generate `columns` from the view rather than writing it out.** It is also what fixes display order,
 and a hand-written list goes stale the moment a pillar adds a column.
- **A legitimately empty view fails the whole dashboard build, not one panel**, because a column spec
 cannot be derived from no rows. Declare a fallback schema for any view where finding nothing is the
 good outcome. Only for those: leaving it off is what keeps "the tier has not run yet" a build failure
 rather than a silently blank page.
- **Column order is fixed by an `organize` transformation, not by the key names.** Infinity's backend
 parser alphabetises by the stripped display text, so a leading space in a key does not order the
 column - it only changes the key you must use to read the row.
- **Both AWS keys go in `secureJsonData`, as `awsAccessKey` and `awsSecretKey`.** Putting the id in
 `jsonData.aws.accessKey` yields `invalid/empty AWS access key` with HTTP 403.

## Grafana Assistant

- **The only working route is the plugin-resource proxy**:
 `https://<slug>.grafana.net/api/plugins/grafana-assistant-app/resources/<path>`. The region-level
 Assistant URL 401s and `/api/v1/...` on the stack 404s.
- **Usage endpoints take `start` and `end` in epoch MILLISECONDS.** `from`/`to` gives 400, ISO-8601
 gives 422, and **epoch seconds gives HTTP 200 with every value zero** - a silent wrong answer.
- **The response is a Grafana dataframe with parallel arrays**: `values[i]` belongs to `fields[i]`. A
 frame carrying only a `time` field means zero, not a set of zeros.
- **Every inventory figure is tenant-scoped, and the panels must say so.** A user-scoped skill or rule
 is invisible to every other identity including a full Admin, and `pagination.total` reads 0 for it.
 Say "tenant skills", never "skills".
- **Watcher agents, investigation inventory and user-scoped objects are product boundaries, not
 permission gaps.** `/api/v1/watcher-agents` 403s for a full Admin. A wider role fixes none of them.
- **A 403 from the plugin proxy can be transient.** Give the first call of each stack one re-attempt.
 401 and 404 should not be retried, because neither changes in three seconds.
- **The plugin API's window and the billing metrics' window are different**, a rolling 30 days against
 the current billing period. On the same stack and the same day they disagree by a wide margin. Never
 let a panel compare them, and never present one as the other.
- **The per-identity token counter is cumulative; the aggregate resets monthly.** Never call the
 aggregate a lifetime figure.
- **`user_type="service"` is not proof of a service-account identity.** Live rows include human-shaped
 addresses. Present it as the service-token series category.
- **Self-managed usage folds into its connected Cloud stack.** The metrics carry no
 originating-instance label, so the datasource cannot split Cloud-native from self-managed use. That is
 not the same as self-managed use being zero, and unmatched ids are not an "external stack" count.
- **Message categorisation covers a minority of messages.** Every category figure needs an
 uncategorised remainder stated alongside it, and shares are of the categorised subset, not of total
 messages. The two sources can also disagree in both directions on the same stack, so clamp the
 remainder and show the disagreement rather than hiding it.

## Other data-plane endpoints

- **Tempo needs the `/tempo` path prefix.**
- **Fleet Management's basic-auth user is the stack id**, not a signal instance id.
- **`ListCollectors` returns a bare `{}` for a stack with no collectors**, not `{"collectors":[]}`.
 Read it with a defaulting accessor or a stack with nothing registered raises instead of counting zero.
- **`markedInactiveAt` alone understates dead Fleet registrations.** One live stack carried 26
 collectors with no `markedInactiveAt` whose `updatedAt` was eleven months old, and four of
 twenty-four sampled stacks had a newest `updatedAt` over ninety days. Recency of `updatedAt` is the
 stronger liveness test.
- **`remotecfg_*` is NOT a Fleet Management sentinel.** Measured against `ListCollectors` ground truth
 it has recall 0.47 under both a has-collectors and a checked-in-recently definition: it misses more
 than half of the stacks genuinely using Fleet Management, and it fires on stacks with no
 registrations at all. What it actually tracks is Alloy scrape breadth - the k8s-monitoring chart
 ships an eleven-name `alloy_*` keep-list that excludes `remotecfg_*`, so its presence is a property
 of the metrics pipeline, not of the product. Fleet adoption comes from the API, never from a metric.
- **The Alertmanager's basic-auth user is `amInstanceId`**, which is its own instance id and matches no
 signal. `{amInstanceUrl}/alertmanager/api/v2/status` also returns the stack's RAW Alertmanager
 configuration in `config.original`, `http_config` included, so on a stack whose contact points live in
 Alertmanager it can carry webhook URLs and tokens. Never store, log or emit that body.
- **The Loki ruler answers 404 `no rule groups found` when a stack has no rules.** That is an empty
 inventory, not a permission failure. `{hlInstanceUrl}/prometheus/api/v1/rules` returns 200 with an
 empty group list for the same stack, so prefer it and read the 404 as zero.
- **`{prom}/api/prom/api/v1/alerts` returns firing instances with their full customer label sets.**
 Unbounded and identity-bearing. Count them; never carry them into a metric label.
- **Mimir's ruler config API is not at `config/v1/rules` on Grafana Cloud** - that 404s. Rule state is
 `{prom}/api/prom/api/v1/rules`.
- **Adaptive Metrics config is `/aggregations/recommendations/config`.** `/aggregations/config` 404s,
 and no `/aggregations` exemptions path has answered 200 across eight tried variants.
- **Pyroscope's Connect-RPC returns 400 without a time range.**
- **Usage-insights `instance_type` has five values**: `alerts`, `grafana`, `logs`, `metrics`, `traces`.
 No `graphite`, no `profiles`.
- **A usage-insights endpoint can answer 200 to a labels call and then return zero streams** from
 `query_range` for the same credential. It needs a stack service-account token through the datasource
 proxy, not an org token.
- **`grafanacloud_grafana_instance_custom_datasource_count` has a floor of ONE, not zero**, and on the
 150 of 274 stacks sitting at that floor the single datasource is the auto-provisioned
 knowledge-graph one. `> 0` therefore claims universal adoption of nothing; threshold at `> 1`. The
 metric also equals `sum(datasourceCnts.values())` from the gcom inventory exactly, on every stack,
 so it is a lossier projection of a payload the collector already fetches - gcom carries the
 per-TYPE breakdown the billing datasource does not expose at all.
- **`grafana-knowledgegraph-datasource` is auto-provisioned everywhere.** Counted, it is the
 most-adopted plugin in the estate and means nothing. Exclude it from any adoption count.
- **Synthetic Monitoring rejects an org-realm token and 500s even from an Admin service account.**
- **`POST /api/v1/rule/backtest` returns HTTP 400 and is not worth pursuing.** To prove an alert fires,
 evaluate the live rule's own expression over a window where the fault really happened. That is
 stronger evidence than a synthetic backtest, because the fault window is real.

## Signal label inventory (Mimir, Loki, Tempo, Pyroscope)

The org CAP reads label names and values on all four signal databases with the same HTTP basic pattern
the collector already uses for cardinality: `<per-signal instance id>:<CAP>`, the username taken from
`dataplane.AUTH_FIELD`.

- **A widened access-policy scope reaches the signal databases MINUTES after the control plane, and the
 gap answers 401.** The access-policy API reflects a new scope immediately, so reading the policy back
 confirms only that the edit landed - not that the data plane will honour it. During the lag every
 affected signal answers
 `401 {"status":"error","error":"authentication error: invalid scope requested"}`, which reads exactly
 like a permanently wrong scope. Measured once: 401 within the first half hour of the policy update,
 200 on the same token, stack and username 46 minutes after it. **An existing token DOES pick up a
 scope added after it was minted - do not re-mint, and above all do not widen a scope further to chase
 the 401.** Wait, retry, and confirm with the same token against a broader-policy control before
 concluding anything.
- **One org-realm CAP reads all four signal databases across every region.** Verified on a live estate
 spanning eight Mimir regions: Mimir, Loki, Tempo and Pyroscope each answered 200 in all of them under
 a single region-`us` policy. The region hint in the token payload does not constrain the data plane.
- **A metric covered by an Adaptive Metrics rule answers HTTP 422 to a bare selector.** The body
 names the aggregated labels and says to use an aggregation function. Measured on two live stacks
 against a metric whose `collector_id`, `instance` and `job` labels were aggregated away. A panel or
 collector using the bare selector therefore errors on exactly the stacks that adopted the cost
 lever hardest. Wrap any selector that might be aggregated in `count(...)` or `sum(...)`.
- **`metrics:read` covers the whole Prometheus query API**, not only the cardinality endpoint.
 `label/<name>/values`, `series` and `query` all answer 200 under it.
- **`hmInstancePromUrl` carries no `/api/prom` suffix.** Every Mimir path is
 `{hmInstancePromUrl}/api/prom/api/v1/...`. Omitting it is a 404, which reads as a missing endpoint
 rather than a path bug.
- **Mimir's label-values endpoint defaults to the whole retention window.** Unbounded and 30d agree; a
 24h window can return a third fewer names, because a name that received nothing recently is still in
 retention. With no explicit `start`/`end` an asset inventory reports decommissioned technology as
 currently observed, and the answer looks entirely plausible. Loki's default is a short recent window
 rather than full retention, so the two databases disagree on what "no window" means. Pass the window
 explicitly on every call to every signal.
- **Pyroscope wants epoch MILLISECONDS** in `start`/`end` on
 `querier.v1.QuerierService/LabelValues`, and returns 400 without them.
- **Tempo tag values are objects, not strings**: `{"tagValues":[{"type":"string","value":"cart"}]}`.
 The scoped tag list is `/api/v2/search/tags`; values are `/api/v2/search/tag/<tag>/values` and the tag
 name is fully qualified, for example `resource.service.name`.
- **A signal with no data answers 200 with an empty list.** That is a measured absence and a real
 adoption finding. It is not a permission problem and must not be retried as one.
- **Named service inventory is unbounded and its size varies by three orders of magnitude.** Across six
 sampled stacks on one day, distinct Loki `service_name` values ranged from 2 to 2,721. A view keyed on
 service name needs a top-N bound, and a metric label on service name is never viable.
- **Distinct metric names per stack is the largest response on this path** and the only one worth
 sizing. Bound it with both `limit` and the window, and never carry the name list itself into a metric.
- **Four label reads per stack complete in roughly one to four seconds**, so the whole estate at the
 collector's existing concurrency is a couple of minutes. This belongs in a daily tier, not a fast one.
- **`target_info` is NOT a sentinel for OpenTelemetry instrumentation.** Measured on a 270-stack
 estate it is present on 231 stacks, and on 190 of those the ONLY series is a single per-stack
 synthetic health-check canary whose `job` and `service_name` are equal. Genuine OTel SDK resources
 were 19 stacks; every OTLP-protocol application instrumentation including eBPF and a Micrometer OTLP
 registry reached 26. The metric overstates by roughly nine times. What it actually means is 'an
 OTLP-to-Prometheus conversion has happened here at least once', and in practice that is dominated by
 synthetic probes, collector self-telemetry, and Collector infra receivers (postgres, hostmetrics,
 prometheus, ECS, k8s) that contain no SDK at all. The honest name-only sentinels are the HTTP semconv
 counters, which measured zero false positives.
- **`jvm_memory_used_bytes` is not an OTel sentinel** - eight of its stacks were Micrometer or JMX
 Prometheus exporters. It is a fine sentinel for a JVM, and a wrong one for instrumentation flavour.
- **A sparse sentinel flaps under an instant query.** A canary writing every few minutes was measured
 present on 40 stacks at one instant and 188 five minutes later, against 190 over an hour. Evaluate
 every sentinel-presence check over a range window of at least ten minutes; an hour is safer.
- **Metric labels in a customer estate can carry PII, and this platform must never widen it.** One live
 estate had an agent CLI exporting `user_email` as a metric label - per-person identity in Mimir
 labels at unbounded cardinality. Reading such a series is unavoidable when sweeping label values;
 carrying it into a published view, a log line or a metric label is not. Treat any label that could
 name a person as unpublishable, and report the finding to the estate owner rather than storing it.
- **A first-token metric-name prefix is not a technology.** `node`, `go`, `http`, `container`,
 `process`, `cluster` and `rest` are generic and classify confidently wrong. Match one unambiguous
 sentinel metric name per technology instead, and publish the unmatched share alongside every
 classification: a curated registry always lags the estate, and a panel that hides the remainder claims
 a completeness it does not have.

## Writing about any of this

- **Never put a measured figure in always-on prose** - a banner, a panel description that is really an
 assertion, a sentence in a README. It goes stale silently and is then quoted. State the rule and
 point at the panel that measures it.
- **Name the command, not the number.** Estate counts move day to day.
- **A view can legitimately be a whole table rather than a finding set.** A table of 4,964 rows with a
 `Flag` column marking the two that matter is not 4,964 findings. Filter deliberately, and do not
 filter twice.
