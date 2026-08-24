"""Per-stack Grafana Assistant reads (Pillar I, PLAN 17D/17E). Aggregates and metadata ONLY.

Auth is the persistent per-stack reader token from `collector/credentials.py` - basic role `None` plus
`custom:gcinsight.reader`, 11 read actions, writes provably refused (PLAN 17D). One token per stack,
one host per stack, so this sweep never touches gcom and is outside its 6 req/s cap entirely.

## The route, and it is the only one

    https://<slug>.grafana.net/api/plugins/grafana-assistant-app/resources/<path>

The plugin-resource proxy. `regionAssistantUrl` 401s and `https://<slug>.grafana.net/api/v1/...` 404s.

## Trap: the usage endpoints take epoch MILLISECONDS

`from`/`to` → 400. ISO-8601 → 422. **Epoch SECONDS → HTTP 200 with every value zero** - no error, no
warning, an estate that looks like it has never used Assistant. `window()` is the only place the bound is
computed and `tests/test_assistant.py` pins the magnitude, because this failure mode is invisible.

## What is deliberately NOT collected

- **Skill `body`, rule `ruleContent`, MCP `configuration` and `customHeaders`** - prompts, instructions
  and endpoint URLs. `strip_object` keeps a fixed metadata allow-list, so a field the API adds later is
  dropped by default rather than collected by default.
- **`/api/v2/investigations`** is not called at all. It returns `total: 0` for a service account by
  product design (the SA owns no investigation and is in no team), so 273 calls a day would buy a
  guaranteed zero. Investigation COUNTS come from `usage/investigations`, split assistant vs user.
- **`/api/v1/usage/tokens`** is not called: `hero-stats` already carries `totalTokens` for the same
  window, split chat vs investigation.
- **`/api/v1/watcher-agents`** is not called. It 403s `authenticated user identity does not match request
  user` for a full **Admin**, so it is product-blocked for service-account identities and no role fixes
  it. Recorded as not measurable; never retried with a wider role.

## Two counts that are not what they look like

- **Every inventory total is TENANT-SCOPED.** A user-scoped ("Just me") skill or rule is invisible to
  every identity but its owner - including a full Admin - and `pagination.total` reads 0, so a collector
  cannot even learn one exists. Call it "tenant skills", never "skills".
- **`active-users` is a DAILY bucket, so its values do not sum to a user count.** Measured on obs-hub-dev:
  daily max 1, `hero-stats.totalActiveUsers` 5. The deduplicated figure is the hero stat; the daily frame
  is used only for `days_active`, which is how a sustained rollout is told from a one-day spike.

## Categories do not reconcile, and by a wide margin

`chat-categories` summed against `hero-stats.totalUserMessages`, measured 2026-08-20: obs-hub-dev 36/49
(73%), stack024 142/684 (21%), stack023 32/423 (8%), stack152 14/369 (4%). So the categorised share
is a **minority of traffic on most stacks**. Every category figure carries `uncategorised` alongside it
and no consumer may normalise to 100% of messages - only to the categorised subset, said out loud.
"""

from __future__ import annotations

import datetime as dt
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, Mapping, Sequence

from collector.httpclient import ReadOnlyClient

# 30 days: these are rolling-window aggregates and the shortest window that makes a monthly-cadence
# adoption figure meaningful. Also what every live measurement in CAPABILITIES.md was taken over.
WINDOW_DAYS = 30

# Detail rows come back paginated with a default `limit` of 20. Counts use `pagination.total`, so paging
# is only about the detail table; 200 is far above the estate's observed maximum of 3 tenant objects.
DETAIL_LIMIT = 200

BASE = "https://{slug}.grafana.net/api/plugins/grafana-assistant-app/resources"

# The four tenant-scoped inventories, and the response key each nests its list under.
INVENTORIES: dict[str, str] = {
    "skills": "skills",
    "rules": "rules",
    "automations": "automations",
    "integrations": "integrations",
}

# Metadata worth keeping, per inventory kind. An ALLOW-list, not a deny-list: the point is that a field
# the Assistant API adds in a future release is dropped by default. `body`, `ruleContent`,
# `configuration` and `customHeaders` are the ones this exists to exclude.
OBJECT_FIELDS: tuple[str, ...] = (
    "name", "enabled", "scope", "type", "createdBy", "created", "modified", "authenticationFailed",
)

# Why a stack produced no Assistant data. A closed vocabulary - it reaches a view column and the
# coverage classification, so an open-ended string would make both unreadable.
NO_CREDENTIAL = "no_credential"
UNAUTHORISED = "token_401"
FORBIDDEN = "forbidden_403"
PLUGIN_ABSENT = "plugin_absent_404"
HTTP_ERROR = "http_error"
TRANSPORT_ERROR = "transport_error"

# Statuses worth ONE re-attempt on the first call of a stack, after a short pause.
#
# **A 403 from this proxy can be transient - measured, and it matters.** On 2026-08-20 `stack143`
# returned 403 on `hero-stats` during a full sweep and answered **200 to the identical request four
# minutes later**, with the same stored token, 12 effective permissions and 9 Assistant permissions; the
# provisioner independently reported the stack fully provisioned. So a 403 here does NOT prove a
# permission fault the way `PLAN 17D-review` A3 established for the gcom-side checks, and treating one as
# a credential gap would blip the coverage count for a fault that does not exist.
#
# 401 is excluded deliberately: a revoked token will still be revoked in three seconds, and re-asking
# would only slow the sweep. 404 is excluded because a missing plugin does not appear in three seconds
# either. Cloudflare's 52x family is in because the collector's own retry list stops at 504 and the real
# failure observed on this host family was a **522**.
FIRST_CALL_RETRY_STATUSES = frozenset({403, 408, 425, 429, 500, 502, 503, 504, 520, 521, 522, 523, 524})
FIRST_CALL_RETRY_DELAY = 3.0

WATCHERS_NOT_MEASURABLE = (
    "/api/v1/watcher-agents 403s `authenticated user identity does not match request user` for a full "
    "Admin service account. Product-blocked for service-account identities, not a permission gap."
)
INVESTIGATION_INVENTORY_NOT_MEASURABLE = (
    "/api/v2/investigations returns total 0 for a service account, which owns no investigation and is in "
    "no Grafana team. Counts are collectable; the list is not."
)
USER_SCOPED_NOT_MEASURABLE = (
    "User-scoped (\"Just me\") skills and rules are invisible to every identity but their owner, "
    "including a full Admin, and pagination.total reads 0 - not even countable."
)


# --- Pure parsing ---------------------------------------------------------------------------------

def epoch_ms(when: dt.datetime) -> int:
    """MILLISECONDS. Seconds are accepted by the API and answered with zeros - see the module docstring."""
    return int(when.timestamp() * 1000)


def window(now: dt.datetime | None = None, days: int = WINDOW_DAYS) -> tuple[int, int]:
    now = now or dt.datetime.now(dt.timezone.utc)
    return epoch_ms(now - dt.timedelta(days=days)), epoch_ms(now)


def frame_sums(body: Mapping[str, Any] | None) -> dict[str, float]:
    """Sum every numeric field of a Grafana dataframe, keyed by field name.

    Shape (verified live): `{"data": {"schema": {"fields": [{"name","type"}]},
    "data": {"values": [[...], ...]}}}` - parallel arrays, `values[i]` belongs to `fields[i]`.

    **A `time`-only frame is the API's way of saying zero**, and it is what `usage/investigations`
    returns on a stack with none. That yields `{}` here, which the caller must treat as an absent
    breakdown rather than as a set of zeros.
    """
    frame = ((body or {}).get("data") or {})
    fields = ((frame.get("schema") or {}).get("fields") or [])
    values = ((frame.get("data") or {}).get("values") or [])
    out: dict[str, float] = {}
    for index, field in enumerate(fields):
        if not isinstance(field, Mapping) or field.get("type") == "time":
            continue
        if index >= len(values):
            continue
        column = values[index] or []
        out[str(field.get("name"))] = float(sum(v for v in column if isinstance(v, (int, float))))
    return out


def days_active(body: Mapping[str, Any] | None) -> int:
    """Buckets with a non-zero value. `active-users` is daily, so this is 'days anyone used Assistant'."""
    frame = ((body or {}).get("data") or {})
    fields = ((frame.get("schema") or {}).get("fields") or [])
    values = ((frame.get("data") or {}).get("values") or [])
    for index, field in enumerate(fields):
        if isinstance(field, Mapping) and field.get("type") != "time" and index < len(values):
            return len([v for v in (values[index] or []) if isinstance(v, (int, float)) and v > 0])
    return 0


def split_category(field_name: str) -> tuple[str, str]:
    """`"Investigate (cli)"` -> `("Investigate", "cli")`.

    The field set is whatever that stack actually used, and it differs per stack: 15 fields on stack024, 4
    on stack152, with surfaces `web`, `cli`, `a2a`, `automation` and `lodestone` and categories
    including `Errors`. **Never hardcode a column list** - enumerate what came back.

    A name that does not carry a parenthesised surface keeps the whole string as the category and reports
    the surface as `unknown`, so an API change shows up as an odd row rather than as silence.
    """
    text = str(field_name).strip()
    if text.endswith(")") and "(" in text:
        head, _, tail = text.rpartition("(")
        surface = tail[:-1].strip()
        if head.strip() and surface:
            return head.strip(), surface
    return text, "unknown"


# Surfaces a human drives directly. Everything else is machine-driven - a CLI session, an
# agent-to-agent call, an automation or a Lodestone run. This is the human-vs-machine split, and it is a
# signal that exists nowhere in `grafanacloud-usage`.
HUMAN_SURFACES = frozenset({"web"})


def machine_share(categories: Mapping[str, float]) -> float | None:
    """Share of CATEGORISED messages that came from a non-`web` surface.

    Deliberately **not** a share of all messages: the categorised subset is a minority of traffic on
    most stacks, so the denominator has to be what was actually classified. `None` when nothing was
    categorised - a zero would read as "all human".
    """
    total = sum(categories.values())
    if total <= 0:
        return None
    machine = sum(v for name, v in categories.items() if split_category(name)[1] not in HUMAN_SURFACES)
    return round(machine / total, 4)


def object_count(body: Mapping[str, Any] | None, list_key: str) -> int:
    """`pagination.total` where the endpoint offers it, else the list length.

    `/api/v1/automations` returns no `pagination` block at all, so the length is the only count - which
    is why this is not simply `body["data"]["pagination"]["total"]`.
    """
    data = ((body or {}).get("data") or {})
    pagination = data.get("pagination")
    if isinstance(pagination, Mapping) and isinstance(pagination.get("total"), (int, float)):
        return int(pagination["total"])
    items = data.get(list_key)
    return len(items) if isinstance(items, list) else 0


def strip_object(item: Mapping[str, Any], kind: str) -> dict[str, Any]:
    """Metadata allow-list. Drops prompts, instructions, MCP URLs and headers by construction."""
    out: dict[str, Any] = {"kind": kind}
    for key in OBJECT_FIELDS:
        if key in item:
            out[key] = item[key]
    return out


def objects_of(body: Mapping[str, Any] | None, list_key: str, kind: str) -> list[dict[str, Any]]:
    items = ((body or {}).get("data") or {}).get(list_key)
    if not isinstance(items, list):
        return []
    return [strip_object(i, kind) for i in items if isinstance(i, Mapping)]


def summarise_stack(
    slug: str,
    hero: Mapping[str, Any],
    categories: Mapping[str, float],
    investigations: Mapping[str, float],
    daily_days: int,
    inventories: Mapping[str, int],
    objects: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Fold one stack's raw payloads into the record every consumer reads."""
    messages = int(hero.get("totalUserMessages") or 0)
    categorised = int(sum(categories.values()))
    users = int(hero.get("totalActiveUsers") or 0)
    tokens = int(hero.get("totalTokens") or 0)
    tenant_objects = sum(int(v) for v in inventories.values())
    return {
        "available": True,
        "slug": slug,
        "window_days": WINDOW_DAYS,
        "active_users": users,
        "days_active": daily_days,
        "messages": messages,
        "tokens": tokens,
        "chat_tokens": int(hero.get("totalChatTokens") or 0),
        "investigation_tokens": int(hero.get("totalInvestigationTokens") or 0),
        "investigations_created": int(hero.get("totalInvestigationsCreated") or 0),
        # Field names are `assistant (created)` / `user (created)` and are ABSENT when zero.
        "investigations_by_origin": {
            split_category(name)[0]: int(value) for name, value in investigations.items()
        },
        "categories": {name: int(value) for name, value in categories.items()},
        "messages_categorised": categorised,
        # Clamped, and the overflow flagged rather than hidden. It DOES happen: measured 2026-08-20,
        # `stack131` reported 0 messages against 8 categorised and `stack025` 0 against 1. So
        # the two endpoints genuinely disagree in both directions and the clamp must not swallow it.
        "messages_uncategorised": max(0, messages - categorised),
        "categorised_exceeds_total": categorised > messages,
        "machine_share_of_categorised": machine_share(categories),
        "tokens_per_active_user": round(tokens / users, 1) if users else None,
        "tenant": dict(inventories),
        "tenant_objects": tenant_objects,
        "tenant_objects_detail": list(objects),
        "watchers_measurable": False,
        "investigation_inventory_measurable": False,
    }


def unavailable(slug: str, reason: str, detail: str = "") -> dict[str, Any]:
    """A stack that produced nothing, with WHY. 401 and 403 need different repairs (PLAN 17D-review A3)."""
    return {"available": False, "slug": slug, "reason": reason, "detail": detail}


# --- I/O ------------------------------------------------------------------------------------------

def _get(client: ReadOnlyClient, slug: str, token: str, path: str,
         params: Mapping[str, object] | None = None):
    return client.get(f"{BASE.format(slug=slug)}/{path}", params=params, bearer=token)


class AssistantUnavailable(RuntimeError):
    """A stack answered in a way that means 'no data from here', carrying the closed reason."""

    def __init__(self, reason: str, detail: str = "") -> None:
        super().__init__(f"{reason}: {detail}" if detail else reason)
        self.reason = reason
        self.detail = detail


def _reason_for(status: int) -> str:
    return {401: UNAUTHORISED, 403: FORBIDDEN, 404: PLUGIN_ABSENT}.get(status, HTTP_ERROR)


def probe_stack(client: ReadOnlyClient, slug: str, token: str,
                now: dt.datetime | None = None,
                sleep: Callable[[float], None] = time.sleep) -> dict[str, Any]:
    """Eight GETs against one host. Raises `AssistantUnavailable` if the FIRST call is refused twice.

    The first call decides whether the stack is readable at all: if `hero-stats` is refused, the other
    seven would only repeat the same refusal. It gets ONE re-attempt first, because both failures this
    sweep has actually produced against a fully provisioned stack were transient - a Cloudflare 522 and a
    403 that answered 200 four minutes later. Once past that gate, a later individual failure degrades
    that section rather than the stack: a stack with usage and an unreadable inventory is still worth
    having.
    """
    start, end = window(now)
    usage_params = {"start": start, "end": end}

    resp = _get(client, slug, token, "api/v1/usage/hero-stats", usage_params)
    if not resp.ok and resp.status in FIRST_CALL_RETRY_STATUSES:
        sleep(FIRST_CALL_RETRY_DELAY)
        resp = _get(client, slug, token, "api/v1/usage/hero-stats", usage_params)
    if not resp.ok:
        raise AssistantUnavailable(_reason_for(resp.status), f"hero-stats HTTP {resp.status}")
    hero = (resp.json() or {}).get("data") or {}

    def soft(path: str, params: Mapping[str, object] | None = None) -> dict[str, Any] | None:
        r = _get(client, slug, token, path, params)
        return r.json() if r.ok else None

    categories = frame_sums(soft("api/v1/usage/chat-categories", usage_params))
    investigations = frame_sums(soft("api/v1/usage/investigations", usage_params))
    daily = days_active(soft("api/v1/usage/active-users", usage_params))

    counts: dict[str, int] = {}
    objects: list[dict[str, Any]] = []
    for kind, list_key in INVENTORIES.items():
        body = soft(f"api/v1/{kind}", {"limit": DETAIL_LIMIT})
        counts[kind] = object_count(body, list_key)
        objects.extend(objects_of(body, list_key, kind))

    return summarise_stack(slug, hero, categories, investigations, daily, counts, objects)


def probe_all(
    client: ReadOnlyClient,
    stacks: Sequence[Mapping[str, Any]],
    credentials: Mapping[str, Mapping[str, Any]],
    *,
    concurrency: int = 12,
    now: dt.datetime | None = None,
    on_error: Callable[[str, str], None] | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> dict[str, Any]:
    """Iterate the LIVE INVENTORY and look each stack's credential up - never the other way round.

    The golden rule in one line (CLAUDE.md): a stack that appeared this morning gets a row with
    `reason: no_credential` until the 03:35 provisioner reaches it, and a stack that left the estate has
    no row at all whatever the credential store still holds. Iterating `credentials` would invert both.

    **This function takes no `Coverage`, on purpose.** A tier's coverage means "did we get this stack's
    detail from gcom", and the T2 sweep has already recorded ok/failure for the same slugs against the
    same object; a second source writing to it would push `scanned + skipped` past `total` and make
    `coverage_ratio` mean two things at once. Every outcome here is reported per stack in the returned
    record instead, and a missing credential is a PROVISIONING state with its own gauge, view and alert
    rather than a scan failure at all.
    """
    results: dict[str, Any] = {}

    def one(stack: Mapping[str, Any]) -> None:
        slug = str(stack.get("slug"))
        if stack.get("status") == "paused":
            # Paused stacks 403 on the service-account endpoint itself, so they are not provisionable
            # rather than unprovisioned. `pillars/ai.missing_slugs` classifies them out of the gap set;
            # counting them as missing would fire the alert for ever on automated-test leftovers.
            return
        record = credentials.get(slug) or {}
        token = str(record.get("token") or "")
        if not token:
            results[slug] = unavailable(slug, NO_CREDENTIAL,
                                        "no stored token - the daily provisioner has not reached it yet")
            return
        try:
            results[slug] = probe_stack(client, slug, token, now=now, sleep=sleep)
        except AssistantUnavailable as exc:
            results[slug] = unavailable(slug, exc.reason, exc.detail)
            if on_error:
                on_error(slug, f"{exc.reason}: {exc.detail}")
        except Exception as exc:  # noqa: BLE001 - a transport failure is one stack, not the sweep
            results[slug] = unavailable(slug, TRANSPORT_ERROR, f"{type(exc).__name__}: {exc}")
            if on_error:
                on_error(slug, f"{type(exc).__name__}: {exc}")

    with ThreadPoolExecutor(max_workers=max(1, concurrency)) as pool:
        list(pool.map(one, stacks))
    return results
