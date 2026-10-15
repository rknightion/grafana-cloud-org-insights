"""D-LAY23 section 2, independently declared display owners.

These offline tests validate the publication contract, NOT rendering. The same declaration exports
seeded runtime cases for the retained JSONata/@grafana/data witness. A column census alone must never
be reported as enum-survival proof. Open upstream vocabularies are deliberately not closed here.
"""
from __future__ import annotations

import json
from pathlib import Path
import unittest

from tests import test_dashboard_layout as layout_contract
from tests.test_dashboard_layout import OPTIONAL, tabs, visible
from tests.test_dashboard_coverage import declared_schemas, placed
from collector import technology_registry
from collector.pillars import coverage as coverage_producer

ROOT = Path(__file__).resolve().parents[1]

# All 47 frozen section-2 rows. Canonical tab spellings come from accepted section 1, not
# the implementation's placement census. FIELD_OWNERS/LIVE_OWNERS below refine the surfaces;
# PROOF_FENCES records obligations this bounded candidate cannot attest.
SECTION2_OWNERS = (
    ("Test leftover class, Created by / Updated by, Idle (days)", "estate", "Leakage"),
    ("Version drift", "estate", "Composition"),
    ("Plan, Provider, Region, Cluster, Status", "estate", "All stacks"),
    ("Scan tier x reason (skipped/failed)", "estate", "Scan health"),
    ("Input x consuming-tier age/availability", "estate", "Data freshness"),
    ("Finding kind x severity", "estate,cost,usage,risk,ai", "Findings"),
    ("Recs pending, Rules applied, Share of org series", "cost", "Levers"),
    ("Worst label, Label values, Label names", "cost", "Levers"),
    ("Adaptive Logs recommendations", "cost", "Adaptive Logs"),
    ("Signal billing usage (series vs volume)", "cost", "Signals"),
    ("Vendor attribution / allowance / DPM / seat families", "cost", "Vendor attribution|Included allowance context|DPM reconciliation|Seat context"),
    ("Last-seen bucket, Stickiness, dormant", "usage", "Engagement"),
    ("Configured-object counts, exact/at_least, reader state", "usage", "Configured inventory"),
    ("OTLP floor", "usage", "Protocol adoption"),
    ("Hosts, pods, containers, log streams", "coverage", "Observed estate"),
    ("Score, Tier, dimension contribution", "maturity", "Leaderboard|Explain a score"),
    ("Unscored reason", "maturity", "Not scored"),
    ("Owner candidates / emails", "maturity", "Who owns what"),
    ("Routing (inherited/missing/builtin), Receiver state", "risk", "Alert routing"),
    ("Retention policy status (compliant/gap/unreadable)", "risk", "Logs retention"),
    ("Retention vs lookback days", "operations", "Logs retention"),
    ("Org role, staff-access state", "risk", "Access"),
    ("Admin share, Admins", "risk", "Access"),
    ("Delete protection", "risk", "Delete protection"),
    ("SA kind, Flag, Token hygiene", "risk", "Credentials"),
    ("Collector active/inactive, FM dead, Faster than default", "risk", "Collectors"),
    ("Discard reason", "risk", "Data loss"),
    ("Label confidence (high/possible)", "risk", "Label cardinality"),
    ("Label privacy class", "risk", "Label privacy risk"),
    ("Public dashboard Enabled (configured)", "risk", "Public dashboards"),
    ("Public opens / anonymous (observed)", "dashboards", "Public dashboards"),
    ("OnCall state, integration, service, team", "operations", "Alert flow|Ownership"),
    ("Response/resolution bands (7d)", "operations", "Response time"),
    ("Run rate by product", "commercial", "Reported billing"),
    ("Assistant users / AI tokens (billing)", "ai", "Overview"),
    ("Assistant category, surface", "ai", "Recorded surfaces"),
    ("Tenant object kind, enabled, authenticationFailed", "ai", "Enablement and configuration"),
    ("Credential coverage", "ai", "Collection coverage"),
    ("Opening State (opened/unopened/unknown)", "dashboards", "Dashboard opening inventory"),
    ("Grafana surface", "dashboards", "Grafana surfaces"),
    ("Datasource types queried", "dashboards", "Query behaviour"),
    ("Plugins provisioned", "usage", "Adoption"),
    ("Service register (Population, Has SLO/alert/dashboard)", "coverage", "Named service register"),
    ("Technology, cluster", "coverage", "Technology and cluster registers"),
    ("Capability populations / opportunities", "coverage", "Adoption opportunities"),
    ("Labelling score, severity, coverage, catalogue version", "labelling", "Stack scorecard"),
    ("Rule result (pass/fail/not evaluated/excluded)", "labelling", "Per-signal rules|Not evaluated and coverage"),
)

# Frozen section-2 rows, not inferred from existing panel columns. Each binding is
# (dashboard, owner tab, element, source fields). Context copies never enter this table.
FIELD_OWNERS = {
    "Test leftover, creator/updater and idle days": [
        ("estate", "Leakage", "idle", ("Test leftover", "Created by", "Updated by", "Idle (days)")),
        ("estate", "Leakage", "billing", ("Test leftover", "Created by", "Updated by", "Idle (days)"))],
    "Version drift": [("estate", "Composition", "drift", ("Version drift",))],
    "Plan/provider/region/cluster/status": [
        ("estate", "All stacks", "estate", ("Plan name", "Provider", "Region", "Cluster", "Status"))],
    "Adaptive Metrics levers": [
        ("cost", "Levers", "headroom", ("Recs pending", "Rules applied", "Share of org series %"))],
    "Cardinality register": [
        ("cost", "Levers", "cardinality", ("Worst label", "Label values", "Label names"))],
    "Adaptive Logs recommendations": [
        ("cost", "Adaptive Logs", "adaptive_logs_recommendations",
         ("Recommendations", "Applied", "Pending", "Pending GB", "Pending GB (unqueried)", "Levels"))],
    "Signal billing usage": [
        ("cost", "Signals", "signals", (" Signal", "Billing usage", "Current usage"))],
    "Last seen/stickiness/dormant": [
        ("usage", "Engagement", "recency", ("Recency", "Last seen (days)")),
        ("usage", "Engagement", "dormant", ("Users (active)", "Users (daily)", "Stickiness"))],
    "Configured objects and count relation": [
        ("usage", "Configured inventory", "library_panels_inventory", ("Configured library panels",)),
        ("usage", "Configured inventory", "playlists_inventory", ("Configured playlists",)),
        ("usage", "Configured inventory", "reports_inventory", ("Configured reports",)),
        ("usage", "Configured inventory", "pdc_networks", ("Configured private networks",)),
        ("usage", "Configured inventory", "cloud_accounts", ("Configured accounts", "Provider")),
        ("usage", "Configured inventory", "ml_jobs", ("Configured forecast jobs",)),
        ("usage", "Configured inventory", "faro_apps",
         ("Configured Faro apps", "Web apps", "Mobile apps", "Unknown type apps")),
        ("usage", "Configured inventory", "irm_integrations", ("Configured IRM integrations",)),
        ("usage", "Configured inventory", "irm_alert_groups", ("IRM alert groups", "Relation", "Population"))],
    "Maturity score/tier/contribution": [
        ("maturity", "Leaderboard", "board", ("Score", "Tier")),
        ("maturity", "Explain a score", "dims", ("Dimension", "Contribution", "Weight", "Applicable"))],
    "Unscored reason": [("maturity", "Not scored", "unscored_detail", ("Unscored reason",))],
    "Owner candidates/emails": [
        ("maturity", "Who owns what", "owners", ("Owner candidates", "Owner emails"))],
    "Routing/receiver state": [
        ("risk", "Alert routing", "alert_routing_findings", ("Routing", "Receiver state"))],
    "Retention policy status": [
        ("risk", "Logs retention", "retention_policy_status", ("Status",))],
    "Org role/staff access": [("risk", "Access", "org_members", ("Role", "Staff access"))],
    "Admin share/admins": [("risk", "Access", "admins", ("Admin share %", "Admins"))],
    "Delete protection": [("risk", "Delete protection", "noprot", ("Delete protection",))],
    "Service-account kind/flag/token hygiene": [
        ("risk", "Credentials", "sa_inventory", ("Kind", "Flag", "Token hygiene"))],
    "Collector state/FM dead/faster than default": [
        ("risk", "Collectors", "fleet", ("Collectors (active)", "Collectors (inactive)", "FM dead")),
        ("risk", "Collectors", "fleet_scrape_intervals", ("Faster than default",))],
    "Label confidence": [("risk", "Label cardinality", "label_cardinality", ("Confidence",))],
    "Label privacy class": [("risk", "Label privacy risk", "risk_label_hygiene", ("Class",))],
    "Configured public-dashboard enabled": [
        ("risk", "Public dashboards", "public_dashboards", ("Enabled",))],
    "Observed public opens": [("dashboards", "Public dashboards", "tbl_public", ("Events",))],
    "Assistant category/surface": [
        ("ai", "Recorded surfaces", "tbl_ai_combo_stack", ("Category", "Surface"))],
    "Tenant object kind/enabled/authenticationFailed": [
        ("ai", "Enablement and configuration", "tbl_ai_tenant", ("kind", "enabled", "authenticationFailed"))],
    "Credential coverage": [("ai", "Collection coverage", "tbl_ai_coverage", ("State", "Actionable"))],
    "Opening state": [("dashboards", "Dashboard opening inventory", "tbl_opening_inventory", ("State",))],
    "Grafana surface": [
        ("dashboards", "Grafana surfaces", "tbl_surface_usage", ("Surface",))],
    "Datasource types queried": [
        ("dashboards", "Query behaviour", "tbl_ds", (" Datasource type",))],
    "Plugins provisioned": [("usage", "Adoption", "plugins", (" Plugin",))],
    "Service register population/evidence": [
        ("coverage", "Named service register", "tbl_services",
         ("Population", "Has SLO", "Has alert", "Has dashboard"))],
    "Technology/cluster": [
        ("coverage", "Technology and cluster registers", "tbl_technologies", ("Technology",)),
        ("coverage", "Technology and cluster registers", "tbl_clusters", ("Cluster",))],
    "Capability population/opportunities": [
        ("coverage", "Adoption opportunities", "tbl_adoption",
         ("Capability", "Population basis", "Population stacks", "Opportunity stacks")),
        ("coverage", "Adoption opportunities", "tbl_adoption_targets", ("Capability", "Opportunity"))],
    "Labelling score/severity/coverage/version": [
        ("labelling", "Stack scorecard", "scorecard", ("Score", "Worst severity", "Coverage", "Catalogue version"))],
    "Rule results": [
        ("labelling", "Per-signal rules", "rules_metrics", ("Result",)),
        ("labelling", "Per-signal rules", "rules_logs", ("Result",)),
        ("labelling", "Per-signal rules", "rules_traces", ("Result",)),
        ("labelling", "Per-signal rules", "rules_profiles", ("Result",)),
        ("labelling", "Not evaluated and coverage", "not_evaluated", ("Result", "Reason")),
        ("labelling", "Not evaluated and coverage", "coverage", ("Signal", "Not evaluated", "Excluded rules"))],
}

# The remaining frozen rows use live metrics, not JSON view fields. Required surfaces are explicit,
# but their PromQL execution proof is separate from the table witness and is not claimed by this test.
LIVE_OWNERS = {
    "Scan tier x skipped/failed reason": ("estate", "Scan health", ("b_failed", "b_skipped")),
    "Input x consuming-tier age/availability": ("estate", "Data freshness", ("t_inputs", "t_input_avail")),
    "Vendor attribution": ("cost", "Vendor attribution", ("context_attr_metrics_active", "context_attr_logs_bytes")),
    "Included allowance": ("cost", "Included allowance context", ("context_allow_metrics", "context_allow_logs")),
    "DPM": ("cost", "DPM reconciliation", ("context_vendor_stack", "context_vendor_org", "context_vendor_divisor")),
    "Seat families": ("cost", "Seat context", ("context_seat_grafana_billable", "context_seat_irm_billable")),
    "OTLP floor": ("usage", "Protocol adoption", ("n_otlp", "n_otlp_floor")),
    "Hosts/pods/containers/log streams": ("coverage", "Observed estate", ("n_hosts", "n_pods", "n_containers", "n_log_streams")),
    "Retention vs lookback": ("operations", "Logs retention", ("_ret_candidate_table",)),
    "Discard reason": ("risk", "Data loss", ("b_reason",)),
    "OnCall state/integration/service/team": ("operations", "Alert flow", ("t_state", "b_integration", "b_service")),
    "OnCall ownership": ("operations", "Ownership", ("b_service_owner",)),
    "Response/resolution bands 7d": ("operations", "Response time", ("b_ackdist", "b_resdist")),
    "Run rate by product": ("commercial", "Reported billing", ("b_runrate",)),
    "Assistant users/AI tokens billing": ("ai", "Overview", ("n_assistant_users", "n_tokens")),
    "Observed anonymous opens": ("dashboards", "Public dashboards", ("n_anon",)),
}

# Literal expectations transcribed from authoritative producers, never display mappings. None is an
# intentional unknown, not another member of a closed enum. Witness each value once, not permutations.
# Producer references are kept beside each domain to make drift reviewable.
ENUMS = {
    ("usage", "recency", "Recency"): ("collector/pillars/usage.py:LAST_SEEN_BUCKETS", ("7d", "30d", "90d", "older", "never")),
    ("usage", "irm_alert_groups", "Relation"): ("collector/sources/irm_alert_groups.py", ("exact", "at_least")),
    ("risk", "org_members", "Staff access"): ("collector/pillars/risk.py:ORG_MEMBER_STAFF_ACCESS_STATES", ("active", "expired", "none", "unknown")),
    ("risk", "label_cardinality", "Confidence"): ("collector/label_cardinality.py", ("high", "possible")),
    ("risk", "retention_policy_status", "Status"): ("collector/pillars/retention.py:build", ("compliant", "below policy", "unreadable")),
    ("maturity", "unscored_detail", "Unscored reason"): ("collector/pillars/maturity.py:eligibility/score_stack", ("paused", "too_few_users", "no_signal_above_floor", "insufficient_rubric_coverage")),
    ("dashboards", "tbl_opening_inventory", "State"): ("collector/pillars/insights.py", ("opened", "unopened", "unknown")),
    ("labelling", "scorecard", "Worst severity"): ("collector/label_rules.py:WEIGHTS", ("low", "medium", "high", None)),
    ("cost", "signals", " Signal"): ("collector/pillars/cost.py:SIGNAL_CURRENT", ("metrics", "logs", "traces", "profiles", "graphite")),
    ("maturity", "board", "Tier"): ("collector/pillars/maturity.py:TIERS/tier_for", ("leading", "solid", "lagging", "dormant", "unscored")),
    ("maturity", "dims", "Dimension"): ("collector/pillars/maturity.py:RUBRIC", ("signal_breadth", "alerting_proportionality", "adaptive_adoption", "engagement", "access_hygiene", "cardinality_discipline", "dashboard_utilisation", "datasource_breadth", "collector_health")),
    ("risk", "alert_routing_findings", "Routing"): ("collector/sources/alert_routing.py:classify", ("inherited", "direct")),
    ("risk", "alert_routing_findings", "Receiver state"): ("collector/sources/alert_routing.py", ("provisioned", "missing", "unverified_builtin", "not_applicable")),
    ("risk", "sa_inventory", "Kind"): ("collector/pillars/risk.py:build", ("extsvc", "custom")),
    ("risk", "risk_label_hygiene", "Class"): ("collector/pii.py:key_classes/value_classes and collector/pii_patterns.json", ("email", "identity", "person_name", "phone", "ip_address", "secret", "sensitive_identifier", "card_like", "jwt")),
    ("ai", "tbl_ai_tenant", "kind"): ("collector/pillars/ai.py:TENANT_KINDS", ("skills", "rules", "automations", "integrations")),
    ("risk", "sa_inventory", "Token hygiene"): ("collector/sources/serviceaccounts.py:record/_enrich_tokens/_unknown_hygiene", ("ok", "skipped_extsvc", "missing_id", "partial_metadata", "token_401", "forbidden_403", "http_error", "transport_error", "truncated")),
    ("coverage", "tbl_technologies", "Technology"): ("collector/technology_registry.py:REGISTRY (versioned producer catalogue)", tuple(entry.name for entry in technology_registry.REGISTRY.entries)),
    ("coverage", "tbl_adoption_targets", "Capability"): ("collector/pillars/coverage.py:ADOPTION_DISPLAY", tuple(coverage_producer.ADOPTION_DISPLAY[key][0] for key in coverage_producer.ADOPTION_CAPABILITIES)),
    ("coverage", "tbl_adoption", "Capability"): ("collector/pillars/coverage.py:ADOPTION_DISPLAY/_footprint_rows", tuple(coverage_producer.ADOPTION_DISPLAY[key][0] for key in coverage_producer.ADOPTION_CAPABILITIES) + ("Adaptive Metrics", "Adaptive Logs", "Adaptive Traces", "Application Observability", "Database Observability", "Application Observability host reporting", "Application Observability org host-hour reporting", "Infrastructure Observability")),
    ("dashboards", "tbl_surface_usage", "Surface"): ("collector/sources/usage_insights.py:SURFACE_VALUES", ("dashboard", "explore", "app_scenes", "assistant", "app", "kubernetes", "unknown", "other")),
    ("coverage", "tbl_services", "Population"): ("collector/pillars/coverage.py:_population", ("application", "platform", "infrastructure_unit")),
    ("coverage", "tbl_services", "Has SLO"): ("collector/pillars/coverage.py:build/_component_state", ("yes", "no", "unscored: product_not_in_use")),
    ("coverage", "tbl_services", "Has alert"): ("collector/pillars/coverage.py:build/_component_state", ("yes", "no", "unscored: product_not_in_use", "unscored: inventory_unavailable")),
    ("coverage", "tbl_services", "Has dashboard"): ("collector/pillars/coverage.py:build/_component_state", ("yes", "no", "unscored: inventory_unavailable", "unscored: evidence_unavailable")),
    **{("labelling", f"rules_{signal}", "Result"): ("collector/label_rules.py:_result", ("pass", "fail", "not_evaluated", "not_applicable"))
       for signal in ("metrics", "logs", "traces", "profiles")},
    ("labelling", "not_evaluated", "Result"): ("collector/label_rules.py:_result; owner filter not_evaluated", ("not_evaluated",)),
}

# A finite display domain is not justified for these fields. They still own and display observations;
# finite seeds are counterexamples, never an assertion of an exhaustive upstream enum inventory.
OPEN_DOMAINS = {
    "Estate All stacks": "Plan, Provider, Region, Cluster and Status are upstream strings, not a closed schema enum.",
    "Risk Access": "Org Role is passed through from the member API; no closed producer validation.",
    "Risk Credentials": "Flag contains counts and joined descriptions, not a closed enum.",
    "AI Recorded surfaces": "Category/Surface in the view preserve unrecognised source strings; bounded metric projections are not the view domain.",
    "Dashboard usage Grafana surfaces": "Raw source strings remain open in tbl_surface_unmapped; the owned Surface column is the closed SURFACE_VALUES projection.",
    "AI tenant booleans": "strip_object does not validate arbitrary upstream JSON. The owner type-checks these two fields in JSONata before formatting; malformed/missing/null display Unknown. This is presentation only, not producer validation.",
    "Reader state and credential coverage": "Hydration can pass an own-unavailable state string through; credential State may contain missing (<reason>). Known cases are not an exhaustive open domain.",
    "Other named registers": "Plugin, datasource type, technology, cluster and identities are discovered, not configured enums.",
}

# Missing fields / honest proof fences: do not manufacture a new producer field or reduce the goal.
PROOF_FENCES = {
    "Finding kind x severity": "The fixed FindingSpec kind->severity mapping is displayed on each Findings count owner; local Prometheus/Grafana processor proof is retained separately, not inferred from placement.",
    "Test leftover class": "Root accepts the existing boolean plus separately labelled idle/billing membership; no richer class is invented.",
    "Live metric owners": "Placement validation below is not PromQL/render proof; the table runtime witness cannot attest live panels or open live domains.",
    "OnCall state": "t_state is an explicitly aggregate gauge; current bounded source cannot establish a distinct per-object state inventory. Existing acknowledgement-share withholding stays intact.",
    "Rule excluded": "Producer Result is pass/fail/not_evaluated/not_applicable. Exclusion is route_parked on a not_evaluated row plus Excluded rules, not a Result enum named excluded.",
    "Routing spelling": "The frozen inherited/missing/builtin wording spans two producer fields: Routing inherited/direct and Receiver state provisioned/missing/unverified_builtin/not_applicable.",
    "Retention spelling": "The producer spells the gap Status below policy, not gap. Source spelling is retained; no new enum value is invented.",
    "Resolution bands 7d": "Root's historical bucket-shape witness and current official producer documentation authorize the existing RES family and 7d window; local seeded Prometheus/Grafana proof is retained separately. No matched acknowledgement cohort or completeness claim.",
}


class FieldOwnershipPublicationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Use the real CLI artifact, including metadata, layout consolidation and identity mapping.
        layout_contract.DashboardLayoutContractTest.setUpClass.__func__(cls)

    def test_full_frozen_owner_table_names_real_non_explanatory_tabs(self):
        self.assertEqual(len(SECTION2_OWNERS), 47)
        self.assertEqual(len({row[0] for row in SECTION2_OWNERS}), 47)
        for field, names, owners in SECTION2_OWNERS:
            for name in names.split(","):
                for owner in owners.split("|"):
                    with self.subTest(field=field, dashboard=name, tab=owner):
                        self.assertIn(owner, tabs(self.documents["gcinsight"][name]))
                        self.assertNotEqual(owner, "How to read this")

    def test_independent_required_fields_are_visible_on_declared_owner_tabs(self):
        for group, bindings in FIELD_OWNERS.items():
            for name, tab, key, fields in bindings:
                with self.subTest(group=group, owner=key):
                    document = self.documents["gcinsight"][name]
                    self.assertIn(key, list(placed(tabs(document)[tab])))
                    selectors = {selector for selector, _alias in visible(document["spec"]["elements"][key])}
                    self.assertTrue(set(fields) <= selectors, (fields, selectors))
                    self.assertNotEqual(tab, "How to read this")

    def test_reader_runtime_availability_is_on_configured_owner_not_just_explanatory_tab(self):
        document = self.documents["gcinsight"]["usage"]
        owner = list(placed(tabs(document)["Configured inventory"]))
        for view in OPTIONAL:
            with self.subTest(reader=view):
                self.assertIn(f"_meta_{view}", owner)
                fields = {selector for selector, _alias in visible(document["spec"]["elements"][f"_meta_{view}"])}
                self.assertTrue({"input", "availability", "input_state", "measurement", "age_now"} <= fields)

    def test_live_owner_placements_are_not_claimed_as_runtime_evidence(self):
        for group, (name, tab, keys) in LIVE_OWNERS.items():
            with self.subTest(group=group):
                document = self.documents["gcinsight"][name]
                self.assertTrue(set(keys) <= set(placed(tabs(document)[tab])))
                self.assertIn("Live metric owners", PROOF_FENCES)

    def test_named_aggregate_exemptions_are_honestly_titled(self):
        for name, document in self.documents["gcinsight"].items():
            keys = {"_findings_now", "b_leftover", "b_recency", "t_state"}
            if "Overview" in tabs(document):
                keys.update(key for key in placed(tabs(document)["Overview"])
                            if document["spec"]["elements"][key]["spec"]["vizConfig"]["group"] == "stat"
                            and key not in {"_coverage", "_freshness"} and not key.startswith("_age_"))
            for key in keys & document["spec"]["elements"].keys():
                with self.subTest(dashboard=name, aggregate=key):
                    self.assertIn("aggregate", document["spec"]["elements"][key]["spec"]["title"].lower())

    def test_finding_severity_is_owned_without_guessing_shared_view_variants(self):
        from collector.pillars.findings import SPECS
        by_kind = {}
        for spec in SPECS:
            by_kind.setdefault(spec.kind, set()).add(spec.severity)
        self.assertTrue(all(len(values) == 1 for values in by_kind.values()))
        self.assertEqual(by_kind["label_cardinality_high_confidence"], {"high"})
        self.assertEqual(by_kind["label_cardinality_possible"], {"info"})
        for name in ("estate", "cost", "usage", "risk", "ai"):
            doc = self.documents["gcinsight"][name]
            self.assertIn("_findings_now", list(placed(tabs(doc)["Findings"])))
            panel = doc["spec"]["elements"]["_findings_now"]["spec"]
            overrides = panel["vizConfig"]["spec"]["fieldConfig"]["overrides"]
            mappings = [p["value"] for override in overrides
                        if override["matcher"] == {"id": "byName", "options": "Field"}
                        for p in override["properties"] if p["id"] == "mappings"]
            self.assertEqual(len(mappings), 1, name)
            options = mappings[0][0]["options"]
            for kind, severities in by_kind.items():
                self.assertEqual(options[kind]["text"], f"{kind} [severity: {next(iter(severities))}]")
            self.assertEqual(set(options), set(by_kind))

    def test_resolution_bands_have_a_separate_qualified_owner(self):
        document = self.documents["gcinsight"]["operations"]
        self.assertIn("b_resdist", list(placed(tabs(document)["Response time"])))
        panel = document["spec"]["elements"]["b_resdist"]["spec"]
        queries = panel["data"]["spec"]["queries"]
        self.assertEqual(len(queries), 5)
        for query in queries:
            expr = query["spec"]["query"]["spec"]["expr"]
            self.assertIn("grafanacloud_oncall_instance_alert_groups_resolution_time_seconds_bucket", expr)
            self.assertNotIn("increase(", expr)
            self.assertNotIn("or vector(0)", expr)
        self.assertIn("not a matched acknowledgement cohort", panel["description"])

    def test_finding_ambiguous_same_kind_severity_refuses_presentation(self):
        from dataclasses import replace
        from unittest.mock import patch
        from collector.dashboards import layout
        from collector.pillars.findings import SPECS
        with patch.object(layout.findings, "SPECS", (SPECS[0], replace(SPECS[0], severity="info"))):
            with self.assertRaisesRegex(ValueError, "ambiguous severity"):
                layout.apply("value", {"_findings_now": {}}, [], [])

    def test_tenant_boolean_presentation_is_type_checked_before_formatting(self):
        panel = self.documents["gcinsight"]["ai"]["spec"]["elements"]["tbl_ai_tenant"]["spec"]
        query = panel["data"]["spec"]["queries"][0]["spec"]["query"]["spec"]
        self.assertEqual(query["root_selector"],
                         'rows ~> |$|{"enabled": $type(enabled) = "boolean" ? enabled : null, '
                         '"authenticationFailed": $type(authenticationFailed) = "boolean" ? authenticationFailed : null}|')
        for field in ("enabled", "authenticationFailed"):
            self.assertEqual(next(c["type"] for c in query["columns"] if c["selector"] == field), "boolean")
            self.assertIn({"matcher": {"id": "byName", "options": field},
                           "properties": [{"id": "noValue", "value": "Unknown"}]},
                          panel["vizConfig"]["spec"]["fieldConfig"]["overrides"])

    def test_boolean_projection_whitelist_refuses_other_transforms(self):
        from tests.test_dashboard_coverage import presentation_root
        panel = self.documents["gcinsight"]["ai"]["spec"]["elements"]["tbl_ai_tenant"]["spec"]
        selector = panel["data"]["spec"]["queries"][0]["spec"]["query"]["spec"]["root_selector"]
        self.assertEqual(presentation_root(selector), "rows")
        for mutation in (selector.replace('"enabled":', '"fabricated":'),
                         selector.replace('enabled : null', 'true : false'),
                         selector + '[enabled = true]'):
            self.assertNotEqual(presentation_root(mutation), "rows")

    def test_recency_domain_is_independent_of_the_display(self):
        from collector.pillars.usage import LAST_SEEN_BUCKETS
        self.assertEqual(LAST_SEEN_BUCKETS, ENUMS[("usage", "recency", "Recency")][1])


def runtime_cases(documents):
    """Export meaningful runtime-only copies, leaving committed fixtures untouched.

    Preserve supporting columns from the synthetic row to exercise actual projections, predicates,
    sort and formatters. Override only the independently required field under observation. The witness
    compares each final cell with its seeded source cell, including numeric units and unknown blanks.
    """
    schemas = declared_schemas()
    cases = []
    for group, bindings in FIELD_OWNERS.items():
        for name, tab, key, fields in bindings:
            panel = documents[name]["spec"]["elements"][key]["spec"]
            query = panel["data"]["spec"]["queries"][0]["spec"]["query"]["spec"]
            view = query["url"].rsplit("/", 1)[-1].removesuffix(".json")
            payload = json.loads((ROOT / "testdata/views" / f"{view}.json").read_text())
            template = dict((payload.get("rows") or [{}])[0])
            for field, kind in schemas.get(view, ()):
                template.setdefault(field, {"string": "synthetic-observation", "number": 17, "boolean": True}.get(kind))
            for field in fields:
                selector = next(c for c in query["columns"] if c["selector"] == field)
                domain = ENUMS.get((name, key, field))
                values = domain[1] if domain else {
                    "number": (0, 17, None), "boolean": (True, False, None),
                    "string": ('unrecognised \"quoted\" / ? & = observation', "Unrecognised 雪 <observation>", None),
                }[selector["type"]]
                rows = []
                for index, value in enumerate(values):
                    row = {**template, field: value}
                    # Matching identity is supporting context, never linked by value.
                    if " Stack" in row:
                        row[" Stack"] = f"synthetic-{index}"
                    if "Stack" in row:
                        row["Stack"] = f"synthetic-{index}"
                    if key == "not_evaluated":
                        row["Result"] = "not_evaluated"
                    if key.startswith("rules_"):
                        row["Signal"] = key.removeprefix("rules_")
                    rows.append(row)
                cases.append({"group": group, "dashboard": name, "tab": tab, "key": key,
                              "field": field, "query": query, "panel": panel,
                              "payload": {**payload, "rows": rows}, "values": values,
                              "closed": domain is not None,
                              "producer": domain[0] if domain else "open/numeric/boolean field observations"})
    # Raw publication states must not collapse into the availability summary. Healthy provenance
    # may lack a state; do not invent "available" or "disabled" in that missing field.
    for view in OPTIONAL:
        panel = documents["usage"]["spec"]["elements"][f"_meta_{view}"]["spec"]
        query = panel["data"]["spec"]["queries"][0]["spec"]["query"]["spec"]
        for state in ("disabled", "partial", "unavailable", "incompatible_schema", "future_timestamp",
                      "upstream-unrecognised-a", "upstream-unrecognised-b", None):
            provenance = {"available": state is None, "stale": False, "age_seconds": 17}
            if state is not None:
                provenance["state"] = state
            payload = {"meta": {"generated_at": "2020-01-02T00:00:00Z", "inputs": {view: provenance}}, "rows": []}
            cases.append({"group": "Reader publication state", "dashboard": "usage", "tab": "Configured inventory",
                          "key": f"_meta_{view}", "field": "input_state", "query": query,
                          "panel": panel, "payload": payload, "values": [state], "closed": False,
                          "producer": "collector/emit/hydrate.py:hydrate (known explicit states; open own-unavailable strings)"})
    return cases


if __name__ == "__main__":
    import sys
    if len(sys.argv) == 3 and sys.argv[1] == "--runtime-cases":
        directory = Path(sys.argv[2])
        documents = {name.removeprefix("gcinsight-"): json.loads(path.read_text())
                     for path in directory.glob("gcinsight-*.json") for name in (path.stem,)}
        print(json.dumps(runtime_cases(documents)))
    else:
        unittest.main()
