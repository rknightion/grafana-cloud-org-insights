# Synthetic Monitoring list contract

This minimized fixture reconstructs the bare array/object shape from the anonymized staff proxy
check/probe witnesses captured on 2026-10-02: checks have boolean `enabled` and an object `settings`
keyed by check kind; probes have boolean `public`. The positive check sample has four items, with
HTTP and ping settings. Probe cardinality here is deliberately illustrative, not a staff measurement.
The datasource UID uses a synthetic placeholder and the plugin type is public vendor vocabulary.

No original target, name, job, ID, tenant, location, label, script, header or URL is retained.
Tests add synthetic sensitive canaries transiently to prove they cannot escape the source boundary.
`tests/test_synthetic.py` uses these arrays through the real GET client, composition and hydration;
`compose_inputs.json` contains only the resulting minimized counts for a synthetic inventory stack.
