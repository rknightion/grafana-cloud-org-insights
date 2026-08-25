#!/usr/bin/env python3
"""Provision and reconcile the per-stack read-only reader (PLAN 17D).

    ./bin/provision.py --dry-run          # what it would do, no writes anywhere
    ./bin/provision.py                    # reconcile the whole estate
    ./bin/provision.py --stack stack039   # one stack, for debugging

Decision logic lives in `collector/provision.py`; this file is the I/O and the ordering.

## The credential

`GCINSIGHT_PROVISION_TOKEN` - access policy `gcinsight-provisioner`, with scopes **exactly**
`stacks:read` + `stack-service-accounts:write`. Verified 2026-08-20: it can list the estate, list and
create service accounts and mint their tokens, and it is **401 on `/v1/accesspolicies`**  -  a leak cannot
escalate itself to a broader credential. It is deliberately NOT the collector's credential; the
collector reads SSM and never holds this token.

`stack-service-accounts:write` is the narrowest scope that exists  -  there is no `:create`  -  so this
token could in principle delete every service account on 273 stacks, including the organisation's own
`Observability Service Account(DO NOT MODIFY OR DELETE!)`. Two controls, not one:

1. **`_delete_sa` refuses any id this process did not itself create.** The ledger is authoritative, not
   a name pattern. `tests/test_provision_io.py` asserts the refusal.
2. **Pruning needs no gcom delete at all**  -  a deleted stack takes its service accounts with it, so
   removal is an SSM parameter delete. Steady-state gcom write surface is create-only.

## Why this does not use `ReadOnlyClient`

`collector/httpclient.ReadOnlyClient` **refuses any non-GET method by construction**
(`MethodNotAllowed`, SPEC §8)  -  that is a load-bearing property of the collector and is not weakened to
suit this script. The provisioner carries its own client, so the one component in this project that can
write to gcom is the one file whose whole purpose is provisioning. It shares the same 6 req/s pacing
(`config.HOST_RATE_LIMITS`) through a single bucket for reads AND writes, because gcom's limit is per
credential and two buckets would double the intended rate.

## Ordering, and why it is this order

The role must be correct BEFORE a token is minted, or we store a credential that 403s on everything.
The transient Admin identity is deleted LAST, because it is the only identity that can undo the role -
a teardown that removes it first leaves an orphaned role nothing can delete. That is not hypothetical:
it happened during the 17D spike and needed a fresh Admin service account to recover.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from collector import identity                             # noqa: E402
from collector import provision as pr                      # noqa: E402
from collector.httpclient import RateLimiter                # noqa: E402

GCOM = "https://grafana.com/api"
SSM_REGION = os.environ.get("GCINSIGHT_SSM_REGION", "eu-west-1")


class SsmStoreUnreadable(RuntimeError):
    """The credential store's contents are unknown, so reconciliation must stop.

    A successful empty response is a valid bootstrap state. A failed or malformed paginated read is
    not: treating either one as `{}` makes every healthy stack look as if it needs a new token and also
    gives pruning an incomplete view of the parameters it owns.
    """


class Ledger:
    """Every object this run created, recorded BEFORE the next call is made.

    Name matching is not a substitute. During the 17D spike a teardown that matched on a name substring
    deleted the wrong service account and orphaned a custom role; the ledger is what makes cleanup and
    the delete-refusal check exact.
    """

    def __init__(self) -> None:
        self.admin_sas: dict[str, int] = {}     # slug -> sa id
        self.created_sas: set[tuple[str, int]] = set()

    def record_admin(self, slug: str, sa_id: int) -> None:
        self.admin_sas[slug] = sa_id
        self.created_sas.add((slug, sa_id))

    def record_sa(self, slug: str, sa_id: int) -> None:
        self.created_sas.add((slug, sa_id))

    def created_here(self, slug: str, sa_id: int) -> bool:
        return (slug, sa_id) in self.created_sas


class Gcom:
    """Reads and writes against gcom, on ONE 6 req/s bucket (the limit is per credential).

    Not `ReadOnlyClient`: that class refuses non-GET by construction and keeping it that way is worth
    more than the code reuse.
    """

    def __init__(self, token: str, dry_run: bool, rate: float = 6.0) -> None:
        self._t = token
        self.dry_run = dry_run
        self._limiter = RateLimiter(rate)
        self.reads = 0
        self.writes = 0

    def _call(self, method: str, path: str, body: dict | None = None) -> tuple[int, Any]:
        self._limiter.acquire()
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(f"{GCOM}{path}", data=data, method=method)
        req.add_header("Authorization", f"Bearer {self._t}")
        if data:
            req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=45) as r:
                raw = r.read()
                try:
                    return r.status, json.loads(raw)
                except ValueError:
                    return r.status, None
        except urllib.error.HTTPError as e:
            raw = e.read()
            retry = e.headers.get("Retry-After")
            if e.code == 429 and retry:
                # gcom answers 429 with Retry-After: 8-10. Obeying it beats guessing.
                time.sleep(float(retry) + 1)
                return self._call(method, path, body)
            try:
                return e.code, json.loads(raw)
            except ValueError:
                return e.code, raw[:200].decode(errors="replace")
        except Exception as exc:                                  # noqa: BLE001
            return 0, f"{type(exc).__name__}: {exc}"

    def get(self, path: str) -> tuple[int, Any]:
        self.reads += 1
        return self._call("GET", path)

    def _write(self, method: str, path: str, body: dict | None = None) -> tuple[int, Any]:
        if self.dry_run:
            shown = {k: v for k, v in (body or {}).items()}
            print(f"    DRY-RUN {method} {path} {json.dumps(shown)[:130]}")
            # Mirror the real API: service-account creation answers 201, token creation 200. A stub that
            # returns one status for every POST made the token branch look like a failure in dry runs.
            status = 200 if (method != "POST" or path.endswith("/tokens")) else 201
            return status, {
                "id": 0, "uid": "dry-run", "key": "dry-run", "role": "None", "name": "dry-run",
            }
        self.writes += 1
        return self._call(method, path, body)

    def post(self, path: str, body: dict) -> tuple[int, Any]:
        return self._write("POST", path, body)

    def patch(self, path: str, body: dict) -> tuple[int, Any]:
        return self._write("PATCH", path, body)

    def put(self, path: str, body: dict) -> tuple[int, Any]:
        return self._write("PUT", path, body)

    def delete(self, path: str) -> tuple[int, Any]:
        return self._write("DELETE", path)


class Stack:
    """Calls against one stack's own Grafana API, with a stack-local token."""

    def __init__(self, base_url: str, token: str, dry_run: bool) -> None:
        # The inventory URL is authoritative. A slug is not a hostname contract: custom domains and
        # historical stack names make `https://<slug>.grafana.net` a plausible route to the wrong host.
        if not isinstance(base_url, str) or not base_url.startswith("https://"):
            raise ValueError(f"stack inventory returned an unusable URL: {base_url!r}")
        self.base = base_url.rstrip("/")
        self._t = token
        self.dry_run = dry_run

    NOT_INSPECTED = 0

    def _call(self, method: str, path: str, body: dict | None = None) -> tuple[int, Any]:
        if self.dry_run and self._t == "dry-run":
            # A dry run has no real Admin token, so stack-side state genuinely CANNOT be read. Say so
            # with a distinct status rather than reporting a 401 that looks like a broken credential.
            if method == "GET":
                return self.NOT_INSPECTED, None
        if self.dry_run and method != "GET":
            print(f"    DRY-RUN {method} {self.base}{path} {json.dumps(body or {})[:130]}")
            return 200, {"uid": "dry-run", "permissions": [], "message": "dry-run"}
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(f"{self.base}{path}", data=data, method=method)
        req.add_header("Authorization", f"Bearer {self._t}")
        if data:
            req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=45) as r:
                raw = r.read()
                try:
                    return r.status, json.loads(raw)
                except ValueError:
                    return r.status, None
        except urllib.error.HTTPError as e:
            raw = e.read()
            try:
                return e.code, json.loads(raw)
            except ValueError:
                return e.code, raw[:200].decode(errors="replace")
        except Exception as exc:                                  # noqa: BLE001
            return 0, f"{type(exc).__name__}: {exc}"

    get = lambda self, path: self._call("GET", path)                       # noqa: E731
    post = lambda self, path, body: self._call("POST", path, body)         # noqa: E731
    put = lambda self, path, body: self._call("PUT", path, body)           # noqa: E731
    patch = lambda self, path, body: self._call("PATCH", path, body)       # noqa: E731
    delete = lambda self, path: self._call("DELETE", path)                 # noqa: E731


def ssm_load_all() -> dict[str, dict[str, Any]]:
    """Every stored credential, by slug, in ONE paginated sweep.

    Deliberately not a `get-parameter` per stack: each `aws` invocation is a fresh process at roughly a
    second, so 269 of them cost ~4.5 minutes of a Fargate task's life doing nothing but starting Python.
    `get-parameters-by-path` returns 10 per page, so the whole estate is ~27 calls.

    A parameter whose value will not parse remains present as an invalid-record sentinel. That is the
    state a half-finished write leaves behind: the stack needs a re-mint, while pruning must still know
    that the parameter exists.
    """
    out: dict[str, dict[str, Any]] = {}
    token: str | None = None
    while True:
        cmd = ["aws", "ssm", "get-parameters-by-path", "--path", pr.SSM_PREFIX, "--recursive",
               "--with-decryption", "--region", SSM_REGION, "--output", "json"]
        if token:
            cmd += ["--next-token", token]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            detail = proc.stderr.strip()[:200] or f"aws exited {proc.returncode}"
            raise SsmStoreUnreadable(detail)
        try:
            body = json.loads(proc.stdout or "{}")
        except ValueError as exc:
            raise SsmStoreUnreadable("aws returned invalid JSON") from exc
        if not isinstance(body, dict) or not isinstance(body.get("Parameters"), list):
            raise SsmStoreUnreadable("aws response did not contain a Parameters list")
        for param in body["Parameters"]:
            slug = str(param.get("Name", "")).rsplit("/", 1)[-1]
            try:
                out[slug] = json.loads(param.get("Value") or "")
            except ValueError:
                # This parameter is known to exist but its credential is unusable. Keep the slug in the
                # inventory so pruning still sees the object; `probe` treats the missing token as the
                # repairable, per-stack state it is.
                out[slug] = {"invalid_record": True}
        token = body.get("NextToken")
        if not token:
            return out


def ssm_put(slug: str, record: dict[str, Any], dry_run: bool) -> bool:
    if dry_run:
        keys = ",".join(sorted(k for k in record if k != "token"))
        print(f"    DRY-RUN ssm put {pr.ssm_path(slug)} (keys: {keys}, token redacted)")
        return True
    proc = subprocess.run(
        ["aws", "ssm", "put-parameter", "--name", pr.ssm_path(slug), "--type", "SecureString",
         "--value", json.dumps(record), "--overwrite", "--region", SSM_REGION],
        capture_output=True, text=True,
    )
    if proc.returncode != 0:
        print(f"    ssm put FAILED for {slug}: {proc.stderr.strip()[:200]}", file=sys.stderr)
    return proc.returncode == 0


def ssm_delete(slug: str, dry_run: bool) -> bool:
    if dry_run:
        print(f"    DRY-RUN ssm delete {pr.ssm_path(slug)}")
        return True
    proc = subprocess.run(
        ["aws", "ssm", "delete-parameter", "--name", pr.ssm_path(slug), "--region", SSM_REGION],
        capture_output=True, text=True,
    )
    return proc.returncode == 0


def ssm_list_slugs() -> list[str]:
    """Slugs that currently hold a stored credential."""
    return sorted(ssm_load_all())


def _delete_sa(g: Gcom, ledger: Ledger, slug: str, sa_id: int) -> bool:
    """Refuses any service account this run did not create. The one hard safety check.

    `stack-service-accounts:write` is the narrowest scope gcom offers, so the credential itself cannot
    be prevented from deleting the organisation's own service accounts. This is what prevents it.
    """
    if not ledger.created_here(slug, sa_id):
        raise RuntimeError(
            f"REFUSING to delete service account {sa_id} on {slug}: not created by this run. "
            f"The provisioner is create-only against gcom by design (PLAN 17D-review)."
        )
    status, _ = g.delete(f"/instances/{slug}/api/serviceaccounts/{sa_id}")
    return status == 200


def sweep_leftover_admin(g: Gcom, ledger: Ledger, slug: str, sas: list[dict]) -> int:
    """Remove an Admin identity a previous crashed run left behind.

    Matched on **exact equality** with our own reserved name  -  never a substring, and used for nothing
    but our own leftovers. A substring match is what orphaned a custom role during the 17D spike, and it
    is the same mistake that can leave pilot accounts on live customer stacks.

    The leftover is already inert: its token carries `ADMIN_TOKEN_TTL` (15 min), so a crashed run leaves
    a credential that expires almost immediately. This removes the account itself.
    """
    removed = 0
    for sa in sas:
        if sa.get("name") == pr.ADMIN_SA_NAME:
            # Adopt it into the ledger so the delete check permits exactly this id and no other.
            ledger.record_admin(slug, sa["id"])
            if _delete_sa(g, ledger, slug, sa["id"]):
                removed += 1
    return removed


def list_sas(g: Gcom, slug: str) -> tuple[int, list[dict]]:
    status, body = g.get(f"/instances/{slug}/api/serviceaccounts/search?perpage=300")
    if status != 200 or not isinstance(body, dict):
        return status, []
    return status, body.get("serviceAccounts") or []


def probe(slug: str, stack_url: str, sas: list[dict],
          stored: dict[str, dict[str, Any]], *,
          desired: Any = pr.DESIRED_PAIRS) -> pr.Presence:
    """Phase 1: READ-ONLY. No gcom writes, no Admin identity, no stack-side role inspection.

    Role facts come from the stored token's own effective permissions, which is all that is knowable
    without Admin. `needs_repair` is written to respect that.
    """
    reader = next((s for s in sas if s.get("name") == pr.READER_SA_NAME), None)
    record = stored.get(slug)
    token_status: int | None = None
    # `{action: (scope, ...)}` once a token answers; empty until then. Drift needs the scopes.
    actions: dict[str, tuple[str, ...]] = {}

    if record and record.get("token"):
        status, body = Stack(stack_url, record["token"], dry_run=False).get(
            "/api/access-control/user/permissions")
        token_status = status
        if status == 200 and isinstance(body, dict):
            # The FULL mapping, not `frozenset(body)`. The API answers `{action: [scopes]}`, and drift is
            # compared on (action, scope) pairs - keeping only the keys threw the scopes away and made a
            # grant at the wrong scope indistinguishable from the right one.
            actions = {a: tuple(sc) for a, sc in body.items()}
    return pr.Presence(
        sa_exists=reader is not None,
        secret_exists=bool(record and record.get("token")),
        token_status=token_status,
        basic_role=(reader or {}).get("role"),
        # Only meaningful once we have Admin; phase 1 infers from the token and `needs_repair` ignores it.
        role_exists=bool(actions),
        role_actions=actions,
        assigned=bool(actions) and not pr.role_drift(actions, desired),
    )


def ensure_role(st: Stack, *, write_stack: bool = False) -> tuple[bool, str, str]:
    """Create or reconcile `custom:gcinsight.reader`. Returns (ok, uid, note).

    GET → compare → PUT, never a blind POST: role creation is not idempotent (400 on a duplicate name),
    and the comparison is a SUBSET check on an unordered set so Grafana's self-attached `folders:read`
    does not look like drift and rewrite 273 roles every run.
    """
    desired_permissions = pr.desired_permissions(write_stack=write_stack)
    desired_pairs = pr.permission_pairs(desired_permissions)
    removable_pairs = pr.RETIRED_PAIRS | (
        frozenset() if write_stack else frozenset({pr.WRITE_STACK_PAIR})
    )
    status, roles = st.get("/api/access-control/roles?includeHidden=true")
    if status == Stack.NOT_INSPECTED:
        # Dry run: the gcom write plan above is real, the stack-side plan cannot be known without
        # minting a genuine Admin token, which a dry run must not do.
        return True, "dry-run", "not inspected (dry run  -  needs a real Admin token)"
    if status != 200 or not isinstance(roles, list):
        return False, "", f"role list HTTP {status}"
    existing = next((r for r in roles if r.get("name") == pr.ROLE_NAME), None)

    if existing is None:
        status, created = st.post("/api/access-control/roles", {
            "version": 1, "name": pr.ROLE_NAME, "displayName": pr.ROLE_DISPLAY,
            "group": pr.ROLE_GROUP, "global": False,
            "description": "Read-only collector inventory; datasource queries remain exact-uid scoped.",
            "permissions": [dict(p) for p in desired_permissions],
        })
        if status not in (200, 201) or not isinstance(created, dict):
            return False, "", f"role create HTTP {status}: {str(created)[:120]}"
        return True, created["uid"], "created"

    uid = existing["uid"]
    status, full = st.get(f"/api/access-control/roles/{uid}")
    if status != 200 or not isinstance(full, dict) or not isinstance(full.get("permissions"), list):
        return False, uid, f"role read HTTP {status}"
    permissions = [dict(p) for p in full["permissions"] if isinstance(p, dict) and p.get("action")]
    have: dict[str, list[str]] = {}
    for permission in permissions:
        have.setdefault(permission["action"], []).append(permission.get("scope") or "")
    dangerous = sorted(pr.dangerous_extra_pairs(have, desired_pairs, removable_pairs))
    if dangerous:
        shown = ", ".join(f"{action}@{scope or '*'}" for action, scope in dangerous)
        return False, uid, (
            "REFUSED: the reader role carries unexpected blast-radius permissions: " + shown
        )
    if not pr.role_drift(have, desired_pairs):
        return True, uid, "unchanged"

    # Replacing the role body is the only update API. Preserve every permission we did not declare,
    # except the explicitly retired pairs, including its scope: collapsing extras to `{action}` silently
    # broadens or destroys scoped grants.
    # Dangerous extras were refused above. Benign Grafana-added reads remain preserved.
    retired = [
        permission for permission in permissions
        if (permission["action"], permission.get("scope") or "") in removable_pairs
    ]
    extras = [
        permission for permission in permissions
        if (permission["action"], permission.get("scope") or "") not in
        (desired_pairs | removable_pairs)
    ]
    missing = sorted(pr.missing_pairs(have, desired_pairs))
    status, updated = st.put(f"/api/access-control/roles/{uid}", {
        "version": int(existing.get("version") or 1) + 1,
        "name": pr.ROLE_NAME, "displayName": pr.ROLE_DISPLAY, "group": pr.ROLE_GROUP,
        "global": False,
        "description": "Read-only collector inventory; datasource queries remain exact-uid scoped.",
        # Union, not replace: never strip an action somebody added deliberately on a customer stack.
        "permissions": [dict(p) for p in desired_permissions] + extras,
    })
    if status not in (200, 201):
        return False, uid, f"role update HTTP {status}: {str(updated)[:120]}"
    shown = ",".join(f"{action}@{scope or '<global>'}" for action, scope in missing)
    return True, uid, (
        f"patched (added {len(missing)} pair(s), removed {len(retired)} retired pair(s): "
        f"{shown[:80]})"
    )


def validate_write_stack(
    stacks: list[dict[str, Any]], opted_out: list[str], write_stack_slug: str,
) -> str | None:
    """Reject a stale or ineligible write-stack nomination before any repair can write."""
    matches = [stack for stack in stacks if str(stack.get("slug") or "") == write_stack_slug]
    if len(matches) != 1:
        return "is absent from live inventory" if not matches else "is duplicated in live inventory"
    state = pr.classify(matches[0], opted_out)
    if state != pr.PROVISIONABLE:
        return f"is not provisionable ({state})"
    return None


def verify_reader(g: Gcom, slug: str, stack_url: str, token: str, *,
                  write_stack: bool = False) -> tuple[bool, str]:
    """Re-probe the durable reader after repair; accepted writes are not proof they took effect."""
    status, sas = list_sas(g, slug)
    if status != 200:
        return False, f"service-account verification HTTP {status}"
    desired = pr.permission_pairs(pr.desired_permissions(write_stack=write_stack))
    verified = probe(slug, stack_url, sas, {slug: {"token": token}}, desired=desired)
    if pr.needs_repair(verified, desired):
        return False, (
            f"post-repair probe still needs {pr.plan_action(verified, desired)} "
            f"(sa={verified.sa_exists} secret={verified.secret_exists} "
            f"token={verified.token_status} basic_role={verified.basic_role})"
        )
    return True, "verified"


def repair(g: Gcom, ledger: Ledger, slug: str, stack_url: str, sas: list[dict],
           dry_run: bool, *, presence: pr.Presence,
           existing_token: str | None, write_stack: bool = False) -> pr.Outcome:
    """Phase 2: the only place that writes. Creates a transient Admin identity, repairs, cleans up.

    The Admin service account is deleted in the `finally`, LAST  -  it is the only identity that can undo
    the role, so removing it earlier can orphan one (this happened during the 17D spike).

    `presence` decides whether a reader token has to be minted. It is a required, validated fact: an
    unknown presence must fail before the first write rather than restoring unconditional minting.
    """
    if not isinstance(presence, pr.Presence):
        raise TypeError("repair requires a probed Presence; refusing writes with unknown token state")
    status, admin = g.post(f"/instances/{slug}/api/serviceaccounts",
                           {"name": pr.ADMIN_SA_NAME, "role": "Admin"})
    if status != 201 or not isinstance(admin, dict):
        detail = str(admin)[:140]
        if isinstance(admin, dict) and admin.get("messageId") == "serviceaccounts.ErrAlreadyExists":
            detail = "a previous run left an Admin identity behind; swept next run"
        return pr.Outcome(slug, pr.PROVISIONABLE, "admin_sa_failed", detail)
    # Recorded BEFORE anything else, so a crash from here on is still cleanable.
    ledger.record_admin(slug, admin["id"])
    try:
        status, tok = g.post(
            f"/instances/{slug}/api/serviceaccounts/{admin['id']}/tokens",
            {"name": f"{pr.ADMIN_SA_NAME}-{slug}", "secondsToLive": pr.ADMIN_TOKEN_TTL})
        if status not in (200, 201) or not isinstance(tok, dict):
            return pr.Outcome(slug, pr.PROVISIONABLE, "admin_token_failed", str(tok)[:140])
        st = Stack(stack_url, tok["key"], dry_run=dry_run)

        ok, role_uid, note = ensure_role(st, write_stack=write_stack)
        if not ok:
            # A brand-new stack may not have the Assistant plugin yet, so its actions are unknown to
            # RBAC. Retry next run rather than failing the sweep.
            state = pr.NO_ASSISTANT if "assistant" in note.lower() else pr.PROVISIONABLE
            return pr.Outcome(slug, state, "role_failed", note)

        reader = next((s for s in sas if s.get("name") == pr.READER_SA_NAME), None)
        if reader is None:
            status, created = g.post(f"/instances/{slug}/api/serviceaccounts",
                                     {"name": pr.READER_SA_NAME, "role": "None"})
            if status == 400 and isinstance(created, dict) and \
                    created.get("messageId") == "serviceaccounts.ErrAlreadyExists":
                # Verified behaviour: names cannot duplicate. Re-read rather than treating it as failure.
                _, sas = list_sas(g, slug)
                reader = next((s for s in sas if s.get("name") == pr.READER_SA_NAME), None)
            elif status != 201 or not isinstance(created, dict):
                return pr.Outcome(slug, pr.PROVISIONABLE, "reader_sa_failed", str(created)[:140])
            else:
                reader = created
                ledger.record_sa(slug, created["id"])
        if reader is None:
            return pr.Outcome(slug, pr.PROVISIONABLE, "reader_sa_failed", "not found after create")
        sa_id = reader["id"]

        # The read-only claim depends on this staying `None`.
        if reader.get("role") not in (None, "None"):
            status, changed = st.patch(f"/api/serviceaccounts/{sa_id}", {"role": "None"})
            if status not in (200, 201):
                return pr.Outcome(slug, pr.PROVISIONABLE, "basic_role_failed",
                                  f"HTTP {status}: {str(changed)[:120]}")

        status, assigned = st.post(
            f"/api/access-control/users/{sa_id}/roles", {"roleUid": role_uid, "global": False})
        if status not in (200, 201):
            return pr.Outcome(slug, pr.PROVISIONABLE, "role_assignment_failed",
                              f"HTTP {status}: {str(assigned)[:120]}")

        # A role patch does not invalidate a working credential, so do not mint one. Minting here
        # unconditionally is what would have left an orphaned token on every stack in the estate.
        reader_token = existing_token
        if not pr.needs_token_mint(presence):
            if not reader_token:
                return pr.Outcome(slug, pr.PROVISIONABLE, "verification_failed",
                                  "existing credential was not supplied for post-repair verification")
        else:
            status, minted = g.post(f"/instances/{slug}/api/serviceaccounts/{sa_id}/tokens",
                                    {"name": pr.token_name(slug)})
            if status not in (200, 201) or not isinstance(minted, dict):
                return pr.Outcome(slug, pr.PROVISIONABLE, "token_failed", str(minted)[:140])
            reader_token = minted.get("key")
            if not reader_token:
                return pr.Outcome(slug, pr.PROVISIONABLE, "token_failed",
                                  "mint response did not contain a key")
            minted_id = minted.get("id")
            if minted_id is None:
                return pr.Outcome(slug, pr.PROVISIONABLE, "token_failed",
                                  "mint response did not contain a token id")
            record = {
                "slug": slug, "sa_id": sa_id, "token_id": minted_id,
                "role_uid": role_uid, "token": reader_token,
                "provisioned_at": dt.datetime.now(dt.timezone.utc).isoformat(),
            }
            store_error = ""
            try:
                stored = ssm_put(slug, record, dry_run)
            except Exception as exc:                              # noqa: BLE001
                stored = False
                store_error = f" ({type(exc).__name__}: {exc})"
            if not stored:
                cleanup_status, cleanup_body = st.delete(
                    f"/api/serviceaccounts/{sa_id}/tokens/{minted_id}")
                if cleanup_status not in (200, 204):
                    return pr.Outcome(
                        slug, pr.PROVISIONABLE, "ssm_write_failed",
                        "token minted but NOT stored; exact-token revocation failed "
                        f"with HTTP {cleanup_status}: {str(cleanup_body)[:100]}",
                    )
                return pr.Outcome(slug, pr.PROVISIONABLE, "ssm_write_failed",
                                  f"token minted but NOT stored{store_error}; "
                                  f"token {minted_id} revoked")

        if dry_run:
            return pr.Outcome(slug, pr.PROVISIONABLE, pr.OK,
                              f"role {note}; post-repair probe not available in dry-run")
        verified, detail = verify_reader(
            g, slug, stack_url, reader_token, write_stack=write_stack,
        )
        if not verified:
            return pr.Outcome(slug, pr.PROVISIONABLE, "verification_failed", detail)
        kept = ", existing credential kept" if not pr.needs_token_mint(presence) else ""
        return pr.Outcome(slug, pr.PROVISIONABLE, pr.OK, f"role {note}{kept}; verified")
    finally:
        try:
            _delete_sa(g, ledger, slug, admin["id"])
        except Exception as exc:                                  # noqa: BLE001
            print(f"    WARNING: could not remove the transient Admin identity on {slug}: {exc}",
                  file=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true",
                    help="probe and plan, write nothing to gcom, the stacks or SSM")
    ap.add_argument("--stack", help="one slug, for debugging")
    ap.add_argument("--limit", type=int, help="first N stacks, for debugging")
    ap.add_argument("--no-prune", action="store_true",
                    help="skip deleting stored credentials for stacks that have left the estate")
    args = ap.parse_args(argv)

    try:
        identity.verify_runtime_projection("provisioner")
    except identity.InvalidIdentity as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    token = os.environ.get("GCINSIGHT_PROVISION_TOKEN", "").strip()
    if not token:
        print("error: GCINSIGHT_PROVISION_TOKEN is not set. It is the `gcinsight-provisioner` "
              "policy token (stacks:read + stack-service-accounts:write), NOT the collector's "
              "reader.", file=sys.stderr)
        return 2

    org_id = os.environ.get("GCINSIGHT_ORG_ID", "").strip()
    if not org_id:
        print("error: GCINSIGHT_ORG_ID is not set (Grafana Cloud organisation to provision)",
              file=sys.stderr)
        return 2

    write_stack_slug = os.environ.get("GCINSIGHT_WRITE_STACK", "").strip()
    if not write_stack_slug:
        print("error: GCINSIGHT_WRITE_STACK is not set (the only reader allowed to query "
              "grafanacloud-usage)", file=sys.stderr)
        return 2

    g = Gcom(token, dry_run=args.dry_run)
    ledger = Ledger()

    status, body = g.get(f"/instances?orgId={org_id}")
    if status != 200 or not isinstance(body, dict):
        print(f"error: inventory HTTP {status}", file=sys.stderr)
        return 1
    stacks = body.get("items") or []
    print(f"estate: {len(stacks)} stacks discovered")

    opted_out = [s for s in os.environ.get("GCINSIGHT_OPT_OUT", "").split(",") if s.strip()]
    if opted_out:
        print(f"opt-out list: {', '.join(opted_out)}")

    write_stack_error = validate_write_stack(stacks, opted_out, write_stack_slug)
    if write_stack_error:
        print(f"error: GCINSIGHT_WRITE_STACK {write_stack_error}", file=sys.stderr)
        return 2

    if args.stack:
        stacks = [s for s in stacks if str(s.get("slug")) == args.stack]
    elif args.limit:
        stacks = stacks[: args.limit]

    try:
        stored = ssm_load_all()
    except SsmStoreUnreadable as exc:
        print(f"error: credential store unreadable; refusing repair and prune: {exc}",
              file=sys.stderr)
        return 1
    print(f"credential store: {len(stored)} stack(s) already hold a token")

    outcomes: list[pr.Outcome] = []
    for s in stacks:
        slug = str(s.get("slug"))
        state = pr.classify(s, opted_out)
        if state != pr.PROVISIONABLE:
            outcomes.append(pr.Outcome(slug, state, pr.OK, "skipped"))
            continue

        stack_url = s.get("url")
        if not isinstance(stack_url, str) or not stack_url.startswith("https://"):
            outcomes.append(pr.Outcome(
                slug, pr.PROVISIONABLE, "invalid_stack_url",
                "inventory did not provide an authoritative HTTPS stack URL",
            ))
            continue

        status, sas = list_sas(g, slug)
        if status != 200:
            outcomes.append(pr.Outcome(slug, pr.PROVISIONABLE, "sa_list_failed", f"HTTP {status}"))
            continue

        swept = sweep_leftover_admin(g, ledger, slug, sas)
        if swept:
            print(f"  {slug}: removed {swept} leftover Admin identity(ies) from an earlier run")
            _, sas = list_sas(g, slug)

        is_write_stack = slug == write_stack_slug
        desired = pr.permission_pairs(pr.desired_permissions(write_stack=is_write_stack))
        presence = probe(slug, stack_url, sas, stored, desired=desired)
        if not pr.needs_repair(presence, desired):
            outcomes.append(pr.Outcome(slug, pr.PROVISIONABLE, pr.OK, "already provisioned"))
            continue

        action = pr.plan_action(presence, desired)
        print(f"  {slug}: {action} (sa={presence.sa_exists} secret={presence.secret_exists} "
              f"token={presence.token_status} basic_role={presence.basic_role})")
        if action == pr.UNEXPLAINED_403:
            outcomes.append(pr.Outcome(
                slug, pr.PROVISIONABLE, pr.UNEXPLAINED_403,
                "credential authenticates and the role carries every declared action, and the API "
                "still refuses  -  needs a human, do not re-mint"))
            continue
        record = stored.get(slug) or {}
        outcomes.append(repair(
            g, ledger, slug, stack_url, sas, args.dry_run,
            presence=presence, existing_token=record.get("token"), write_stack=is_write_stack,
        ))

    if not args.no_prune and not args.stack and not args.limit:
        gone = pr.prune_targets(sorted(stored), [str(s.get("slug")) for s in
                                                 (body.get("items") or [])])
        for slug in gone:
            # No gcom delete: a stack that has left took its service accounts with it.
            print(f"  prune {slug}: stack no longer in the estate")
            ssm_delete(slug, args.dry_run)
        if gone:
            print(f"pruned {len(gone)} stored credential(s)")

    by_state: dict[str, int] = {}
    for o in outcomes:
        key = o.state if o.state != pr.PROVISIONABLE else f"provisionable/{o.action}"
        by_state[key] = by_state.get(key, 0) + 1
    print("\nsummary: " + ", ".join(f"{k}={v}" for k, v in sorted(by_state.items())))
    print(f"gcom: {g.reads} reads, {g.writes} writes")
    for name, labels, value in pr.coverage_metrics(outcomes):
        print(f"  {name}{labels or ''} = {value}")
    failed = [o for o in outcomes if o.action != pr.OK]
    if failed:
        print(f"\n{len(failed)} stack(s) not provisioned:")
        for o in failed[:20]:
            print(f"  {o.slug}: {o.action}  -  {o.detail}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
