#!/usr/bin/env python3
"""PLAN 0.2 - determine the usage-insights credential map empirically.

Mints a SHORT-LIVED service account on one stack per cluster, reads that stack's real usage-insights
host from its datasource list, measures which stacks the tenant actually covers, then deletes every
service account it created.

Deliberately separate from `collector/` - the collector's HTTP client is GET-only by construction, and
provisioning a service account on a live customer stack is an explicit, logged step, never something a
collector does implicitly (SPEC §8).

    export GCINSIGHT_READ_TOKEN=...
    ./bin/probe_regions.py --targets /tmp/cluster-targets.json --out testdata/region-map.json

Teardown runs in a `finally` block and is verified. If this script is killed, run with `--cleanup-only`
to sweep any SA matching the probe name.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from typing import Any

GCOM = "https://grafana.com/api"
SA_NAME = "gcinsight-probe"
TOKEN_TTL = 3600
PACE = 1.0 / 6.0  # gcom is paced at 6 req/s - a measured ceiling, see docs/traps.md

_last_call = [0.0]


def call(method: str, url: str, token: str, body: dict | None = None) -> tuple[int, Any]:
    wait = PACE - (time.monotonic() - _last_call[0])
    if wait > 0:
        time.sleep(wait)
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", f"Bearer {token}")
    if data:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=60) as fh:
            _last_call[0] = time.monotonic()
            raw = fh.read()
            return fh.status, (json.loads(raw) if raw else None)
    except urllib.error.HTTPError as exc:
        _last_call[0] = time.monotonic()
        raw = exc.read()
        retry = exc.headers.get("Retry-After")
        if exc.code == 429 and retry:
            time.sleep(float(retry) + 1)
            return call(method, url, token, body)
        try:
            return exc.code, json.loads(raw)
        except Exception:
            return exc.code, raw[:200].decode(errors="replace")


def create_sa(cap: str, slug: str) -> tuple[int, str] | None:
    status, body = call(
        "POST", f"{GCOM}/instances/{slug}/api/serviceaccounts", cap,
        {"name": SA_NAME, "role": "Admin", "isDisabled": False},
    )
    if status != 201 or not isinstance(body, dict):
        print(f"  {slug}: SA create HTTP {status} {body}", file=sys.stderr)
        return None
    sa_id = body["id"]
    status, tok = call(
        "POST", f"{GCOM}/instances/{slug}/api/serviceaccounts/{sa_id}/tokens", cap,
        {"name": "probe", "secondsToLive": TOKEN_TTL},
    )
    if status != 200 or not isinstance(tok, dict):
        print(f"  {slug}: token HTTP {status}", file=sys.stderr)
        return sa_id, ""
    return sa_id, tok["key"]


def delete_sa(cap: str, slug: str, sa_id: int) -> bool:
    status, _ = call("DELETE", f"{GCOM}/instances/{slug}/api/serviceaccounts/{sa_id}", cap)
    return status == 200


def sweep(cap: str, slug: str) -> int:
    """Delete every SA on this stack matching the probe name. Idempotent."""
    status, body = call(
        "GET", f"{GCOM}/instances/{slug}/api/serviceaccounts/search?query={SA_NAME}", cap
    )
    if status != 200 or not isinstance(body, dict):
        return 0
    removed = 0
    for sa in body.get("serviceAccounts", []):
        if sa.get("name") == SA_NAME and delete_sa(cap, slug, sa["id"]):
            removed += 1
    return removed


def probe_stack(slug: str, token: str) -> dict[str, Any]:
    """With a stack token: find the usage-insights datasource, then measure its coverage."""
    base = f"https://{slug}.grafana.net"
    out: dict[str, Any] = {"slug": slug}

    status, dss = call("GET", f"{base}/api/datasources", token)
    if status != 200 or not isinstance(dss, list):
        out["error"] = f"datasources HTTP {status}"
        return out

    # Trap 6: the uid is NOT `grafanacloud-usage-insights` on every stack, and the name is
    # slug-prefixed. Resolve at runtime, and exclude the pdcInjected regional variants (Trap 7).
    candidates = [
        d for d in dss
        if d.get("type") == "loki"
        and "usage-insights" in str(d.get("name", ""))
        and not (d.get("jsonData") or {}).get("pdcInjected")
    ]
    if not candidates:
        out["error"] = "no usable usage-insights datasource"
        out["loki_datasources"] = [d.get("name") for d in dss if d.get("type") == "loki"]
        return out

    ds = candidates[0]
    out["ds_uid"] = ds.get("uid")
    out["ds_name"] = ds.get("name")
    out["insight_host"] = ds.get("url")

    end = int(time.time())
    start = end - 86400
    q = urllib.parse.urlencode(
        {"match[]": '{instance_type=~".+"}', "start": f"{start}000000000", "end": f"{end}000000000"}
    )
    status, series = call(
        "GET", f"{base}/api/datasources/proxy/uid/{ds['uid']}/loki/api/v1/series?{q}", token
    )
    if status != 200 or not isinstance(series, dict):
        out["error"] = f"series HTTP {status}"
        return out

    pairs = {(str(d.get("instance_id")), str(d.get("instance_type"))) for d in series.get("data", [])}
    out["pairs"] = sorted(pairs)
    out["pair_count"] = len(pairs)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--targets", required=True, help="JSON map of cluster -> stack slug")
    ap.add_argument("--out", required=True)
    ap.add_argument("--cleanup-only", action="store_true")
    args = ap.parse_args()

    cap = os.environ.get("GCINSIGHT_READ_TOKEN", "").strip()
    if not cap:
        print("error: GCINSIGHT_READ_TOKEN not set", file=sys.stderr)
        return 2

    targets: dict[str, str] = json.load(open(args.targets))

    if args.cleanup_only:
        for cluster, slug in targets.items():
            n = sweep(cap, slug)
            print(f"{slug}: swept {n}")
        return 0

    created: list[tuple[str, int]] = []
    results: dict[str, Any] = {}
    try:
        for cluster, slug in targets.items():
            print(f"{cluster} -> {slug}", file=sys.stderr)
            made = create_sa(cap, slug)
            if not made:
                results[cluster] = {"slug": slug, "error": "sa_create_failed"}
                continue
            sa_id, token = made
            created.append((slug, sa_id))
            if not token:
                results[cluster] = {"slug": slug, "error": "token_failed"}
                continue
            res = probe_stack(slug, token)
            res["cluster"] = cluster
            results[cluster] = res
            print(f"  {res.get('insight_host', res.get('error'))} "
                  f"pairs={res.get('pair_count', 0)}", file=sys.stderr)
    finally:
        print("\n-- teardown --", file=sys.stderr)
        for slug, sa_id in created:
            ok = delete_sa(cap, slug, sa_id)
            print(f"  {slug} sa={sa_id} deleted={ok}", file=sys.stderr)
        leftover = {slug: sweep(cap, slug) for slug, _ in created}
        stragglers = {k: v for k, v in leftover.items() if v}
        print(f"  swept stragglers: {stragglers or 'none'}", file=sys.stderr)

    with open(args.out, "w") as fh:
        json.dump(results, fh, indent=2)
    print(f"wrote {args.out}", file=sys.stderr)

    # Which stacks does each insight tenant actually cover?
    inv = json.load(open("testdata/gcom-instances-2026-08-17.json"))["items"]
    lut: dict[str, dict[str, str]] = {}
    for s in inv:
        for f in ("id", "hmInstancePromId", "hmInstanceGraphiteId", "hlInstanceId",
                  "htInstanceId", "hpInstanceId", "amInstanceId"):
            if s.get(f):
                lut[str(s[f])] = {"slug": s["slug"], "cluster": s["clusterSlug"],
                                  "region": s["regionSlug"]}

    print(f"\n{'cluster':20s} {'insight host':46s} {'stacks':>6s}  clusters covered")
    for cluster, res in sorted(results.items()):
        if "pairs" not in res:
            print(f"{cluster:20s} {res.get('error', '?'):46s}")
            continue
        covered = defaultdict(set)
        for iid, _ in res["pairs"]:
            hit = lut.get(iid)
            if hit:
                covered[hit["cluster"]].add(hit["slug"])
        allstacks = {s for v in covered.values() for s in v}
        host = (res.get("insight_host") or "").replace("https://", "")
        print(f"{cluster:20s} {host:46s} {len(allstacks):6d}  "
              f"{ {c: len(v) for c, v in covered.items()} }")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
