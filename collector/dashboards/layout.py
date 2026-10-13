"""Approved assembled-layout and register-survival seam (D-LAY23).

Only presentation changes live here. Sources, units, labels and schema contracts stay in existing
builders; canonical links are resolved from final assembled documents by the caller. The tenant
boolean projection below prevents malformed source JSON from becoming a boolean display claim.
"""
from __future__ import annotations

from copy import deepcopy
import json

from collector import label_rules
from collector.dashboards import build
from collector.pillars import findings

TAB_ORDER = {
    "estate": "Overview|Findings|Leakage|Change|Scan health|Data freshness|Composition|All stacks|How to read this",
    "cost": "Overview|Findings|Savings available|Levers|Adaptive Logs|Biggest stacks|Signals|DPM-aware savings|DPM reconciliation|Vendor attribution|Included allowance context|Seat context|How to read this",
    "usage": "Overview|Findings|Engagement|Unread telemetry|Adoption|Protocol adoption|Workload|Configured inventory|Bounded producers and configured alerting|How to read this",
    "maturity": "Overview|Leaderboard|Explain a score|Not scored|By dimension|Who owns what|How it is scored|How to read this",
    "risk": "Overview|Findings|Data loss|Alerting health|Alert routing|Delete protection|Access|Credentials|Collectors|Public dashboards|Logs retention|Label cardinality|Label privacy risk|Per stack|How to read this",
    "value": "Overview|Savings|Capability gaps|Adoption|Test and probe adoption|Capability flags|Benchmarks|How to read this",
    "operations": "Alert flow|Logs retention|Backend health|Response time|Ownership|Engagement|How to read this",
    "commercial": "Commitment|Run rate|Consumption vs term|How to read this",
    "ai": "Overview|Findings|Enablement and configuration|Assistant use per stack|Adoption by stack|Token consumption|Commercial|Human vs machine|People and identities|Collection coverage|Feature activity|How to read this",
    "dashboards": "Adoption|What people open|Query behaviour|Public dashboards|Grafana surfaces|Coverage|How to read this",
    "coverage": "Observed estate|Adoption opportunities|Coverage depth|Named service register|Technology and cluster registers|Adjacent datasource estate|Adaptive Traces|Synthetic inventory|SLO inventory|Outcome value|Unit economics|Summary|Classification evidence|How to read this",
    "labelling": "Estate overview|Per-signal rules|Stack scorecard|Cross-signal consistency|Label register|Not evaluated and coverage|How to read this",
}

REGISTER_OWNERS = {
    "estate": {"_fd_idle": "idle", "_fd_billing": "billing", "_fd_drift": "drift"},
    "cost": {"_fd_headroom": "headroom", "_fd_cardinality": "cardinality"},
    "usage": {"_fd_dormant": "dormant"},
    "risk": {"_fd_admins": "admins", "_fd_noprot": "noprot", "_fd_fleet": "fleet",
             "_fd_plugins": "plugindrift", "_fd_label_high": "label_cardinality",
             "_fd_label_possible": "label_cardinality", "_fd_sa": "sa_inventory",
             "_fd_fast": "fleet_scrape_intervals"},
    "ai": {"_fd_ai_gap": "tbl_ai_gap", "_fd_ai_tokens": "tbl_ai_outliers",
           "_fd_ai_mcp": "tbl_ai_mcp_failed", "_fd_ai_off": "tbl_ai_disabled"},
}

# Actual reader rows on the accepted base. Optional absence stays a build observation, never a
# missing-object query or an inferred disabled reader. Bounded producer readers keep their own tab.
CONFIGURED_READERS = (
    ("Configured library panels", "library_panels_inventory"),
    ("Configured playlists", "playlists_inventory"),
    ("Configured reports", "reports_inventory"),
    ("Configured PDC private networks", "pdc_networks"),
    ("Configured AWS accounts", "cloud_accounts"),
    ("Configured forecast jobs", "ml_jobs"),
    ("Configured Faro apps", "faro_apps"),
    ("Configured IRM integrations", "irm_integrations"),
    ("IRM alert groups", "irm_alert_groups"),
)



# These endpoints are conditional on publication in d_risk. Missing required endpoints still fail.
OPTIONAL_PANELS = frozenset({
    ("risk", "label_cardinality"), ("risk", "fleet_scrape_intervals"),
    ("risk", "public_dashboards"), ("risk", "retention_policy_status"),
})
OPTIONAL_REGISTER_DETAILS = {
    ("risk", "_fd_label_high"): "label_cardinality",
    ("risk", "_fd_label_possible"): "label_cardinality",
    ("risk", "_fd_fast"): "fleet_scrape_intervals",
}


DETAIL_KINDS = {"_fd_label_high": "label_cardinality_high_confidence",
                "_fd_label_possible": "label_cardinality_possible", "_fd_sa": "service_account_risk",
                "_fd_fast": "fleet_fast_scrape"}
ROW_LINKS = {
    "maturity": {"board": ("Stack", [("maturity", "dims", "Explain this score"),
                                      ("maturity", "owners", "Ownership candidates")])},
    "estate": {"estate": ("Stack", [("risk", "risk", "Stack risks"),
                                    ("maturity", "dims", "Explain this score"),
                                    ("cost", "cost", "Largest series stacks")])},
    "operations": {"_ret_candidate_table": ("Stack", [("risk", "retention_policy_status", "Retention policy observation")])},
    "ai": {"tbl_stack_users": ("Stack", [("ai", "tbl_ai_per_stack", "Assistant observations")]),
           "tbl_stack_tokens": ("Stack", [("ai", "tbl_ai_per_stack", "Assistant observations")])},
    "risk": {"public_dashboards": ("Stack", [("dashboards", "tbl_public", "Observed public opens")])},
    "dashboards": {"tbl_public": ("Stack", [("risk", "public_dashboards", "Configured public dashboards")])},
}


def _split_identity(panel, field):
    """Keep linked and unlinked rows in native separate datasets, never drop unknown identity."""
    for query in _data(panel)["queries"]:
        inner = query["spec"]["query"]
        if inner["group"] != build.INFINITY_TYPE:
            continue
        spec = inner["spec"]
        identity = next(c["selector"] for c in spec["columns"] if c["text"] == field)
        if identity not in {" Stack", "Stack", "stack"}:
            raise ValueError("Row links require an existing stack identity column")
        key = json.dumps(identity)
        value = f'$lookup($, {key})'
        spec["root_selector"] += (
            f' ~> |$|{{{key}: $type({value}) = "string" ? {value} : null}}|')
    aliases = {}
    for transform in _data(panel)["transformations"]:
        if transform["spec"]["id"] == "organize":
            aliases.update(transform["spec"]["options"].get("renameByName", {}))
    raw_field = next((raw for raw, display in aliases.items() if display == field), field)
    config = panel["spec"]["vizConfig"]["spec"]["fieldConfig"]
    for override in config["overrides"]:
        matcher = override["matcher"]
        if matcher["id"] == "byName":
            matcher["options"] = next((raw for raw, display in aliases.items()
                                       if display == matcher["options"]), matcher["options"])
    # Partition names label datasets, not table columns. Restore original display aliases and
    # match original field names so existing day/ratio units survive partition's cache naming.
    displays = {c["text"]: c["text"] for q in _data(panel)["queries"]
                for c in q["spec"]["query"]["spec"].get("columns", [])}
    displays.update(aliases)
    config["overrides"].extend({"matcher": {"id": "byName", "options": raw},
                               "properties": [{"id": "displayName", "value": display}]}
                              for raw, display in displays.items())
    # All panels reach one table frame before this seam. Copy the raw identity with a
    # row reducer, convert only that temporary copy to presence, then partition once.
    # Fetching the source twice could observe different snapshots and lose/duplicate rows.
    _data(panel)["transformations"].extend([
        {"kind": "calculateField", "spec": {"id": "calculateField", "options": {
            "mode": "reduceRow", "timeSeries": False, "alias": "Stack links available",
            "reduce": {"reducer": "first", "include": [field]},
        }}},
        {"kind": "convertFieldType", "spec": {"id": "convertFieldType", "options": {
            "conversions": [{"targetField": "Stack links available", "destinationType": "boolean"}],
        }}},
        {"kind": "partitionByValues", "spec": {"id": "partitionByValues", "options": {
            "fields": ["Stack links available"], "keepFields": False,
            "naming": {"asLabels": True},
        }}},
    ])
    panel["spec"]["description"] += (
        " The table dataset selector uses the Stack links available=true/false presentation label: "
        "true rows have a stack identity (linked); false rows are without "
        "one (unlinked); both datasets retain their rows. Row links use only the existing stack slug "
        "and selected time, replacing the current Stack selection.")
    return raw_field


def _data(panel):
    return panel["spec"]["data"]["spec"]


def _organize(panel):
    return next(t["spec"]["options"] for t in _data(panel)["transformations"]
                if t["spec"]["id"] == "organize")


def _columns(panel):
    return _data(panel)["queries"][0]["spec"]["query"]["spec"]["columns"]


def _show(panel, order):
    options = _organize(panel)
    options["indexByName"] = {column: index for index, column in enumerate(order)}
    options["excludeByName"] = {c["text"]: True for c in _columns(panel) if c["text"] not in order}
    options["renameByName"] = {k: v for k, v in options["renameByName"].items() if k in order}


def _widen(owner, duplicate):
    """Union source selectors AND presentation aliases, keeping the owner's existing column order."""
    columns = _columns(owner)
    existing = {c["selector"]: c for c in columns}
    for column in _columns(duplicate):
        if column["selector"] in existing:
            if existing[column["selector"]] != column:
                raise ValueError("Consolidated register has incompatible source/display column contracts")
        else:
            columns.append(deepcopy(column))
    options = _organize(owner)
    for column, alias in _organize(duplicate)["renameByName"].items():
        if column in options["renameByName"] and options["renameByName"][column] != alias:
            raise ValueError("Consolidated register has incompatible presentation aliases")
        options["renameByName"][column] = alias
    order = list(options["indexByName"])
    order.extend(c["text"] for c in columns if c["text"] not in order)
    _show(owner, order)
    # Preserve units/widths from both displays; widening must not turn qualified ratios into counts.
    overrides = owner["spec"]["vizConfig"]["spec"]["fieldConfig"]["overrides"]
    for override in duplicate["spec"]["vizConfig"]["spec"]["fieldConfig"]["overrides"]:
        if override not in overrides:
            overrides.append(deepcopy(override))


def _filter(panel, filters):
    """Grafana's native field predicates, after Infinity parses the existing source columns."""
    _data(panel)["transformations"].insert(0, {"kind": "filterByValue", "spec": {
        "id": "filterByValue", "options": {"type": "include", "match": "all", "filters": filters},
    }})


def apply(name, elements, tabs, detail):
    """Change only approved placements/copies, returning pending static canonical destinations."""
    links = {}
    active_registers = {evidence: owner for evidence, owner in REGISTER_OWNERS.get(name, {}).items()
                        if owner in elements or (name, owner) not in OPTIONAL_PANELS}
    for evidence, owner in active_registers.items():
        _widen(elements[owner], elements[evidence])
        entry = next(entry for entry in detail if entry[0] == evidence)
        spec = next(spec for spec in findings.SPECS if spec.kind == DETAIL_KINDS.get(evidence)
                    or (evidence not in DETAIL_KINDS and spec.view == entry[2]))
        panel = elements[evidence]
        order = [c["text"] for c in _columns(panel)]
        if spec.fields:
            order = ["Stack", *spec.fields]
        _show(panel, order)
        # Filter source JSON before typed frame conversion can coerce a malformed value.
        # Python truthiness treats nonempty containers as true even if their members are false.
        predicates = []
        for field in spec.require:
            value = f'$lookup($, {json.dumps(field)})'
            predicates.append(f'($type({value}) = "array" ? $count({value}) > 0 : '
                              f'$type({value}) = "object" ? $count($keys({value})) > 0 : $boolean({value}))')
        for field, floor in spec.at_least:
            value = f'$lookup($, {json.dumps(field)})'
            predicates.append(f'(($type({value}) = "number" or $type({value}) = "boolean") '
                              f'and $number({value}) >= {floor})')
        for field, value in spec.equals:
            predicates.append(f'$lookup($, {json.dumps(field)}) = {json.dumps(value)}')
        if predicates:
            _data(panel)["queries"][0]["spec"]["query"]["spec"]["root_selector"] = (
                'rows[' + ' and '.join(predicates) + ']')
        panel["spec"]["description"] += (
            " FindingSpec evidence only; canonical full detail is linked below. "
            "The source is already condition-matched unless a field predicate is declared here.")
        links[evidence] = [(name, owner, "Canonical full register")]

    if "_findings_now" in elements:
        # The metric intentionally has no severity label. Use only the fixed producer kind
        # contract, never a view->severity guess (the cardinality view has two severities).
        severities = {}
        for spec in findings.SPECS:
            if spec.kind in severities and severities[spec.kind] != spec.severity:
                raise ValueError("Finding kind has ambiguous severity; cannot present a fixed severity")
            severities[spec.kind] = spec.severity
        panel = elements["_findings_now"]["spec"]
        panel["vizConfig"]["spec"]["fieldConfig"]["overrides"].append({
            "matcher": {"id": "byName", "options": "Field"},
            "properties": [{"id": "mappings", "value": [{"type": "value", "options": {
                kind: {"text": f"{kind} [severity: {severity}]"}
                for kind, severity in severities.items()
            }}]}],
        })
        panel["title"] += " and fixed severity"
        panel["description"] += (
            " Severity is the deterministic FindingSpec classification of each kind, not a new "
            "metric label or a per-row judgement. Unknown kinds remain verbatim; no severity is guessed.")

    by_title = {tab["spec"]["title"]: tab for tab in tabs}

    def grid(title, keys):
        old = by_title[title]["spec"]["layout"]
        old["spec"]["items"] = build.auto_grid(keys)["spec"]["items"]

    def link_panel(key, title, destinations, description=""):
        elements[key] = build.text_panel(title, description or
            "The canonical registers retain the source values and qualifications. Open the linked "
            "panels with the selected time and Stack context; these live-source observations remain "
            "estate-wide where their own contracts say so.")
        links[key] = destinations

    if name == "estate":
        grid("Leakage", ["billing", "idle", "b_leftover"])
        layout = by_title["Scan health"]["spec"]["layout"]["spec"]
        items = layout["items"]
        layout["items"] = sorted(items, key=lambda item: item["spec"]["element"]["name"] != "b_failed")
    elif name == "usage":
        rows = [build.row("Configured footprint summary", ["n_types", "_optional_view_state"], max_columns=2)]
        for title, view in CONFIGURED_READERS:
            original = by_title.pop(title, None)
            if original is not None:
                row = original["spec"]["layout"]["spec"]["rows"][0]
                row["spec"]["layout"] = build.auto_grid([view, f"_age_{view}"], max_columns=2)
                rows.append(row)
                # Reader availability belongs beside its configured inventory, not solely in HtR.
                # Reuse the runtime metadata element: no new source, build-time state or missing URL.
                if f"_meta_{view}" in elements:
                    rows.append(build.row(f"{title}: publication and input state",
                                          [f"_meta_{view}"], max_columns=1, row_height="tall"))
        by_title["Configured inventory"] = build.rows_tab("Configured inventory", rows)
        workload = by_title["Workload"]["spec"]["layout"]["spec"]["rows"]
        workload[0]["spec"]["layout"] = build.auto_grid(["n_intseries", "n_intshare"], max_columns=2,
                                                         row_height="short")
        link_panel("_canonical_workload", "Canonical workload quantities: Coverage", [
            ("coverage", "n_pods", "Kubernetes pod-info quantity"),
            ("coverage", "n_hosts", "Node uname-info quantity")])
        workload.insert(1, build.row("Canonical workload quantities", ["_canonical_workload"], max_columns=1))
        link_panel("_canonical_ai", "Canonical Assistant and token quantities: AI", [
            ("ai", "n_assistant_users", "Assistant users"), ("ai", "n_tokens", "AI token billing-period quantity")])
        workload[-1]["spec"]["layout"] = build.auto_grid(["_canonical_ai"], max_columns=1, row_height="short")
        for key in ("n_pods", "n_hosts", "n_assistant", "n_aitokens"):
            del elements[key]
    elif name == "ai":
        # Legends are presentation, not identity: a missing slug can fall back to stack_id.
        # These queries are instant. Native label extraction retains typed missing cells;
        # reducing labels per series can create ragged columns when some labels are absent.
        for key, value_name in (("tbl_stack_users", "Active users"), ("tbl_stack_tokens", "AI tokens")):
            _data(elements[key])["transformations"] = [
                {"kind": "labelsToFields", "spec": {"id": "labelsToFields", "options": {"mode": "columns"}}},
                {"kind": "merge", "spec": {"id": "merge", "options": {}}},
                {"kind": "sortBy", "spec": {"id": "sortBy", "options": {
                    "sort": [{"field": "Value", "desc": True}],
                }}},
                {"kind": "organize", "spec": {"id": "organize", "options": {
                    "indexByName": {"slug": 0, "stack_id": 1, "Value": 2},
                    "excludeByName": {"Time": True, "__name__": True},
                    "renameByName": {"slug": "Stack", "stack_id": "Stack ID", "Value": value_name},
                }}},
                {"kind": "limit", "spec": {"id": "limit", "options": {"limitField": 100}}},
            ]
        # Presentation only: Grafana's boolean formatter coerces numbers to True/False and can
        # display arrays as blank. Check the source JSON type in JSONata, before frame conversion.
        # Preserve real booleans; missing/null/malformed values stay unknown, never disabled.
        panel = elements["tbl_ai_tenant"]
        query = _data(panel)["queries"][0]["spec"]["query"]["spec"]
        query["root_selector"] = (
            'rows ~> |$|{"enabled": $type(enabled) = "boolean" ? enabled : null, '
            '"authenticationFailed": $type(authenticationFailed) = "boolean" ? authenticationFailed : null}|')
        for column in _columns(panel):
            if column["selector"] in ("enabled", "authenticationFailed"):
                column["type"] = "boolean"
                panel["spec"]["vizConfig"]["spec"]["fieldConfig"]["overrides"].append({
                    "matcher": {"id": "byName", "options": column["text"]},
                    "properties": [{"id": "noValue", "value": "Unknown"}],
                })
        panel["spec"]["description"] += (
            " Boolean cells show Unknown for missing, null or non-boolean source JSON. "
            "This is a display projection, not producer validation or a claim that the source is healthy.")
    elif name == "maturity":
        grid("Leaderboard", ["b_bottom", "b_top", "board"])
        _widen(elements["board"], elements["unscored_detail"])
        _filter(elements["unscored_detail"], [
            {"fieldName": "Unscored reason", "config": {"id": "isNotNull", "options": {}}},
            {"fieldName": "Unscored reason", "config": {"id": "notEqual", "options": {"value": ""}}},
        ])
        elements["unscored_detail"]["spec"]["description"] += " Only nonempty Unscored reason rows are shown."
        links["unscored_detail"] = [("maturity", "board", "Canonical leaderboard and full score fields")]
    elif name == "value":
        rows = by_title["Benchmarks"]["spec"]["layout"]["spec"]["rows"]
        keys = [item["spec"]["element"]["name"] for row in rows[2:]
                for item in row["spec"]["layout"]["spec"]["items"]]
        rows[2:] = [build.row("Benchmark trends: separate populations and units", keys, max_columns=2)]
    elif name == "operations":
        grid("Alert flow", ["n_state_history_failures", "b_state_history_failures", "n_groups", "n_notified",
                            "b_integration", "b_service", "t_state", "b_am_active"])
    elif name == "commercial":
        by_title["Commitment"] = build.rows_tab("Commitment", [
            build.row("Consumed share and term elapsed", ["n_consumed_share", "n_term_elapsed"], max_columns=2, row_height="short"),
            build.row("Raw commitment quantities", ["n_commit", "n_consumed", "n_balance"], max_columns=3, row_height="short"),
            build.row("Separate months diagnostics", ["n_months_metric", "n_months_contract"], max_columns=2, row_height="short"),
        ])
        by_title["Run rate"] = build.rows_tab("Run rate", [
            build.row("Raw total and reconciliation diagnostic", ["n_runrate", "n_reconcile"], max_columns=2, row_height="short"),
            build.row("Products and trends", ["b_runrate", "t_runrate", "t_metrics_share"], max_columns=2),
        ])
    elif name == "dashboards":
        rows = by_title["Query behaviour"]["spec"]["layout"]["spec"]["rows"]
        rows.sort(key=lambda row: not any(item["spec"]["element"]["name"] == "tbl_datasource_query_cost"
                                        for item in row["spec"]["layout"]["spec"]["items"]))
    elif name == "coverage":
        link_panel("_canonical_operations_outcome", "Canonical response and ownership: Operations", [
            ("operations", "n_engaged", "Recorded acknowledgement observations (7d)"),
            ("operations", "n_engagement", "Acknowledgement share withheld, not zero"),
            ("operations", "n_tail", "Acknowledgement observations over an hour (7d)"),
            ("operations", "n_unowned_all", "No-team gauge share (timing stacks)"),
            ("operations", "n_unowned_svc", "No-service gauge share (timing stacks)"),
        ])
        by_title["Outcome value"] = build.rows_tab("Outcome value", [
            build.row("Recorded observations, not saved operator time", ["outcome_scope"], max_columns=1, row_height="short"),
            build.row("Qualified gauge and recorded median delays", ["n_value_groups", "n_value_mtta", "n_value_mttr"], max_columns=3, row_height="short"),
            build.row("Canonical Operations detail", ["_canonical_operations_outcome"], max_columns=1),
        ])
        link_panel("_canonical_operations_ownership", "Canonical OnCall ownership: Operations", [
            ("operations", "b_service_owner", "Observed services and their owning teams")])
        rows = by_title["Named service register"]["spec"]["layout"]["spec"]["rows"]
        rows[1]["spec"]["layout"] = build.auto_grid(["_canonical_operations_ownership"], max_columns=1)
        for key in ("n_value_acknowledged", "n_value_engagement", "n_value_tail", "n_value_unowned_team",
                    "n_value_unowned_service", "b_oncall"):
            del elements[key]
        for key, target, owner in (("tbl_datasource_provisioned", "usage", "plugins"),
                                   ("tbl_datasource_queried", "dashboards", "tbl_ds")):
            elements[key]["spec"]["title"] += " - deliberate comparison copy"
            links[key] = [(target, owner, f"canonical: {target} register")]
    elif name == "labelling":
        links["register"] = [("risk", "label_cardinality", "Mimir top-20 label-name findings (Risk)"),
                             ("cost", "cardinality", "Cardinality outliers (Cost)")]
        if elements["overview"]["spec"]["vizConfig"]["group"] == "table":
            _widen(elements["scorecard"], elements["overview"])
        weights = json.dumps(label_rules.WEIGHTS, separators=(",", ":"))
        for key in ("overview", *(f"rules_{signal}" for signal in ("metrics", "logs", "traces", "profiles"))):
            if elements[key]["spec"]["vizConfig"]["group"] != "table":
                continue
            query = _data(elements[key])["queries"][0]["spec"]["query"]["spec"]
            if key == "overview":
                query["root_selector"] = f'rows^(>$lookup({weights}, `Worst severity`), <Score)'
            else:
                query["root_selector"] = f'rows^(>(Result = "fail" ? 1 : 0), >$lookup({weights}, Severity))'
    # These named headlines deliberately collapse dimensions. Declare the aggregation honestly;
    # context copies and explanatory tabs do not thereby acquire field/enum ownership.
    aggregate_keys = {"_findings_now", "b_leftover", "b_recency", "t_state"}
    if "Overview" in by_title:
        def overview_elements(value):
            if isinstance(value, dict):
                if value.get("kind") == "ElementReference":
                    yield value["name"]
                for child in value.values():
                    yield from overview_elements(child)
            elif isinstance(value, list):
                for child in value:
                    yield from overview_elements(child)
        aggregate_keys.update(key for key in overview_elements(by_title["Overview"])
                              if elements[key]["spec"]["vizConfig"]["group"] == "stat")
    for key in aggregate_keys & elements.keys():
        elements[key]["spec"]["title"] += " - aggregate"
    expected = TAB_ORDER[name].split("|")
    unknown = set(by_title) - set(expected)
    if unknown:
        raise ValueError(f"Unapproved tab deletion: {sorted(unknown)}")
    row_links = {key: ("Stack", destinations) for key, destinations in links.items()
                 if key in active_registers}
    row_links.update({key: value for key, value in ROW_LINKS.get(name, {}).items()
                      if key in elements or (name, key) not in OPTIONAL_PANELS})
    for key, (field, destinations) in row_links.items():
        # Target discovery also resolves row destinations, independently of static panel links.
        links.setdefault(key, []).extend(d for d in destinations if d not in links.get(key, []))
        if key not in elements:
            raise KeyError(key)
    if "_findings_now" in elements:
        destinations = []
        for key, owner in active_registers.items():
            view = next(entry[2] for entry in detail if entry[0] == key)
            spec = next(spec for spec in findings.SPECS if spec.kind == DETAIL_KINDS.get(key)
                        or (key not in DETAIL_KINDS and spec.view == view))
            destinations.append((name, key, spec.kind))
        links["_findings_now"] = destinations
    return [by_title[title] for title in expected if title in by_title], links, row_links


def resolve_links(document, pending, targets, row_links):
    """Read IDs from assembled targets, never a literal or a guessed numeric identity."""
    elements = document["spec"]["elements"]
    for key, destinations in pending.items():
        panel = elements[key]["spec"]
        for name, owner, title in destinations:
            uid, target = targets[name]
            if owner not in target["spec"]["elements"] and (name, owner) in OPTIONAL_PANELS:
                continue
            panel_id = target["spec"]["elements"][owner]["spec"]["id"]
            url = f"/d/{uid}?viewPanel={panel_id}&${{__url_time_range}}&${{stack:queryparam}}"
            panel["links"].append({"title": title, "url": url, "targetBlank": False})
            if panel["vizConfig"]["group"] == "text":
                panel["vizConfig"]["spec"]["options"]["content"] += f"\n\n[{title}]({url})"

    for key, (field, destinations) in row_links.items():
        panel = elements[key]["spec"]
        links = []
        for name, owner, title in destinations:
            uid, target = targets[name]
            if owner not in target["spec"]["elements"] and (name, owner) in OPTIONAL_PANELS:
                continue
            panel_id = target["spec"]["elements"][owner]["spec"]["id"]
            links.append({"title": title, "url": f"/d/{uid}?viewPanel={panel_id}&${{__url_time_range}}"
                          "&var-stack=${__value.raw:percentencode}", "targetBlank": False})
        if not links:
            # No published destination: keep the unsplit source table, with no invented link.
            continue
        field = _split_identity({"spec": panel}, field)
        # Every frame is homogeneous in identity availability. No link property is attached to
        # an all-null/empty frame, even though Grafana can construct a link with an empty href.
        panel["vizConfig"]["spec"]["fieldConfig"]["overrides"].insert(0, {
            "matcher": {"id": "allMatch", "options": [
                {"id": "byName", "options": field},
                {"id": "byType", "options": "string"},
                {"id": "byRegexp", "options": "/ true$/"},
            ]}, "properties": [{"id": "links", "value": links}],
        })
