# Legacy Synthetic permission golden

`synthetic_legacy_permissions.json` was captured offline by executing `collector/provision.py`
from v0.4.3 source SHA `8e7423045ee0efa23619ea8e8b5a4af3d1a6f338`, obtained with
`git show <SHA>:collector/provision.py`. It was compiled into a registered `types.ModuleType`
so its dataclass definitions execute normally. No current permission function produced this golden.

Enumerate the Cartesian product of `write_stack=(False, True)` and both booleans selecting `slo`
and `synthetic-monitoring`. For each combination call the original `desired_permissions` and
`removable_pairs`; normalize the desired permissions into `{action: [scopes]}` and call the original
`dangerous_extra_pairs(have, permission_pairs(desired), removable)`. Serialize the ordered desired
permissions and sorted removable/dangerous pairs. These are public action and scope names, not
customer identifiers. No network, deployment, AWS or credential lookup is involved.

`tests/test_provision_io.py::test_legacy_synthetic_customer_safety` compares every combination and
both stack roles, and records the actual CLI policy lookup to prove zero discovery on correct roles.
