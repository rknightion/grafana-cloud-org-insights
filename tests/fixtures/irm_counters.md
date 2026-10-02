# Synthetic IRM projected-counter schema

Constructed from the admitted route schema, not a live export. The opaque key is a privacy sentinel. Exact nonnegative integer `alerts_count` and `alert_groups_count` values are validated and then discarded. Zero-activity entries are still configured integrations. The empty map is a measured configured count of zero; malformed or failed reads are unavailable.

`tests/test_irm_integrations.py` sends this through the real GET-only client, scan gatherer, compose and S3 view publisher. No live identifiers, tokens or configuration are present.
