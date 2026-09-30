# SLO and Adaptive Traces resource fences

These count-only readers select the optional guarded GET path in `collector/httpclient.py`.
The normal client remains GET-only and retains its existing default transport/retry behavior.

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
  platform DNS resolution is not interruptible by urllib, and initial connection setup can
  overrun the total budget by its blocking platform/socket operations. This is not a hard
  process-level watchdog. Once setup returns, an expired request fails rather than publishing.
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
ML/Faro/IRM credential lists are authorized by this transport/schema repair.
