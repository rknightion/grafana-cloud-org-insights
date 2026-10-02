"""Count the approved forecasting jobs route, retaining no job details.

Only this route accepts transient job-top-level grafanaApiKey receipt. This is
not memory secrecy, universal visibility, or a narrow-credential guarantee.
"""
from collections.abc import Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable

from collector.httpclient import ReadOnlyClient
from collector.sources.resource_schema import UnsafeSchema, guard_resource
from collector.sources.stack_catalog import validated_base_url

PATH = "/api/plugins/grafana-ml-app/resources/manage/api/v1/jobs"
MAX_JOBS = 100_000


def fetch_ml_jobs(client: ReadOnlyClient, stack: Mapping[str, Any], reader: str) -> dict[str, Any]:
    base, error = validated_base_url(stack)
    if error:
        return {"available": False, "reason": "invalid_url"}
    if not reader:
        return {"available": False, "reason": "no_credential"}
    try:
        response = client.get(base + PATH, bearer=reader, guarded=True)
        if response.status != 200:
            return {"available": False, "reason": "unreadable"}
        body = response.json()
        # The witnessed envelope has no pagination or partial-result contract.
        if (not isinstance(body, dict) or set(body) != {"status", "data"}
                or body["status"] != "success" or not isinstance(body["data"], list)
                or len(body["data"]) > MAX_JOBS):
            return {"available": False, "reason": "invalid_response"}
        for job in body["data"]:
            if not isinstance(job, dict):
                return {"available": False, "reason": "invalid_response"}
            # Exact field, exact depth only. Every other credential field, including
            # nested grafanaApiKey, remains rejected by the global structural fence.
            job.pop("grafanaApiKey", None)
        guard_resource(body)
        if any(not isinstance(job.get("id"), str) or not job["id"].strip()
               for job in body["data"]):
            return {"available": False, "reason": "invalid_response"}
        return {"available": True, "job_count": len(body["data"])}
    except UnsafeSchema:
        return {"available": False, "reason": "unsafe_schema"}
    except Exception:  # noqa: BLE001 - upstream exceptions may contain keys or private job content
        return {"available": False, "reason": "transport_error"}


def probe_all(client: ReadOnlyClient, stacks: Sequence[Mapping[str, Any]],
              credentials: Mapping[str, Mapping[str, Any]], *, concurrency: int = 8,
              on_error: Callable[[str, str], None] | None = None) -> dict[str, Any]:
    """Left-join credentials onto the fresh inventory, never the reverse."""
    def probe(stack):
        slug = str(stack["slug"])
        token = str((credentials.get(slug) or {}).get("token") or "")
        result = fetch_ml_jobs(client, stack, token)
        if not result["available"] and on_error:
            on_error(slug, "ml_jobs: " + result["reason"])
        return slug, result

    selected = [s for s in stacks if s.get("slug") and s.get("status") != "paused"]
    with ThreadPoolExecutor(max_workers=max(1, concurrency)) as pool:
        return dict(pool.map(probe, selected))
