# SLO and Adaptive Traces resource fences

These count-only readers select the optional guarded GET path in `collector/httpclient.py`.
The normal client remains GET-only with bounded retries. All shared-client attempts now fence the
caller's wait through `collector.netbound`; this is not hard cancellation or a general response-byte cap.

- Both sources validate the inventory origin as HTTPS, without userinfo, non-root paths,
  whitespace, query or fragment. They do not derive a hostname or follow any redirect,
  including a same-origin redirect to an unapproved route.
- Body permission is limited to the SLO list and Adaptive config, policies and recommendations.
  Adaptive first probes the fixed plugin-proxy `health` route in **status-only** mode: no success
  or error body read, JSON decode or body output. Health 404/500 does not gate the other domains
  and says nothing about enablement or resource absence.
- Guarded requests make one attempt, with a total budget of the lesser of request timeout and
  remaining caller deadline, including host queue/rate-limit waits. Header/body receives clamp
  their socket timeout to the remaining budget. Available-chunk reads check elapsed time rather
  than waiting to fill a large buffer. TCP/TLS setup enters with the remaining socket timeout;
  `collector.netbound` also fences the caller's wait across platform DNS and complete reads.
  Underlying DNS/TCP/TLS or body reads can survive that wait: Python cannot interrupt these
  operations. The process-wide pool admits at most 32 operations and has at most 32 daemon
  workers including survivors, with no replacement workers. A surviving GET keeps its host
  concurrency slot until completion. Exhaustion times out new admission; abandoned queued
  work is cancelled. Survivors may retain credentials and transient response bytes until
  completion or process exit. This is not a hard process-level watchdog or an erasure guarantee.
- Successful JSON bodies are limited to 2 MiB, plus one overflow-detection byte. Oversize,
  incomplete Content-Length, malformed JSON and expired responses never produce truncated
  success. HTTP error/redirect bodies are closed without reading. JSON parsing is bounded by
  bytes but is subsequent local work, outside the network deadline.
- A structural guard rejects known credential-bearing field names, normalizing case, underscores
  and hyphens. It bounds depth (32), total nodes (100,000) and field-name length (256). Malformed
  structures fail closed. It does not inspect strings, expressions, scripts or policy semantics.
  `unsafe_schema` is a fixed safe defer reason, not a healthy count or measured zero.
  Adaptive's independently valid domains remain available when another domain is deferred.

The first response has already entered memory before the structural guard can reject it. The
field-name list is not a secret detector or a guarantee that arbitrary JSON is nonsecret; unknown
credential field names and credentials embedded in values are outside it. Repeated scans will defer
again, not maintain a dynamic denylist or inventory/config store. Only minimized scalar projections
leave these source functions. No permission expansion, detail routes, metric series or broader
ML/Faro/IRM credential lists are authorized by these transport/schema fences.

## Other source paths and limits

The ordinary GET client, label-risk native Pyroscope reads, legacy
`dataplane._connect_rpc` reads and the no-client `usage_insights._query` seam all use the same
caller-wait helper. Legacy helper timeouts are not automatically the tier's remaining budget;
this does not strengthen their route guards or approve new POST methods. Label risk has its own
response-byte cap; ordinary and legacy reads do not gain a response-memory bound from this helper.
Loki push and Mimir remote_write are publication transports and remain outside the source fence.
Daemon shutdown does not wait for surviving reads. A caller timeout proves bounded waiting, not
termination of DNS, TCP/TLS, a slow body read, or cleanup of its credentials from process memory.
