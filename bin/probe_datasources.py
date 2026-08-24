#!/usr/bin/env python3
"""PLAN 0.8 / 0.9 / 0.10 - probe the datasources and plugin APIs that Pillars B and D depend on.

Mints ONE short-lived Admin SA on the target stack, probes, then deletes it (verified). Discovery tool,
not part of the collector.

    export GCINSIGHT_READ_TOKEN=...
    ./bin/probe_datasources.py --stack <slug>
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.parse
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from bin.probe_regions import call, create_sa, delete_sa, sweep  # noqa: E402


def show(label: str, status: int, body: Any, keys: int = 6) -> None:
    if isinstance(body, dict):
        summary = json.dumps({k: body[k] for k in list(body)[:keys]}, default=str)[:220]
    elif isinstance(body, list):
        first = body[0] if body else None
        inner = list(first)[:keys] if isinstance(first, dict) else first
        summary = f"list[{len(body)}] first_keys={inner}"
    else:
        summary = str(body)[:200]
    print(f"  {label:52s} HTTP {status}  {summary}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stack", required=True)
    args = ap.parse_args()

    cap = os.environ.get("GCINSIGHT_READ_TOKEN", "").strip()
    if not cap:
        print("error: GCINSIGHT_READ_TOKEN not set", file=sys.stderr)
        return 2

    slug = args.stack
    base = f"https://{slug}.grafana.net"
    made = create_sa(cap, slug)
    if not made:
        return 1
    sa_id, token = made
    print(f"probing {slug} (sa={sa_id})\n", file=sys.stderr)
    findings: dict[str, Any] = {"stack": slug}

    try:
        _, dss = call("GET", f"{base}/api/datasources", token)
        dss = dss if isinstance(dss, list) else []
        byname = {d.get("name"): d for d in dss}

        # --- 0.8: alert-state-history. Regional like usage-insights, or per-stack? ---
        print("== 0.8 grafanacloud-alert-state-history ==")
        ash = next((d for d in dss if "alert-state-history" in str(d.get("name"))), None)
        if ash:
            uid = ash["uid"]
            findings["alert_state_history"] = {"uid": uid, "url": ash.get("url")}
            st, lbl = call("GET", f"{base}/api/datasources/proxy/uid/{uid}/loki/api/v1/labels", token)
            show("labels", st, lbl)
            labels = (lbl or {}).get("data", []) if isinstance(lbl, dict) else []
            findings["alert_state_history"]["labels"] = labels
            end = int(time.time()); start = end - 86400
            for lab in ("orgID", "org_id", "instance_id", "ruleUID", "from"):
                if lab in labels:
                    st, v = call(
                        "GET",
                        f"{base}/api/datasources/proxy/uid/{uid}/loki/api/v1/label/{lab}/values",
                        token,
                    )
                    vals = (v or {}).get("data", []) if isinstance(v, dict) else []
                    show(f"label {lab} values", st, f"n={len(vals)} {vals[:6]}")
                    findings["alert_state_history"][f"label_{lab}_count"] = len(vals)
            q = urllib.parse.urlencode(
                {"query": '{from="state-history"}', "limit": 2,
                 "start": f"{start}000000000", "end": f"{end}000000000"}
            )
            st, res = call(
                "GET", f"{base}/api/datasources/proxy/uid/{uid}/loki/api/v1/query_range?{q}", token
            )
            streams = (res or {}).get("data", {}).get("result", []) if isinstance(res, dict) else []
            show("sample query_range", st, f"streams={len(streams)}")
            if streams:
                findings["alert_state_history"]["sample"] = str(streams[0]["values"][0][1])[:400]
                print(f"    sample line: {str(streams[0]['values'][0][1])[:300]}")
        else:
            print("  NOT PRESENT on this stack")

        # --- 0.9: cardinality datasource vs the raw Mimir cardinality API ---
        print("\n== 0.9 grafanacloud-cardinality-datasource ==")
        card = next((d for d in dss if d.get("type") == "grafanacloud-cardinality-datasource"), None)
        if card:
            findings["cardinality_ds"] = {"uid": card["uid"], "url": card.get("url")}
            for path in ("", "/api/v1/labels", "/labels", "/api/v1/cardinality"):
                st, b = call("GET", f"{base}/api/datasources/proxy/uid/{card['uid']}{path}", token)
                show(f"proxy{path or ' (root)'}", st, b)
        else:
            print("  NOT PRESENT")

        # --- 0.10: Adaptive Metrics / Adaptive Logs recommendations ---
        print("\n== 0.10 Adaptive Metrics / Logs ==")
        for label, path in [
            ("adaptive-metrics recommendations", "/api/plugins/grafana-adaptive-metrics-app/resources/aggregations/recommendations"),
            ("adaptive-metrics rules", "/api/plugins/grafana-adaptive-metrics-app/resources/aggregations/rules"),
            ("adaptive-metrics exemptions", "/api/plugins/grafana-adaptive-metrics-app/resources/aggregations/exemptions"),
            ("adaptive-logs patterns", "/api/plugins/grafana-adaptivelogs-app/resources/patterns"),
            ("adaptive-logs drop-rules", "/api/plugins/grafana-adaptivelogs-app/resources/drop-rules"),
            ("cmab cost-attribution", "/api/plugins/grafana-cmab-app/resources/cost-attribution"),
            ("cmab usage", "/api/plugins/grafana-cmab-app/resources/usage"),
        ]:
            st, b = call("GET", f"{base}{path}", token)
            show(label, st, b)
            findings.setdefault("plugin_apis", {})[label] = st

        # --- bonus: which of the interesting datasources exist here at all ---
        print("\n== datasource inventory of interest ==")
        interesting = [
            ("grafanacloud-usage", lambda name: name == "grafanacloud-usage"),
            ("usage-insights", lambda name: name.endswith("-usage-insights")),
            ("alert-state-history", lambda name: name.endswith("-alert-state-history")),
            ("cardinality-management", lambda name: name.endswith("-cardinality-management")),
            ("showback", lambda name: "showback" in name.lower()),
        ]
        for label, matches in interesting:
            found = next((d for name, d in byname.items() if matches(str(name))), None)
            print(f"  {label:46s} {'present' if found else 'absent':8s} "
                  f"{found.get('type') if found else ''}")
    finally:
        ok = delete_sa(cap, slug, sa_id)
        n = sweep(cap, slug)
        print(f"\nteardown: deleted={ok} swept={n}", file=sys.stderr)

    out = f"testdata/probe-datasources-{slug}.json"
    with open(out, "w") as fh:
        json.dump(findings, fh, indent=2, default=str)
    print(f"wrote {out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
