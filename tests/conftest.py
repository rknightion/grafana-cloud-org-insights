"""Test-wide configuration.

`collector.dashboards.build` resolves its view source at import time, so this has to run before any
test module imports it. pytest loads `conftest.py` first, which is exactly the hook that guarantees it.

Pointing the suite at `testdata/views/` is what makes the dashboard tests runnable with no AWS
credentials and no deployed bucket. Those views are composed from `tests/fixtures/compose_inputs.json`
by the pillars themselves, so a column spec asserted here is one the code really produces rather than
one somebody wrote down.
"""

from __future__ import annotations

import os
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent

os.environ.setdefault("GCINSIGHT_VIEWS_DIR", str(ROOT / "testdata" / "views"))
# The Infinity datasource URL is baked into a published dashboard, so it cannot fall back to a local
# directory. A placeholder keeps `bucket_url()` answerable in tests without implying a real bucket.
os.environ.setdefault("GCINSIGHT_S3_BUCKET", "gcinsight-test-bucket")
