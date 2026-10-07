"""Public assembled selectors, including empty schemas, not dashboard source text.

This gate does not certify source queries, units, cohorts, browser rendering or live
semantics. Exemptions below are debts, never evidence of rendering.
"""
from __future__ import annotations

import copy
import functools
import importlib
import json
import pathlib
import pkgutil
import re
import tempfile
import unittest
from unittest import mock

from bin import alerts, dashboards, make_local_views
from collector import pillars
from collector.dashboards import build
from collector.emit import budget, hydrate, s3
from collector.pillars import coverage, library_panels

ROOT = pathlib.Path(__file__).resolve().parents[1]


def declared_schemas():
    """Producer declarations, independent of consumer columns and fixture occupancy."""
    # This producer declares a single SCHEMA but no VIEW constant. The public
    # object name is its publication contract, not a consumer fallback readback.
    schemas = {"library_panels_inventory": library_panels.SCHEMA}
    for entry in pkgutil.iter_modules(pillars.__path__):
        module = importlib.import_module(f"collector.pillars.{entry.name}")
        schemas.update(getattr(module, "VIEW_SCHEMAS", {}))
        if hasattr(module, "VIEW") and hasattr(module, "SCHEMA"):
            schemas[module.VIEW] = module.SCHEMA
    return schemas


def placed(value):
    if isinstance(value, dict):
        if value.get("kind") == "ElementReference":
            yield value["name"]
        for child in value.values():
            yield from placed(child)
    elif isinstance(value, list):
        for child in value:
            yield from placed(child)


def consumers(documents):
    """Only query-bearing, placed panels; organize/treemap exclusions are real."""
    fields, expressions, tabs = {}, [], {}
    for dashboard, document in documents.items():
        spec = document["spec"]
        layout = spec["layout"]
        layouts = layout["spec"].get("tabs", [layout])
        for index, tab in enumerate(layouts):
            tab_id = (dashboard, tab["spec"].get("title", str(index)))
            names = list(placed(tab))
            tabs[tab_id] = names
            for name in names:
                panel = spec["elements"][name]["spec"]
                data = panel.get("data", {}).get("spec", {})
                hidden = set()
                for transform in data.get("transformations", []):
                    if transform["spec"]["id"] == "organize":
                        hidden.update(k for k, v in transform["spec"]["options"]
                                      .get("excludeByName", {}).items() if v)
                for query in data.get("queries", []):
                    inner = query["spec"]["query"]
                    q = inner["spec"]
                    if "expr" in q:
                        expressions.append((tab_id, name, q["expr"]))
                    if inner["group"] != build.INFINITY_TYPE:
                        continue
                    match = re.search(r"/views/([^/]+)\.json$", q.get("url", ""))
                    if not match:
                        continue
                    root = q.get("root_selector", "")
                    optional = re.fullmatch(r"\$exists\(([^()]+)\) \? \[\1\] : \[\]", root)
                    if optional:
                        root = optional[1]
                    viz = panel["vizConfig"]
                    options = viz["spec"].get("options", {})
                    for column in q.get("columns", []):
                        display = column.get("text", column["selector"])
                        if display in hidden:
                            continue
                        if viz["group"] == "marcusolsson-treemap-panel" and display not in (
                            options.get("textField"), options.get("sizeField"),
                            options.get("colorByField"), *options.get("labelFields", []),
                        ):
                            continue
                        fields.setdefault((match[1], f"{root}.{column['selector']}"), set()).add(tab_id)
    return fields, expressions, tabs


def row_requirements(payloads, schemas):
    return {(view, f"rows.{field}") for view, payload in payloads.items()
            for field in ({key for row in payload["rows"] for key in row}
                          | {key for key, _kind in schemas.get(view, ())})}


def field_gaps(payloads, schemas, documents):
    rendered, _expressions, _tabs = consumers(documents)
    return row_requirements(payloads, schemas) - rendered.keys()


# A bounded lexical recognizer, not a PromQL parser/engine. Strings and comments
# are indivisible tokens; matcher, range and grouping-label contents never earn
# selector credit. Unknown syntax and templated enum matchers earn no credit.
# stack/region are live identity dimensions, not closed enum vocabularies.
PROM_TOKEN = re.compile(
    r'''(?P<skip>\s+|\#[^\n]*)|(?P<string>"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'|`[^`]*`)|'''
    r'(?P<number>(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)|'
    r'(?P<identifier>[A-Za-z_:][A-Za-z0-9_:]*|\$[A-Za-z_][A-Za-z0-9_]*)|'
    r'(?P<symbol>=~|!~|!=|==|<=|>=|[{}()\[\],+*/%^<>=@-])')
LABEL_GROUPS = {"by", "without", "on", "ignoring", "group_left", "group_right"}
BINARY_OPS = {"+", "-", "*", "/", "%", "^", "==", "!=", "<", ">", "<=", ">=",
              "and", "or", "unless", "atan2"}


def selector_matchers(tokens):
    """Require whole comma-delimited matcher syntax, never regex fragments."""
    matchers = []
    index = 0
    while index < len(tokens):
        if index + 3 > len(tokens):
            return None
        (kind, key), (_op_kind, op), (value_kind, quoted) = tokens[index:index + 3]
        if (kind != "identifier" or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key)
                or op not in ("=", "!=", "=~", "!~")
                or value_kind != "string" or not quoted.startswith('"')):
            return None
        try:
            expected = json.loads(quoted)
            if op in ("=~", "!~"):
                re.compile(expected)
        except (ValueError, re.error):
            return None
        matchers.append((key, op, expected))
        index += 3
        if index < len(tokens):
            if tokens[index][1] != ",":
                return None
            index += 1  # A single trailing comma is valid PromQL.
    return tuple(matchers)


@functools.lru_cache(maxsize=2048)
def vector_selectors(expression):
    tokens = []
    position = 0
    while position < len(expression):
        token = PROM_TOKEN.match(expression, position)
        if token is None:
            return ()  # Including unterminated quotes: no partial regex credit.
        if token.lastgroup != "skip":
            tokens.append((token.lastgroup, token.group()))
        position = token.end()
    # Balance delimiters before crediting anything, and record opaque spans.
    stack, closing, label_ends = [], {}, set()
    for index, (_kind, value) in enumerate(tokens):
        if value in ("(", "{", "["):
            stack.append((index, value))
        elif value in (")", "}", "]"):
            if not stack or stack[-1][1] != {")": "(", "}": "{", "]": "["}[value]:
                return ()
            start, opener = stack.pop()
            closing[start] = index
            if opener == "(" and start and tokens[start - 1][1] in LABEL_GROUPS:
                label_ends.add(index)
    if stack:
        return ()
    selectors, index = [], 0
    while index < len(tokens):
        kind, value = tokens[index]
        previous = tokens[index - 1][1] if index else None
        if value in ("{", "[") or (value == "(" and previous in LABEL_GROUPS):
            index = closing[index] + 1
            continue
        if kind == "identifier" and re.fullmatch(r"gcinsight_[A-Za-z0-9_]+", value):
            end, matchers = index + 1, ()
            if end < len(tokens) and tokens[end][1] == "{":
                matchers = selector_matchers(tokens[end + 1:closing[end]])
                end = closing[end] + 1
            following = tokens[end][1] if end < len(tokens) else None
            # Names in prose, function names and grouping labels are not operands.
            starts_operand = (previous is None or previous in ({"(", ",", "bool", "group_left", "group_right"} | BINARY_OPS)
                              or index - 1 in label_ends)
            ends_operand = following is None or following in ({")", ",", "[", "offset", "@"} | BINARY_OPS)
            if starts_operand and ends_operand and matchers is not None:
                selectors.append((value, matchers))
        index += 1
    return tuple(selectors)


def selects(expression, metric, labels):
    for name, matchers in vector_selectors(expression):
        if name != metric:
            continue
        accepted = True
        for key, op, expected in matchers:
            if key != "__name__" and key not in labels:
                continue
            value = metric if key == "__name__" else labels[key]
            if "$" in expected:
                accepted = False
                break
            equal = (re.fullmatch(expected, value) is not None
                     if op in ("=~", "!~") else value == expected)
            if equal != (op in ("=", "=~")):
                accepted = False
                break
        if accepted:
            return True
    return False


def metric_gaps(requirements, documents):
    _fields, expressions, _tabs = consumers(documents)
    return {(name, labels) for name, labels in requirements
            if not any(selects(expr, name, dict(labels)) for _tab, _panel, expr in expressions)}


def artifact_fixture():
    with tempfile.TemporaryDirectory() as directory:
        make_local_views.main(["--out", directory])
        payloads = {p.stem: json.loads(p.read_text()) for p in pathlib.Path(directory).glob("*.json")}
        with mock.patch.object(build, "VIEWS_DIR", directory), mock.patch.object(build, "BUCKET", "offline"):
            documents = {name: dashboards.assemble(name, "infinity-offline")[1]
                         for name in dashboards.BUILDERS}
    return payloads, documents


def enum_requirements():
    """Fixed/current producer contracts, with open domains explicitly unresolved.

    No compose fixture or capacity number supplies a vocabulary. Discovery-backed
    identities are not configured rosters. UNKNOWN metrics obtain name-only credit,
    never exhaustive enum coverage, and named reserves are not runtime obligations.
    """
    return budget.runtime_requirements()


def metadata_leaves(value, prefix="meta"):
    if isinstance(value, dict) and value:
        for key, child in value.items():
            yield from metadata_leaves(child, f"{prefix}.{key}")
    else:
        yield prefix


# Exact provenance debts, not a blanket metadata exemption. GCI-0110
# (expose optional publication age/completeness) owns supported metadata display;
# GCI-0114 (decide discovery-backed history/metadata) owns missing state contracts.
METADATA_DEBTS = {
    "meta.generated_at": ("Object publication age is not input age.", "GCI-0110"),
    "meta.tier": ("Publisher tier is not input ownership tier.", "GCI-0110"),
    "meta.stacks_total": ("Snapshot estate denominator is not current scan inventory.", "GCI-0110"),
    "meta.stacks_scannable": ("Snapshot scannable denominator is not current scan coverage.", "GCI-0110"),
    "meta.stacks_scanned": ("Snapshot scanned denominator is not current scan coverage.", "GCI-0110"),
    "meta.coverage_ratio": ("Snapshot coverage is not current scan coverage.", "GCI-0110"),
}
INPUT_METADATA_DEBTS = {
    "source": "Input origin remains audit-only, not a rendered product finding.",
    "age_seconds": "Snapshot input age is not the evolving input-age gauge.",
    "tier": "Input owning tier is not the publisher tier.",
    "available": "Unavailable input cannot be inferred from empty rows.",
    "stale": "Last-good staleness is not exposed by the row table.",
    "state": "Unavailable/partial state needs its own public selector.",
    "reason": "Failed observation reason is not empty-product evidence.",
    "schema_version": "Input schema compatibility remains unrendered provenance.",
}


def metadata_debt(path):
    if path in METADATA_DEBTS:
        return METADATA_DEBTS[path]
    parts = path.split(".")
    if (len(parts) == 4 and parts[:2] == ["meta", "inputs"]
            and parts[2] in hydrate.INPUT_OWNER and parts[3] in INPUT_METADATA_DEBTS):
        return INPUT_METADATA_DEBTS[parts[3]], "GCI-0110"
    return None


# GCI-0120 (render or retire uncovered enum combinations): nine real renderings
# close selector debts. Ten exact reserves are NOT rendering or bounded-absence
# exemptions: tests/test_budget.py exercises transitive final emission and seeds
# violations in both composition and common publication processing.
ENUM_DEBTS = {}
ENUM_RESERVES = budget.RUNTIME_RESERVES

# GCI-0121 (declare runtime label domains independently of planning capacity)
# resolves fixed/current contracts, NOT the source-proven open producer semantics.
# GCI-0126 (close bounded-label proof for open Assistant/scan failure domains) owns
# these exact UNKNOWNs. Neither name-only selectors nor helper checks prove them.
DOMAIN_DEBTS = {
    (metric, label): ("Source-proven open vocabulary; exhaustive coverage/conformance unavailable.", "GCI-0126")
    for metric, label in (
        ("gcinsight_ai_estate_messages", "category"),
        ("gcinsight_ai_estate_messages", "surface"),
        ("gcinsight_scan_stacks_failed", "reason"),
    )
}
# Stronger tab-specific ownership and dimension-preserving enum display are NOT
# certified by structural placement or selector inclusion. GCI-0122 (define
# per-tab field/enum display ownership) owns that separate contract.
DISPLAY_CONTRACT_DEBT = (
    "Structural placement and selector inclusion do not certify separate enum granularity or tab ownership.",
    "GCI-0122",
)


class RuntimeRequirementsTest(unittest.TestCase):
    def test_unscored_relation_is_exact_not_cartesian(self):
        requirements, _unknown = enum_requirements()
        actual = {labels for name, labels in requirements if name == "gcinsight_coverage_unscored"}
        expected = {(("component", component), ("reason", reason))
                    for component, reason in coverage.UNSCORED_PAIRS}
        self.assertEqual(actual, expected, "only nine source-backed pairs are runtime obligations")


class SelectorLexicalTest(unittest.TestCase):
    def test_only_actual_vector_selectors_credit_enum_coverage(self):
        metric = "gcinsight_estate_users_by_role"
        labels = {"role": "viewer"}
        positives = (
            metric,
            f'{metric} {{ role = "viewer" }}',
            f'{metric}{{role="viewer",}}',
            f'{metric}{{__name__="{metric}",role="viewer"}}',
            f'up * on (job) group_left (region) {metric}{{role="viewer"}}',
            f'{metric} offset 5m',
            f'{metric} @ end()',
            f'sum by (role) ({metric}{{role=~"admin|viewer"}})',
            f'up + {metric}{{role!="admin"}}',
            f'rate({metric}{{role!~"admin|editor"}}[5m])',
            f'{metric}{{role="viewer",stack=~"$stack"}}',
            f'# {metric}{{role="admin"}}\n{metric}{{role="viewer"}}',
            f'label_replace({metric}, "note", "text", "job", "x")',
            f'{metric}{{role="viewer",note="brace }} and # are string content"}}',
        )
        negatives = (
            f'label_replace(up, "note", "{metric}", "job", "x")',
            f'label_replace(up, "note", \'{metric}\', "job", "x")',
            f'label_replace(up, "note", `{metric}`, "job", "x")',
            f'label_replace(up, "note", "escaped \\\" {metric}", "job", "x")',
            f'up # {metric}{{role="viewer"}}',
            f'# {metric}\nup',
            f'up{{note="{metric}"}}',
            f'sum by ({metric}) (up)',
            f'up + on ({metric}) group_left ({metric}) up',
            f'{metric}(up)',
            f'up{{{metric}="viewer"}}',
            f'up[{metric}]',
            f'mention {metric} in prose',
            f'{metric}{{role="admin"}}',
            f'{metric}{{role=~"$role"}}',
            f'{metric}{{role="viewer",broken}}',
            f'{metric}{{role="viewer"',
            f'{metric}{{role="viewer" role="admin"}}',
            f'{metric}{{role="viewer",,stack="x"}}',
            f'{metric}{{role=~"["}}',
            f'{metric}{{__name__="up",role="viewer"}}',
            f'{metric}{{__name__=~"$metric",role="viewer"}}',
            f'{{__name__="{metric}",role="viewer"}}',  # Unsupported name-only selector.
            f'{metric}{{role=\'viewer\'}}',  # Unsupported matcher string syntax.
            f'{metric}{{role="viewer"}} "arbitrary trailing mention"',
            f'(up + {metric}',
            f'{metric}{{role="viewer"]',
        )
        for expression in positives:
            with self.subTest(expression=expression, selected=True):
                self.assertTrue(selects(expression, metric, labels))
        for expression in negatives:
            with self.subTest(expression=expression, selected=False):
                self.assertFalse(selects(expression, metric, labels))


class DashboardCoverageTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.payloads, cls.documents = artifact_fixture()
        cls.schemas = declared_schemas()
        cls.enums, cls.unknown_domains = enum_requirements()

    def assert_fields_covered(self, payloads, schemas, documents):
        self.assertEqual(field_gaps(payloads, schemas, documents), set(), "Unrendered published row fields")

    def assert_enums_covered(self, requirements, documents):
        self.assertEqual(metric_gaps(requirements, documents) - ENUM_DEBTS.keys() - ENUM_RESERVES.keys(), set(),
                         "Unrendered bounded enum combinations without a specific debt owner")

    def test_every_published_row_field_including_empty_schema_is_selected(self):
        self.assert_fields_covered(self.payloads, self.schemas, self.documents)

    def test_seed_unrendered_field_is_rejected(self):
        payloads = copy.deepcopy(self.payloads)
        self.assertTrue(payloads["estate"]["rows"])
        payloads["estate"]["rows"][0]["Reader role drift"] = "unexpected grant"
        with self.assertRaisesRegex(AssertionError, "Reader role drift"):
            self.assert_fields_covered(payloads, self.schemas, self.documents)

    def test_seed_empty_fixture_schema_field_is_rejected(self):
        self.assertEqual(self.payloads["risk_retention_policy_gaps"]["rows"], [])
        schemas = copy.deepcopy(self.schemas)
        schemas["risk_retention_policy_gaps"] += (("Policy evaluation reason", "string"),)
        with self.assertRaisesRegex(AssertionError, "Policy evaluation reason"):
            self.assert_fields_covered(self.payloads, schemas, self.documents)

    def test_seed_omitted_enum_value_is_rejected(self):
        # Mutate only the assembled artifact. The producer still declares and
        # emits the viewer role; metric-name presence would miss this defect.
        documents = copy.deepcopy(self.documents)
        for document in documents.values():
            for panel in document["spec"]["elements"].values():
                for query in panel["spec"].get("data", {}).get("spec", {}).get("queries", []):
                    spec = query["spec"]["query"]["spec"]
                    if "expr" in spec:
                        spec["expr"] = spec["expr"].replace(
                            'gcinsight_estate_users_by_role{role="viewer"}',
                            'gcinsight_estate_users_by_role{role="admin"}')
        roles = {(name, labels) for name, labels in self.enums if name == "gcinsight_estate_users_by_role"}
        self.assertTrue(any(dict(labels).get("role") == "viewer" for _name, labels in roles))
        self.assert_enums_covered(roles, self.documents)
        with self.assertRaisesRegex(AssertionError, "viewer"):
            self.assert_enums_covered(roles, documents)

    def test_seed_quoted_and_commented_metric_cannot_rescue_omitted_viewer(self):
        documents = copy.deepcopy(self.documents)
        metric = "gcinsight_estate_users_by_role"
        for document in documents.values():
            for panel in document["spec"]["elements"].values():
                for query in panel["spec"].get("data", {}).get("spec", {}).get("queries", []):
                    spec = query["spec"]["query"]["spec"]
                    if "expr" in spec:
                        spec["expr"] = spec["expr"].replace(
                            f'{metric}{{role="viewer"}}', f'{metric}{{role="admin"}}')
                        spec["expr"] += (f' or label_replace(up, "note", "{metric}", "job", "x")'
                                         f' # {metric}{{role="viewer"}}')
        requirement = {(metric, (("role", "viewer"),))}
        self.assertEqual(metric_gaps(requirement, self.documents), set())
        self.assertEqual(metric_gaps(requirement, documents), requirement)
        with self.assertRaisesRegex(AssertionError, "viewer"):
            self.assert_enums_covered(requirement, documents)

    def test_observed_and_declared_enum_combinations_are_rendered(self):
        self.assert_enums_covered(self.enums, self.documents)

    def test_current_debts_have_exact_owners_without_claiming_coverage(self):
        self.assertEqual(metric_gaps(self.enums, self.documents), ENUM_DEBTS.keys(),
                         "New runtime gaps need owners; reserves are not emitted obligations")
        self.assertFalse(self.enums & ENUM_RESERVES.keys(), "reserved capacity is not runtime data")
        self.assertEqual(self.unknown_domains, DOMAIN_DEBTS.keys(),
                         "New unknown domain needs an explicit contract owner")
        for debt in (*ENUM_DEBTS.values(), *DOMAIN_DEBTS.values(), DISPLAY_CONTRACT_DEBT):
            reason, owner = debt
            self.assertTrue(reason)
            self.assertRegex(owner, r"^GCI-\d{4}$")

    def test_resolved_selectors_cannot_hide_behind_reserves(self):
        required = {("gcinsight_value_benchmark", (("kind", kind),)) for kind in
                    ("active_series", "alert_rules", "dashboards_per_user", "datasource_types",
                     "maturity_score", "series_per_billed_user", "signals_in_use")}
        required.update({("gcinsight_coverage_metric_names", (("kind", "matched"),)),
                         ("gcinsight_scan_completed_timestamp_seconds", (("tier", "t4"),))})
        self.assertEqual(metric_gaps(required, self.documents), set())
        for metric, labels in required:
            documents = copy.deepcopy(self.documents)
            for document in documents.values():
                for element in document["spec"]["elements"].values():
                    for query in element["spec"].get("data", {}).get("spec", {}).get("queries", []):
                        spec = query["spec"]["query"]["spec"]
                        if "expr" in spec and selects(spec["expr"], metric, dict(labels)):
                            spec["expr"] = "up"
            with self.subTest(metric=metric, labels=labels):
                with self.assertRaisesRegex(AssertionError, metric):
                    self.assert_enums_covered({(metric, labels)}, documents)

    def test_per_tab_queries_are_placed_and_resolve_public_columns(self):
        fields, expressions, tabs = consumers(self.documents)
        requirements = row_requirements(self.payloads, self.schemas)
        # Metadata roots are independently checked against publication envelopes.
        requirements.update((view, path) for view, payload in self.payloads.items()
                            for path in metadata_leaves(payload["meta"]))
        self.assertTrue(tabs)
        for key, tab_ids in fields.items():
            with self.subTest(field=key, tabs=tab_ids):
                self.assertIn(key, requirements)
        for dashboard, document in self.documents.items():
            names = {name for (owner, _tab), panels in tabs.items() if owner == dashboard for name in panels}
            for name, element in document["spec"]["elements"].items():
                if element["spec"].get("data", {}).get("spec", {}).get("queries"):
                    self.assertIn(name, names, f"Query panel unplaced on {dashboard}")
        explanatory = {("operations", "How to read this"), ("commercial", "How to read this"),
                       ("ai", "Feature activity")}
        # These are explanatory-only, not exempt product-data tabs. Their design
        # disposition is GCI-0100 (review dashboard/tab operator relevance).
        actual = {tab for tab in tabs if not any(tab == t for t, _name, _expr in expressions)
                  and not any(tab in locations for locations in fields.values())}
        self.assertEqual(actual, explanatory)

    def test_metadata_gaps_have_exact_supported_state_debts(self):
        rendered, _expressions, _tabs = consumers(self.documents)
        gaps = {(view, path) for view, payload in self.payloads.items()
                for path in metadata_leaves(payload["meta"]) if (view, path) not in rendered}
        self.assertTrue(gaps, "Do not claim snapshot metadata is rendered by input metrics")
        for view, path in gaps:
            with self.subTest(view=view, path=path):
                self.assertIsNotNone(metadata_debt(path), "New unowned metadata gap")

    def test_optional_empty_unavailable_and_lastgood_keep_public_contract(self):
        # No invented not-enabled state. Own measured-empty and rejected own
        # observations obtain their provenance from the actual hydration API.
        import datetime as dt
        now = dt.datetime(2026, 10, 6, tzinfo=dt.timezone.utc)
        view = input_name = "library_panels_inventory"
        empty = s3.view_payload([], {"generated_at": now.isoformat()})
        old = s3.view_payload([], {"generated_at": (now - dt.timedelta(days=1)).isoformat()})
        with tempfile.TemporaryDirectory() as directory:
            for name, payload in self.payloads.items():
                (pathlib.Path(directory) / f"{name}.json").write_text(json.dumps(payload))
            path = pathlib.Path(directory) / f"{view}.json"
            for payload in (empty, old):
                path.write_text(json.dumps(payload))
                with mock.patch.object(build, "VIEWS_DIR", directory), mock.patch.object(build, "BUCKET", "offline"):
                    doc = dashboards.assemble("usage", "infinity-offline")[1]
                fields, _expr, _tabs = consumers({"usage": doc})
                self.assertTrue(all((view, f"rows.{key}") in fields for key, _ in self.schemas[view]))
                # Timestamp debt is acknowledged, not falsely counted as rendered.
                self.assertNotIn((view, "meta.generated_at"), fields)
                self.assertIsNotNone(metadata_debt("meta.generated_at"))
            path.unlink()
            with mock.patch.object(build, "VIEWS_DIR", directory), mock.patch.object(build, "BUCKET", "offline"):
                absent = dashboards.assemble("usage", "infinity-offline")[1]
            fields, _expr, _tabs = consumers({"usage": absent})
            self.assertFalse(any(name == view for name, _field in fields))
        loader = lambda _tier, _bucket: None
        fixture = json.loads((ROOT / "tests" / "fixtures" / "compose_inputs.json").read_text())
        stack = next(stack for stack in fixture["stacks"] if stack.get("status") != "paused")
        own = {input_name: {stack["slug"]: {"available": True, "library_panel_count": 0}}}
        _inputs, measured = hydrate.hydrate("t2", own, now=now, loader=loader)
        _inputs, rejected = hydrate.hydrate("t2", {}, now=now, loader=loader,
                                           unavailable={input_name: "permission error"})
        _metrics, measured_views = library_panels.build([stack], own[input_name])
        self.assertEqual(measured_views[view], [{"Stack": stack["slug"], "Configured library panels": 0}])
        self.assertTrue(measured[input_name]["available"])
        self.assertFalse(rejected[input_name]["available"])
        kept, withheld = hydrate.filter_views({view: []}, rejected)
        self.assertNotIn(view, kept)
        self.assertIn(view, withheld)
        for state in (measured, rejected):
            for field in state[input_name]:
                self.assertIsNotNone(metadata_debt(f"meta.inputs.{input_name}.{field}"))
