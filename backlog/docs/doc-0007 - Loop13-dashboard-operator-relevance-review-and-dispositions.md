---
id: doc-0007
title: Loop13 dashboard operator relevance review and dispositions
type: other
created_date: '2026-10-06 10:46'
updated_date: '2026-10-06 10:50'
---
# Operator relevance proposal

Lane L-relevance13; GCI-0100 (review every dashboard and tab for operator relevance). Candidate only; root alone admits changes and records the Backlog document/tasks. Base: `689cb1e238ff1c601c4d1282e70d1f7ae96db2a0`.

## Scope and evidence

Read-only review of all 11 definitions and all 93 authored definition tabs, including optional tabs, plus 11 assembled **How to read this** tabs and five **Findings** tabs: maximum 109 tabs. Conditional tabs are not claimed to be present in any deployment. Reviewed every panel call extracted by Python AST (titles, expressions, units, descriptions and tab placements), shared builders, assembly, optional-publication branches, retention helpers and finding definitions. No customer data, credentials, AWS reads, Grafana calls, tracker mutations, implementation changes, test changes, commits or publishes.

Evidence identifiers: `/Users/rob/repos/grafana-cloud-org-insights/bin/dashboards.py:d_estate`, `d_cost`, `d_usage`, `d_maturity`, `d_risk`, `d_value`, `d_operations`, `d_commercial`, `d_ai`, `d_dashboards`, `d_coverage`; `BUILDERS` at 4904; `assemble` at 4913; `/Users/rob/repos/grafana-cloud-org-insights/collector/dashboards/build.py:DASHBOARDS`, `table_panel`, `timeseries_panel`, `barchart_panel`, `findings_elements`; `/Users/rob/repos/grafana-cloud-org-insights/collector/dashboards/retention_panels.py:retention_panels`; `/Users/rob/repos/grafana-cloud-org-insights/collector/pillars/findings.py:SPECS`. This is source-level operator review, not browser evidence or live semantic qualification. No panel is certified live-working or dead from this review alone.

Read task and doc-0006 (feature usage observability matrix) with read-only Backlog CLI; also read six planned-wave tasks. CLI captures: `/tmp/relevance13-task.log`, `/tmp/relevance13-doc.log`, `/tmp/relevance13-wave.log`, `/tmp/relevance13-planned.log`. Panel extraction: `/tmp/relevance13-definitions.log`; tab-count check: `/tmp/relevance13-map-check.log`. Related reference: /Users/rob/repos/grafana-cloud-org-insights/docs/traps.md. No gate requested or run.

**Critical interpretation:** doc-0006's September 30 semantics correction supersedes its original metric-shape guesses. OnCall alert groups are an explicit vendor **gauge**, histograms cover **last seven days**, and much billing/host normalization remains unresolved. Its October 5 host-hour section explicitly says exact host/host-hour fidelity remains unestablished. A roster occurrence proves a name, not a window, unit, population, monotonicity, reset or human adoption. Later Assistant org-user and Agent contracts qualify only their named surfaces.

## Already planned: do not create duplicate tasks

| Existing work | Panel relevance and proof still required |
|---|---|
| GCI-0094 (fix dashboard names and deployment-specific contract text) | Correct App O11y host v2/v3 names and remove Commercial deployment text. Name occurrence proof is enough for spelling, not host-count semantics. Broader interpretation corrections below are separate unless root explicitly extends this task. |
| GCI-0095 (Commercial per-stack cost showback) | Already owns overall/per-line top-N, named stack totals, reconciliation, unattributed lines, derived currency and the authorised SPEC change. Do not open another cost-ranking task. Per-line population and billing normalization remain proof obligations. |
| GCI-0096 (cost attribution, allowances, DPM reconciliation and seat utilisation panels) | Already owns these four families. Add no second seats/allowances/attribution proposal. Unknown units/window must remain explicit, not silently inherited from the old appendix. |
| GCI-0097 (Operations generator, ruler and Logs Export health panels) | Already owns those missing families and per-stack breakdowns; do not duplicate them under Risk. Name, normalization and percentage-versus-ratio proof still required. |
| GCI-0098 (SM, Kubernetes, Knowledge Graph and PDC adoption rows) | Already owns new capability rows, call lists and owner-approved estate series; **needs-series/scope/SPEC**, not eligible for the zero-series subset. Its OnCall gauge wording correction does not fix the Operations histogram denominator. |
| GCI-0099 (harden dashboard coverage gates) | Already owns enum/empty-fixture/per-tab/hydration coverage. Relevance acceptance below complements it with rendered rankings, scope and empty states; do not replace it with more string-presence tests. |

## Prioritised new candidates and acceptance contracts

Every matrix row below inherits the named candidate's owned files, metric-name proof and acceptance, with its panel-specific action added. All `P` items are **panel-only (zero new series)**. All `N` items are **needs-series/scope/SPEC**, with the precise blocker stated; that label does not request a new series automatically. A text correction can be P while a new quantitative claim about the same panel remains N.

Owned implementation files for P1-P7: `/Users/rob/repos/grafana-cloud-org-insights/bin/dashboards.py`, `/Users/rob/repos/grafana-cloud-org-insights/collector/dashboards/build.py`, `/Users/rob/repos/grafana-cloud-org-insights/tests/test_dashboards.py`; add `/Users/rob/repos/grafana-cloud-org-insights/collector/dashboards/retention_panels.py` and `/Users/rob/repos/grafana-cloud-org-insights/tests/test_retention_panels.py` only for P5 retention. These are *proposed* ownership, not edits or allocations. Test-file existence/naming must be checked before assignment. Any implementation also needs normal `just check`; rendered local/staff browser proof must be authorised separately, never a customer probe by default.

1. **P1 - P0 honest interpretation and scope text.** Correct claims unsupported or contradicted by doc-0006; distinguish configured/L2, reporting/L3 and people/L4 in visible panel titles or nearby text, not only tooltips. Immediate safe edits: remove lifetime/rising-counter claims about OnCall; call the histogram seven-day observations; stop saying absent profiles, SM or top-N rows prove zero; remove automatic rule-deletion instructions. **Proof:** no new metric names; cite exact existing expressions and doc-0006's corrected entries. Acceptance: seeded source assertions reject old claims; assembled panels retain data rather than substitute fabricated zeros; cold reader can identify producer window versus dashboard range and absence versus measurement. Quantitative engagement correction is N1, not this text-only item.
2. **P2 - P0 sparse-series and outage honesty.** Investigate source-proven false-health affordances: Estate `b_failed` unconditionally `or on() vector(0)` (659), all trends' `spanNulls=True` (`timeseries_panel`), and lastNotNull rankings retaining old members. Qualify failures with successful scan/completion evidence over the same tier/window; without it show unavailable rather than healthy zero. Disable bridging for freshness/coverage/failure integrity trends, retaining any intentional bridge only with an explicit rationale. **Proof:** existing `gcinsight_scan_stacks_failed`, `gcinsight_scan_completed_timestamp_seconds`, `gcinsight_input_available` declared/produced contracts, not a new vendor name. Acceptance: synthetic stopped publisher renders unavailable and a gap; healthy scan with no failures still renders honest zero; a partial-tier fixture does not certify all tiers healthy. Do not choose an arbitrary success-age cutoff without existing policy evidence.
3. **P3 - P1 ranking policy and readable work queues.** Distinguish range top-N union from current endpoint membership. Adopt Cost's explicit pair (970/979) as a pattern only where spike history is useful; otherwise endpoint-filter plus sort plus display limit, with title specifying endpoint/window. `limit=N` alone does not establish current membership. Fix Maturity bottom-score colours (1673: current lowest values orange then higher red) and label trend top-N as changing membership. **Proof:** reuse each panel's exact existing metric; require emitter proof for collector names, roster occurrence plus unique stack-id-to-slug join proof for usage names, with no new semantics. Acceptance: moving-membership fixture has >N historical entrants but endpoint queue exactly N; sorted worst first; low score red, stronger score less severe; removed/absent members not resurrected by lastNotNull. No blanket replacement of useful union panels.
4. **P4 - P1 selector and ratio population honesty.** Add visible estate/selected scope to headlines where selected tables coexist with estate metrics; do not build another variable or silently filter global findings. In Maturity `n_ranked` filters selection but percentile stats do not (1632-1650); Value Savings repeats `n_remediable` from Overview (2910-2911), while tables are stack-filtered. Global findings bars have no stack dimension. **Proof:** existing selectors and `table_panel` auto-filter behavior; no new name proof for text. Acceptance: All, one stack, multiselect and prefix-collision cases make scope explicit; numerator/denominator cover the same selection; global ratios are never labelled selected. Exact current versus historical inventory membership is not solved merely by changing labels.
5. **P5 - P1 action links and exact drilldowns.** Add field/panel links only where existing returned identity supports a reliable destination, carrying stack/time/window; use collector S3 identifiers or the already existing usage info join, never derive hostnames. Retention candidate table currently offers numeric IDs only; add slug display using proven same-datasource lookup while preserving numeric join keys. Findings details must expose their actual condition, not every row of a broader source view. **Proof:** exact existing field names/schema; `grafanacloud_grafana_instance_info` name/uniqueness and link destination schema before use. Acceptance: rendered clicks resolve the intended stack/table/object under configured prefix, single and multiple selections; optional identity missing produces no invented link; sensitive values do not leak into URLs. Keep native tables beside visual summaries.
6. **P6 - P1 visible optional-view coverage and freshness.** On each optional configured inventory show the *publication's* timestamp/input provenance and unavailable meaning, including last-good stale state. Preserve distinct not-enabled/unavailable/unknown if metadata distinguishes them; otherwise say only unknown. Avoid permanent empty product tabs: use a single concise configured-footprint overview linking to optional detail, retaining detail when an object exists. **Proof:** metadata/schema introspection before any query; no product metric name required for S3-only panels. Acceptance: absent object, measured-empty object, partial coverage, old last-good and permission error each render honestly; access/transport errors are not swallowed as absent. If existing metadata cannot distinguish a requested state, that state goes to N3, not an invented zero.
7. **P7 - P2 reduce duplication and decision-free clutter.** Keep different fidelities separate, but reuse summaries and link to canonical detailed queues rather than copy large inventories into three tabs. Do not remove unique fields/trends to achieve a cleaner screenshot. Convert ordinary Overview grids to short stat rows plus full-width trend/detail rows; reduce multi-panel mixed-scale walls. **Proof:** compare expressions and fields, not titles; retain every published field/metric covered by the existing gates; no new metric names. Acceptance: assembled coverage remains complete, default landing shows a decision and its denominator at normal viewport, and a reader reaches full detail in one click. No tab deletion without root approval.

**Eligible subset for root admission, in order:** P1 conservative text corrections; P2 integrity gaps where existing success policy suffices; P4 visible scope/denominator labels; P3 Maturity colours and selected endpoint queues; P5 finding condition/drilldown alignment; P6 already-supported metadata; P7 layout/duplication cleanup. They introduce no new series or reader grants and require no newly invented vendor metric. P5's slug join and any P3 usage-name change remain conditional on exact name/join witness. Avoid admitting every matrix row as a separate task; group shared builder fixes once, then bounded panel-specific deltas.

### Owner-needed, separate from the eligible subset

- **N1 - OnCall comparable population/window contract (P0).** `ENGAGED_DENOM` joins stacks, not producer windows; seven-day acknowledgement observations divided by gauge state counts of unspecified horizon cannot be certified an acknowledgement share. Affects Operations Engagement/Ownership, Coverage Outcome value/Unit economics and Value OnCall use. Options for owner: retain separately qualified counts and timing distributions, or authorise research for a matched seven-day group population before any engagement/"no acknowledgement" ratio. Never rate/increase the gauge. Metric proof: exact group and histogram family vendor contracts, horizon/reset/eviction/state cohorts and team labels, not roster spelling. Owned proposed files: `/Users/rob/repos/grafana-cloud-org-insights/bin/dashboards.py`, matching semantic tests; collector changes only if owner approves a new source. Acceptance: numerator and denominator are independently shown to share group cohort/window; otherwise withhold the ratio and its causal conclusions. GCI-0098 (extend capability adoption rows) is not this cross-panel repair.
- **N2 - product/host/billing semantics (P0/P1).** Workload's pods/hosts/host-hours and Coverage's per-host-hour/App-service economics overstate fidelity accepted by doc-0006's October 5 host-hour gap. Exact names may already exist but are not units/populations. Retain raw reported observations with unknown unit/window or withhold monetary conversion; no extrapolated hosts, hours, mobile sessions or saved currency. Metric proof: per-family normalization, overlap/deduplication, per-stack scope, billable interval and currency/period; a host metric spelling fix alone is insufficient. Owned: `/Users/rob/repos/grafana-cloud-org-insights/bin/dashboards.py`, semantic tests; reference decision may require /Users/rob/repos/grafana-cloud-org-insights/SPEC.md. Acceptance: independent authoritative contract/control supports every converted unit, and unknown dimensions stay unknown. Fold relevant billing changes into GCI-0095 (per-stack showback) and GCI-0096 (attribution, allowances, DPM and seats); keep unresolved host qualification separately owner-owned.
- **N3 - new metadata/history or dynamic inventory scope (P1).** A genuine per-view completeness state, all-input freshness qualification or trend of optional configured counts needs an emitter/hydration schema change if the required provenance is not published. A selector/rollup guaranteed to contain only the current inventory may require a discovery-backed view; historical Mimir label values and vendor info presence are not a fresh live estate contract. Owned: `/Users/rob/repos/grafana-cloud-org-insights/collector/emit/hydrate.py`, affected pillars/view schemas and tests, `/Users/rob/repos/grafana-cloud-org-insights/bin/dashboards.py`; budget only if a trend is justified. Metric proof: no guessed name; new series need catalogue/budget and bounded dimensions. Acceptance: inventory-failure/empty-unknown/removed-stack/last-good cases preserve estate safety; schema derived and documented. No new configuration roster.
- **N4 - product attribution, people and outcomes (P2).** Per-app Drilldown, mobile users, self-managed Assistant split, Agent cumulative generations, automatic remediation and saved operator time are not panel-only additions. Doc-0006 explicitly leaves those contracts unestablished; do not infer them from app/scenes/backend, non-web surface, positive rates or medians. Owned: future named source/pillar tests, /Users/rob/repos/grafana-cloud-org-insights/SPEC.md only after owner admission. Metric proof: exact independently correlated app/user/source or cumulative/reset contract plus approved route/scope/minimization. Acceptance: real authorised control demonstrates the claimed fidelity; no new grant/customer enablement follows from this proposal.

## Complete dashboard/tab review

Each row names a concrete panel action. `P#` means panel-only; `N#` means needs-series/scope/SPEC. Owned files/proof/acceptance are inherited from the candidate contracts above. Line numbers are in `/Users/rob/repos/grafana-cloud-org-insights/bin/dashboards.py` unless a helper is named. Keep useful existing trends, rankings and full tables; no live-dead diagnosis is asserted.

### Estate - d_estate:489 (7 definition tabs)

| Tab | Panel-level recommendation |
|---|---|
| Overview (719) | P7: `n_stacks/n_active/n_dash/n_users` short headline row; keep `t_stacks/t_content/t_users` full-width. P1: growth without new users is a leakage hypothesis, not proof. |
| Composition (721) | P1: `n_us_region/b_region` replace Swiss-pharma-specific framing with deployment-neutral residency review; retain stack-not-workload caveat. P5: `drift` links to All stacks/context; compare baseline version explicitly if existing columns support it. |
| All stacks (722) | P5: `estate` add contextual stack-detail link using available identity, retaining all rows and unknown admin share; P3: ensure advertised active-series default rank survives table rendering. |
| Leakage (723) | P1: `b_leftover/billing` state billed-use candidate, not "nobody uses it" or automatically removable; P7: put billing queue above governance-only idle rows, keep delete protection visible. |
| Change (724) | P6: `diff_daily/diff_weekly` keep actual achieved comparison interval visible; explain absent baseline beside the table, not only in tooltip. No manufacture of change when either side unmeasured. |
| Scan health (725) | P2: `b_failed` do not show synthetic healthy zero during outage; P1: rename `t_carry_series` to "Series carried forward" because no computed-live line exists; P7: runtime/headroom prose must not claim current healthy state from historical observation. |
| Data freshness (727) | P2: `t_inputs/t_input_avail` show gaps, not spanNulls interpolation; P7: separate consuming tier rows or a filterable table to avoid a many-input spaghetti chart. N3 if desired availability detail is not currently exported. |

### Cost - d_cost:818 (7, one conditional)

| Tab | Panel-level recommendation |
|---|---|
| Overview (1199) | P4: `n_series/t_series` say selected stacks, while `n_ratio/n_unadopted/n_rules_applied` visibly estate-wide. P1: active series is a driver, not a complete bill (DPM and other products matter). |
| Levers (1201) | P5: retain `cardinality_treemap` plus exact `cardinality` queue; distinguish full cardinality register from finding-filtered rows. P6: keep headroom's published rules coverage next to its table if not already present in this row. |
| Savings available (1202) | P1/N2: `n_savings_frac` must not promise aggregation "without losing a query" from name-only gauge evidence. P3: retain the deliberate historical-union/endpoint pair; P5: link named metrics to existing recommendation detail with bounded-retention caveat. |
| Adaptive Logs (1203) | P4: `b_al_pending` uses no stack filter although some companion tables do; label estate rank. P1: pending API-window bytes are not monthly savings; realised drop trend is reporting, not proof of business benefit. Retain unqueried subset and owner review. |
| Biggest stacks (1204) | P3: `t_top/t_billed_top` describe changing membership; add one endpoint ranked companion only if trends are hard to action, using existing metrics. P1: `cost` says cost drivers, not a completed chargeback; showback is already planned. |
| Signals (1205) | P1/N2: `b_signal_volume` must state unit/window by signal; "VOLUME" alone does not prove logs/traces/profiles comparability. Prefer separate mini-panels if units differ; keep Current vs Billing table. |
| DPM-aware savings (1208; rate-card conditional) | Existing before/after and regime rank are useful; P6: explain missing tab as absent DPM-aware configured card, not zero saving. GCI-0096 (DPM/vendor reconciliation and cost families) owns reconciliation; N2 for billing/recommendation horizon qualification. |

### Usage - d_usage:1214 (15, nine optional configured tabs)

| Tab | Panel-level recommendation |
|---|---|
| Overview (1577) | P1: rename `n_types` "Datasource types configured", not "in use"; `t_stick` denominator is active users, not everyone with access. P7 short headlines with estate stickiness plus visible population. |
| Adoption (1578) | P1: `plugins/t_signals` clearly configuration versus reported production; retain `enterprise_catalogue` coverage and unknown licensing. P5 link vendor type ranking to existing named Coverage datasource register rather than infer real demand. |
| Configured library panels (1579; optional) | P6: `library_panels_inventory` show publication age and measured-stack coverage; configured-object counts only, no rendered-instance sum. Preserve same-token folder visibility caveat. |
| Configured playlists (1582; optional) | P6: `playlists_inventory` show measured count/time and absent-state explanation; no playlist execution trend without N3. |
| Configured reports (1585; optional) | P1/P6: `reports_inventory` keep disabled included and configured, not delivery or success; visible published timestamp/denominator. |
| Configured PDC private networks (1588; optional) | P6: `pdc_networks` retain complete realm/page qualification; do not compare policy count as equivalent to connected agents. P5 link to existing adoption/reporting panels, not token routes. |
| Configured AWS accounts (1591; optional) | P1/P6: `cloud_accounts` clearly AWS-only; no empty Azure/GCP bars; measured time/denominator beside counts. |
| Configured forecast jobs (1594; optional) | P1/P6: `ml_jobs` count configured jobs, no failed-job claim or status field invention; provenance visible without touching job details/keys. |
| Configured Faro apps (1597; optional) | P1/P6: `faro_apps` preserve web/mobile/unknown classes, include count coverage/age; N4 for sessions/users by mobile class. |
| Configured IRM integrations (1600; optional) | P6: `irm_integrations` mark configured versus counted alert activity and exact publication coverage; never read a secret-bearing list for a richer panel. |
| IRM alert groups (1603; optional) | P1/P6: `irm_alert_groups` render count with exact/lower-bound relation and API-default window immediately adjacent; no lifetime or seven-day inference. |
| Engagement (1606) | P1: `dormant` zero daily users is not lifetime unused; `b_recency` never-login does not prove paid licence. P7 avoid three equal-height full tables; keep identity detail access-sensitive and below summaries. |
| Protocol adoption (1607) | P3: `n_otlp/n_otlp_floor/t_otlp` currently bare-count series; require 1:1 proof or collapse `stack_id` as Coverage already does. P1: <=1000 is not necessarily on the synthetic floor. Metric-name proof: existing `grafanacloud_instance_active_otlp_series`; threshold remains judgement. |
| Unread telemetry (1608) | P1: `n_logs_unread/b_logs_unread` no recorded queries over matched 24h, not proof nobody benefits from retained logs; remove 13-month deployment assertion. P5 retain owner-ranked rate queue; do not add rejected metrics-write-only feature. |
| Workload (1610) | P7 move duplicate adjacent AI cards to links, group units/populations rather than giant mixed bar wall. GCI-0094 (name/text fixes) owns host v2/v3 spelling. N2 blocks turning raw service/series observations into proved hosts/pods/hours; P1 `b_profiles` absent is unknown, not measured absence. |

### Maturity - d_maturity:1630 (7)

| Tab | Panel-level recommendation |
|---|---|
| Overview (1745) | P4: selected `n_ranked` cannot qualify estate `n_median/n_p90/n_worst`; visibly label populations or make all the same. P1 remove stale weekly-gather cadence language. |
| By dimension (1746) | P6: `b_dims/t_dims` need visible component denominator/unknown explanation; N3 if the numerical per-dimension measured count is not exported. Retain weakest-first direction. |
| Leaderboard (1747) | P3: `b_bottom` threshold colours worst-red and explicit endpoint ranking; `b_top` distinguish small high-score stacks from high-load reference implementations. P5 `board` drilldown to Explain a score. |
| How it is scored (1748) | P7 keep versioned `rubric` canonical and show version/weight denominator before `summary`; avoid duplicate prose but preserve all published rubric fields. |
| Who owns what (1749) | P1/P5: `owners` is admin contact inference, not business ownership; contextual link from stack score into this table, no automatic outreach. |
| Explain a score (1750) | P5: `dims` link from Leaderboard with stack context; make score and applicable/unscored components explicit, preserving blank rather than failure. |
| Not scored (1751) | P1/P7: `unscored_detail` currently full `maturity` table with scored blank reasons; add honest title or panel-local nonempty-reason filter plus link to full board. P4 reason counts remain estate-scoped. |

### Risk - d_risk:1767 (13, privacy optional)

| Tab | Panel-level recommendation |
|---|---|
| Overview (2592) | P7 compact actionable protection/exposure summary; keep broad inventory/active-fleet context secondary. P4 distinguish estate totals from selected summary rows. |
| Public dashboards (2594) | P1/P6: `n_public/n_public_events` retain configured versus observed-open distinction, put independent input ages/denominators on the tab. P5 `public_dashboards` links only with safe dashboard uid, never public access token. |
| Delete protection (2595) | P1: `t_noprot` all unprotected versus `noprot` material-load subset must be explicit; P5 table stack-owner context. Do not make deletion recommendations for low-volume absent rows. |
| Data loss (2596) | P1: `b_trace` says below 90 amber although configured thresholds are red; align wording. `b_spans_late/b_trace_discard` units require doc-0006 normalization qualification (N2 analogue), not confidence from suffix. P3 endpoint fault work queues preserve windowed spikes. |
| Alerting health (2606) | P1: `n_deadrules/b_deadrules` replace "delete rules"/"can never fire" with review query/metric lifecycle; low-frequency or deliberately absent metrics can be valid. P5 existing stack+integration queue is actionable; GCI-0097 (new health families) owns added coverage elsewhere. |
| Alert routing (2614) | P6: `n_routing_available` max across consuming tiers can say available while the table's publication is stale; show that view's own provenance. Retain inherited not automatically broken, missing explicit receiver versus builtin unknown. |
| Logs retention (2615) | P7 retain effective status and request history separately, prioritize policy breach queue before long history. P5 link compliant/unknown status to same stack's detail; never infer effective override from request list. |
| Access (2631) | P7 separate org membership/staff-access and stack governance rows; P5 `policies` preserve exact region lookup and report-only caveat, no remediation shortcut. Unknown staff-access must remain visible. |
| Label cardinality (2632) | P1/P6: maintain Mimir top-20, high/possible tiers and measured-stack count visibly; empty findings require coverage qualification. P5 filters by confidence within existing table, no raw values added. |
| Label privacy risk (2633; optional) | P6 keep coverage before classified detail and publication age; P1 sensitive clear-value warning visible without hover. Do not copy values into shared Findings, links, screenshots or Loki. No privacy expansion proposed. |
| Credentials (2634) | P7 put Flag/Token hygiene actionable custom accounts first in `sa_inventory`; retain Grafana-managed context separately, not as healthy proof. P6 unreadable token metadata stays unknown. |
| Collectors (2641) | P1: `n_coll_active` says not marked inactive but source liveness also depends on recency; display source definition consistently. P5 `fleet` advertised start-by-series hides Active series in selected columns; restore existing field if schema proves it. P7 reach/unparsed and fast-cadence queues above attribute taxonomy. |
| Per stack (2642) | P5 `risk` contextual links to existing access/protection/fleet queues; P4 selected-table scope explicit versus estate cards. Preserve completeness and nulls. |

### Value - d_value:2648 (7)

| Tab | Panel-level recommendation |
|---|---|
| Overview (2910) | P1/P7 `n_unit/t_unit` are series per billed user, not monetary ROI or total efficiency; increasing users can lower ratio without cost falling. Link to Commercial showback instead of more spend stats. |
| Savings (2911) | P4 repeated `n_remediable` is intentional context, not a separate measure; qualify selected `savings` versus global stats. P1 money titles/unit must follow actual rate-card currency/period, never default `short` presented as exact money; N2 if metadata unavailable. |
| Adoption (2919) | P1 `b_adoption/adoption` are reported ingest population, not human use; preserve signal-specific floors/units rather than a universal series threshold. |
| Capability flags (2920) | P1 `n_oncall/b_oncall` gauge >0 is not current human operation or lifetime events. N1 for active-window claim. P7 link Operations canonical details, retain distinction from legacy gcom flag. |
| Test and probe adoption (2921) | P1 `b_sm_active` absent is unknown, not "ran no checks"; k6 billing-period/window remains N2 until exact contract. Retain provisioned versus reporting populations without subtracting mismatched cohorts. |
| Capability gaps (2927) | P1 `b_capability/t_capability` must not say PDC and Adaptive Logs are universally metrics-feature subsets; each has own eligible population. GCI-0098 (new adoption rows) owns durable populations/call lists; P7 link that canonical queue rather than duplicate new rows. |
| Benchmarks (2933) | P5 `bench` retain median/p90/worst and measurement basis; link Maturity component explanation where applicable. P1 show ratios versus percentages visibly, not one interchangeable adoption score. |

### Operations - d_operations:2939 (5)

| Tab | Panel-level recommendation |
|---|---|
| Logs retention (3154) | P5 helper `_ret_candidate_table` add verified slug display and link Risk's effective retention; preserve numeric join keys. P6 `_ret_denom` should expose matched lookback-and-retention population if available, not just any limit. N2 proof required for nanoseconds-to-days conversion. |
| Engagement (3161) | P1 remove lifetime running-average and causal burst conclusions from `t_engagement`; N1 blocks certifying `n_engagement/b_teamengage` despite stack-only join. P3 lowest acknowledgement queues only after ratio contract is sound; current topk selects highest shares, not worst. |
| Response time (3167) | P1 `n_mtta/n_mttr/b_ackdist/t_response` visible last-seven-day observed durations, not lifetime; keep finite-tail count instead of saturated p90. N1 for full-group interpretation; histogram observations themselves can stay separately qualified. |
| Ownership (3173) | P1 `b_teamvol` group gauge, not lifetime workload; N1 `n_unowned_all` versus seven-day acknowledged share cannot be causal ownership evidence. P7 reuse canonical named service/team register and retain unattributed rows. |
| Alert flow (3179) | P1 `n_groups/t_state/b_integration/b_service` gauge-state population can fall; slope is not arrivals/closures, remove "only ever rise". `b_am_active` absent OnCall does not prove no recipient. GCI-0097 (generator/ruler/export health) already owns expansion; P3 endpoint action ranking, not new counter math. |

### Commercial - d_commercial:4155 (3)

| Tab | Panel-level recommendation |
|---|---|
| Commitment (4306) | GCI-0094 (deployment-neutral names/text) owns dates/figures cleanup; P7 short stats grouped whole-term versus remaining duration; N2 verify date normalization before interpreting elapsed fractions, do not assume every epoch family uses seconds. |
| Run rate (4308) | GCI-0095 (per-stack showback) and GCI-0096 (cost family panels) own new detail. P1 `n_reconcile` nonzero is not necessarily a newly introduced line (missing series/window/population can also cause it); `b_runrate` may not say every absent line is zero. P6 show breakdown completeness separately from numeric gap. |
| Consumption vs term (4310) | Retain two ratios with no forecast conclusion. P1/N2 titles visibly derived period/currency; absent contract/balance cannot mean zero burn. P7 reduce duplicate balance stat/trend prose, retain useful trend. |

### AI usage - d_ai:4319 (10)

| Tab | Panel-level recommendation |
|---|---|
| Overview (4779) | P1 keep org Assistant gauge distinct from stack memberships and rolling plugin counts; broaden spend-commit-specific caveat to qualified deployment language (not all overage is whole charge). N2 unresolved AI-token reset/identity contracts are not supplied by newer Assistant-org witness. |
| Adoption by stack (4782) | P3 `tbl_stack_users/tbl_stack_tokens` range top100 union can exceed 100: endpoint policy plus bound, or title historical candidates. P5 existing slug drilldown with correct time window. |
| Assistant use per stack (4784) | P7 daily/plugin 30d window visible in every headline; move `n_ai_combos` drift detector below operational summaries. P1 top50 absence cannot imply uncollected (could be below rank); full `tbl_ai_per_stack` is authoritative measured-state lookup. |
| Human vs machine (4796) | P1 non-web is recorded-surface category, not proof a machine rather than human used CLI/Slack; rename to "Assistant surface mix" or visibly qualify Human/Machine inference. Keep uncategorised denominator on this tab, not only prior tab. N4 for true actor attribution. |
| Enablement and configuration (4804) | P1 no tenant objects is tenant-configuration opportunity, not absence of user-scoped effort; `tbl_ai_mcp_failed` empty does not prove every live stack read successfully unless coverage does. P5 retain named auth failures/disabled queues with unknowns. |
| Collection coverage (4815) | P7 separate Agent positive-rate reporting from Assistant credential health (different input, independent availability), retaining 30d maximum not volume. P1 `tbl_ai_coverage` paused/opted-out rows are nonactionable, so empty is not the sole healthy state. |
| Token consumption (4826) | P1 retain top2/top10 concentration only as qualified reported same-source share; separate contract units from memberships. N2 for claimed token monthly reset where corrected roster leaves exact contract unknown. |
| People and identities (4831) | P1 keep service-token category not bot identity; lifetime/start-reset horizon needs N2 proof. P3 exact top100 or historical-candidate title. P5 no email-bearing drilldown URLs or broader export. |
| Commercial (4833) | GCI-0095 (showback) and GCI-0096 (allowance/seats panels) own new cost detail. P1 raw included gauges: reported zero does not prove no allowance or free tokens on every deployment. No arithmetic against plugin rolling users. |
| Feature activity (4840) | P1 `feature_scope` "every stack now carries reader" is contradicted by coverage gaps; say eligible/readable tenant scope. P7 retain product boundaries and self-managed impossibility as concise guidance links; N4 for self-managed split. |

### Dashboard usage - d_dashboards:3192 (6)

| Tab | Panel-level recommendation |
|---|---|
| Adoption (3575) | P1 `n_views` not the only engagement signal (Assistant/surfaces also exist); opens are events, not proof all unique dashboard owners engaged. P7 24h snapshot trend versus 31d inventory link visible; P4 estate headline versus selected per-stack table. |
| Public dashboards (3584) | P5 `tbl_public` safe uid drilldown to Risk inventory with stack/time; preserve top10-per-stack sample and configured/open distinction, no public token. P3 trend changing membership explicit. |
| Query behaviour (3590) | P1 `n_ds` title "Sum of per-stack datasource types queried", not estate distinct types. P7 prioritize high-duration low-cache `tbl_datasource_query_cost` before mix taxonomy; P3 existing cache floor retained for worst stacks. |
| Grafana surfaces (3591) | P1 `surface_scope` generic app/scenes never identifies a particular Drilldown; don't assert all Drilldown is scenes. `n_surface_stacks` prefer labelled multi-series bar/table over anonymous multi-stat. Identity completeness must stay per-surface; N4 per-app/human attribution. |
| What people open (3602) | P5 full `tbl_opening_inventory` opened/unopened/unknown queue first; link safe uid to object only with actual hostname evidence. Keep `tbl_top` bounded candidates, not estate top50. No automatic retirement based on 31d silence. |
| Coverage (3603) | P6 `tbl_coverage` empty means no known failed rows only with fresh successful input; add visible measured denominator/input age. N3 if separate complete 31d inventory versus daily activity coverage needs new publication metadata. |

### Coverage - d_coverage:3613 (13)

| Tab | Panel-level recommendation |
|---|---|
| Observed estate (4053) | P4 selected canonical asset counts versus estate-only live hosts/pods must be visibly separated; P1/N2 object names do not prove host units. P7 put measured atomic population beside selected summaries. |
| Coverage depth (4064) | P7 split score/denominator, identity evidence and registry reach into coherent rows, keep `b_unscored` explanation above score interpretation. P5 link `b_stack_services` to canonical register, not assume equality to bounded retained rows. |
| Synthetic inventory (4080) | P6 `tbl_synthetic_inventory` count-only, opt-in, measured stacks and age together; P5 link to existing test/probe reporting for different L3 question. No extra execution series. |
| SLO inventory (4085) | P6 `tbl_slo_inventory` deserves its own visible input age/coverage, not presumed fresh from general header; use exported provenance if available, else N3. P1 configured burns, not firing/achieved reliability. |
| Adoption opportunities (4089) | GCI-0098 (extend capability populations/call lists) owns new rows. P5 `tbl_adoption_targets` existing named footprint order retained; P1 eligible/provisioned not entitlement or paid waste. Unknown DB marker contract remains N2/N4. |
| Adjacent datasource estate (4097) | P7 useful intentional L2-versus-query comparison; put their different measured populations/windows visibly above side-by-side panels. P5 full `tbl_datasource_inventory` canonical consolidation scope, no guessed vendor use. |
| Adaptive Traces (4103) | P1 `tbl_at_policy` usage-window activity not configured policy inventory; existing `tbl_at_inventory` already exists, remove obsolete "follows release" text. P6 achieved reduction denominator/window and unreadable configuration visibly separate; N2 if exact rate integration normalization is unproven. |
| Outcome value (4115) | P1 rename "Time returned to people" row: MTTA/MTTR are recorded delays, not saved time. N1 engagement cohort mismatch. P7 retain qualified summary with link Operations for action, not duplicate lifetime narrative. |
| Unit economics (4125) | N2 exact product/host-hour/money population contract before publishing implied prices; N1 monthly spend divided by unspecified group gauge/seven-day observations is not operational ROI. P1 show numerator/denominator windows visibly and remove time-saved/value claims. |
| Named service register (4133) | P5 `tbl_services` actual bounded rows retain applicability and unknowns; do not equate OnCall service names to canonical cross-signal identity without evidence. P7 linked live OnCall catalogue is intentional different fidelity, not a merged union. |
| Technology and cluster registers (4137) | P5 exact per-stack evidence links and filterable names; P6 explicit window and truncation/retained counts. No metric-name/title guessing replaces registry evidence. |
| Classification evidence (4141) | P7 developer backlog below operator decisions; `n_metric_backlog/tbl_metrics` not coverage score. P1 legacy Mimir labels never silently become canonical services. |
| Summary (4147) | P6 `tbl_summary` keep registry version and retained rows/denominators at top, publication age visible; P7 avoid repeating large registers here. |

## Shared assembled tabs: the remaining 16

| Dashboard | Findings | How to read this |
|---|---|---|
| Estate | P5/P7: `_fd_idle/_fd_billing/_fd_drift` retain exact conditions, severity distinction and one-click canonical detail; findings counts are estate-wide. | P2/P4: availability/freshness are measured inventory, not assurance every table current; gap rather than connected health line. |
| Cost | P5: `_fd_cardinality` currently whole cardinality register but `SPECS` counts only Worst label values >=5000; filter panel to same condition or title as wider context. Retain full register on Levers. | P6: Adaptive Logs and dataplane separate input ages, dynamic card/period qualification. |
| Usage | P1/P4: `_fd_dormant` is daily inactivity subset, not paid waste; counts global while table selected. | P6/P7: nine optional reader ages should not imply all default-off readers are broken; concise enabled/known/unknown guide, no invented state. |
| Maturity | No Findings tab (SPECS has no pillar D kinds); do not invent one. | P4/P6: score denominator by dimension and estate/selection distinction; freshness not weekly certainty. |
| Risk | P5: add panel-local same-condition detail or canonical links for existing label-confidence, service-account-risk and fast-scrape kinds absent from FINDING_DETAIL. Do not add raw privacy-match detail. P1 shared help's "count of STACKS" is false for kinds counting label/account/pipeline rows. | P6/P7: readable compact source scopes and sensitive-store boundary; per-input provenance needed to qualify private detail, not latest inventory alone. |
| Value | No Findings tab (no pillar F kinds). | P1/P4: currency from rate card, selected tables versus global series, L3 not human value. |
| Operations | No Findings tab (no pillar G kinds). | P1: live datasource consumer 24h window does not change seven-day histogram producer contract; no scan freshness fiction. |
| Commercial | No Findings tab (no pillar H kinds). | P1/N2: visible derived USD/month and unresolved exact period; live names alone not currency proof. |
| AI usage | P5/P1: four existing queues are helpful intentional reuse; `_fd_ai_mcp/_fd_ai_off` measured empty must be qualified by readable population; no email into URLs. | P1: billing versus plugin rolling30d remains distinct; identity/surface categories are not proven human/machine split. |
| Dashboard usage | No Findings tab (no pillar J kinds). | P1/P6: daily 24h activity versus complete31d opening inventory, summed per-stack users not org headcount. |
| Coverage | No Findings tab (no pillar K kinds). | P4/P6: selected collector registers and estate live panels visibly separated; header's datasource-live scope not a fresh-discovery roster. |

## Residual risks and disposition

- Static proposal, not a rendered acceptance: exact tooltip clipping, third-party visual behavior, Grafana transformation ordering and link persistence remain unverified. AST completeness does not prove runtime optional branches.
- Most vendor names have unresolved semantic normalization despite name discovery; priority is honest existing presentation, not adding superficially attractive rates or costs. No new verified name or role is invented here.
- OnCall seven-day/gauge cohort mismatch can invalidate displayed engagement even after wording is fixed. Root should decide N1 before treating those ratios as operational evidence.
- View-specific provenance queries and source-success gating need schema/policy introspection at implementation; if not supported, park N3 rather than approximate them.
- A historical sparse-metric window or a vendor info join is not current inventory completeness. No no-data panel is removed as "dead" on this evidence; source placeholder `b_runrate` is replaced before assembly (4230/4287), so it is not a shipped dead panel.
- Zero new series does not mean zero privacy risk. Identity-bearing tables, public-share identifiers and classified private labels require the existing access/minimization boundaries; proposal adds no data collection or grants.
- Proposal-time status: root recording was outstanding when the lane returned. The root has now recorded this durable document and the admitted tasks below; the read-only lane itself did not write tracker state.

## Root disposition

Admit bounded P1 wording honesty, P2 collector integrity gaps, and P4 visible estate/selection scope after the planned dashboard chain. No new vendor name or series is introduced. P3, P5, P6 and P7 remain owner-priority follow-ups: browser/link/data-schema proof is not assumed. N1-N4 remain owner decisions, not authority to alter older semantic contracts. Existing dashboard wave tasks retain their own scope; no duplicate showback or cost task. Live-name evidence is pending.
