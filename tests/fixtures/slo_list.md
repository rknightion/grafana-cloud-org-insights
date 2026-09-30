# Synthetic captured SLO list

`slo_list.json` preserves the field and nesting shapes of three objects from the
accepted D1a positive reader/Admin control captured on 2026-09-30. It is not an
invented API response or a measurement of the synthetic estate. All string values
except the bounded `api`, `asserts`, `mimir`, `created` and `updated` classification
values were replaced with `synthetic-sensitive`. Numeric and boolean values and
key names were preserved. No identifiers, expressions, annotations or label values
from the development stack remain.

`tests/test_slo_inventory.py` reads this artifact through the real GET-only client
and checks minimization at the source and composed view boundaries. Its separate
edge cases are deliberately synthetic branching inputs, not captured contracts.
The SLO entry appended to `compose_inputs.json` is this artifact's minimized
projection joined to an existing synthetic stack, used to re-derive hydration.
