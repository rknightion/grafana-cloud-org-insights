# Minimized synthetic Faro app shape

`faro_apps.json` is a synthetic bare-array projection with two synthetic identifiers and the permitted
`appType` key shape. No live app details or identifiers are retained. The admission packet records
an existing two-app staff population with matching exact-two-pair basic-None reader and Admin counts;
all witness service accounts, roles and tokens were removed by the root. This lane made no live calls.
The installed public AppType export defines `web` and `mobile`; other or missing strings map to
`unknown`, never to a browser/OS guess. This is not universal visibility or strict-minimality proof.

`tests/test_faro_apps.py` adds synthetic private canaries to the projection and exercises the real
GET-only client, selected T2 gather, compose, hydration filter, S3 envelope and assembled Usage panel.
The compose-fixture generator's `--synthetic-faro` path appends only minimized counts/types while
preserving upstream SEG, Synthetic and IRM inputs and formatting. No live exporter is called.
