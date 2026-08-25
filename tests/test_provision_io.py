"""The provisioner's write-side safety checks (PLAN 17D-review).

`stack-service-accounts:write` is the narrowest scope gcom offers  -  there is no `:create`  -  so the
credential itself cannot be stopped from deleting the organisation's own service accounts, including
`Observability Service Account(DO NOT MODIFY OR DELETE!)` on all 273 stacks. These tests are the control.
"""

from __future__ import annotations

import importlib.util
import json
import unittest
from types import SimpleNamespace
from unittest import mock
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "provision_cli", Path(__file__).resolve().parent.parent / "bin" / "provision.py")
cli = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cli)

from collector import provision as pr  # noqa: E402


class _FakeGcom:
    def __init__(self) -> None:
        self.deleted: list[str] = []
        self.dry_run = False
        self.reads = self.writes = 0

    def delete(self, path):
        self.deleted.append(path)
        return 200, {}


class DeleteRefusalTest(unittest.TestCase):
    def test_deleting_a_service_account_this_run_created_is_allowed(self):
        g, led = _FakeGcom(), cli.Ledger()
        led.record_sa("stack039", 42)
        self.assertTrue(cli._delete_sa(g, led, "stack039", 42))
        self.assertEqual(g.deleted, ["/instances/stack039/api/serviceaccounts/42"])

    def test_deleting_a_service_account_we_did_not_create_RAISES_and_issues_no_call(self):
        """The customer's own service accounts. Nothing may reach the API here."""
        g, led = _FakeGcom(), cli.Ledger()
        with self.assertRaises(RuntimeError) as ctx:
            cli._delete_sa(g, led, "stack039", 7)
        self.assertIn("REFUSING", str(ctx.exception))
        self.assertEqual(g.deleted, [])

    def test_the_ledger_does_not_confuse_the_same_id_on_a_different_stack(self):
        """Service-account ids are per stack and low-numbered, so collisions are the norm."""
        g, led = _FakeGcom(), cli.Ledger()
        led.record_sa("stack039", 15)
        with self.assertRaises(RuntimeError):
            cli._delete_sa(g, led, "obs-hub", 15)
        self.assertEqual(g.deleted, [])

    def test_an_adopted_leftover_admin_becomes_deletable_only_via_the_ledger(self):
        g, led = _FakeGcom(), cli.Ledger()
        sas = [{"id": 9, "name": pr.ADMIN_SA_NAME}, {"id": 10, "name": "organisation-own-sa"}]
        self.assertEqual(cli.sweep_leftover_admin(g, led, "stack039", sas), 1)
        self.assertEqual(g.deleted, ["/instances/stack039/api/serviceaccounts/9"])

    def test_the_sweep_matches_our_reserved_name_EXACTLY_not_as_a_substring(self):
        """A substring match is what orphaned a custom role during the spike."""
        g, led = _FakeGcom(), cli.Ledger()
        sas = [
            {"id": 1, "name": pr.ADMIN_SA_NAME + "-old"},
            {"id": 2, "name": "prefix-" + pr.ADMIN_SA_NAME},
            {"id": 3, "name": pr.READER_SA_NAME},
        ]
        self.assertEqual(cli.sweep_leftover_admin(g, led, "stack039", sas), 0)
        self.assertEqual(g.deleted, [])

    def test_the_sweep_never_touches_organisations_own_observability_service_account(self):
        g, led = _FakeGcom(), cli.Ledger()
        sas = [{"id": 4, "name": "Observability Service Account(DO NOT MODIFY OR DELETE!)"}]
        self.assertEqual(cli.sweep_leftover_admin(g, led, "stack039", sas), 0)
        self.assertEqual(g.deleted, [])


class DryRunTest(unittest.TestCase):
    def test_a_dry_run_gcom_issues_no_write(self):
        g = cli.Gcom("fake-token", dry_run=True)
        status, _ = g.post("/instances/x/api/serviceaccounts", {"name": "n", "role": "None"})
        self.assertEqual(status, 201)
        self.assertEqual(g.writes, 0)

    def test_a_dry_run_stack_client_issues_no_write(self):
        st = cli.Stack("https://stack039.grafana.net", "fake", dry_run=True)
        status, body = st.post("/api/access-control/roles", {"name": "x"})
        self.assertEqual(status, 200)
        self.assertEqual(body["uid"], "dry-run")


class SsmPathTest(unittest.TestCase):
    def test_the_stored_slug_round_trips_through_the_parameter_path(self):
        """`prune_targets` compares slugs taken back off the path against the inventory."""
        for slug in ("stack039", "obs-hub", "teststack003"):
            self.assertEqual(pr.ssm_path(slug).rsplit("/", 1)[-1], slug)


class StackUrlAuthorityTest(unittest.TestCase):
    def test_probe_uses_the_inventory_url_not_a_hostname_derived_from_slug(self):
        seen = []

        class CaptureStack:
            def __init__(self, base_url, token, dry_run):
                seen.append((base_url, token, dry_run))

            def get(self, _path):
                return 200, {"serviceaccounts:read": ["serviceaccounts:*"]}

        sas = [{"name": pr.READER_SA_NAME, "role": "None"}]
        stored = {"misleading-slug": {"token": "reader"}}
        with mock.patch.object(cli, "Stack", CaptureStack):
            cli.probe("misleading-slug", "https://authoritative.customer.example", sas, stored)

        self.assertEqual(seen, [("https://authoritative.customer.example", "reader", False)])


class SsmStoreFailClosedTest(unittest.TestCase):
    def test_a_successful_empty_store_is_a_known_bootstrap_state(self):
        proc = SimpleNamespace(returncode=0, stdout=json.dumps({"Parameters": []}), stderr="")
        with mock.patch.object(cli.subprocess, "run", return_value=proc):
            self.assertEqual(cli.ssm_load_all(), {})

    def test_a_failed_first_page_is_not_an_empty_bootstrap_store(self):
        proc = SimpleNamespace(returncode=255, stdout="", stderr="AccessDenied")
        with mock.patch.object(cli.subprocess, "run", return_value=proc):
            with self.assertRaises(cli.SsmStoreUnreadable):
                cli.ssm_load_all()

    def test_a_failed_later_page_does_not_return_a_dangerous_partial_store(self):
        first = SimpleNamespace(
            returncode=0,
            stdout=json.dumps({
                "Parameters": [{"Name": pr.ssm_path("a"), "Value": json.dumps({"token": "x"})}],
                "NextToken": "next",
            }),
            stderr="",
        )
        failed = SimpleNamespace(returncode=255, stdout="", stderr="expired session")
        with mock.patch.object(cli.subprocess, "run", side_effect=[first, failed]):
            with self.assertRaises(cli.SsmStoreUnreadable):
                cli.ssm_load_all()

    def test_invalid_aws_json_is_unknown_not_empty(self):
        proc = SimpleNamespace(returncode=0, stdout="not-json", stderr="")
        with mock.patch.object(cli.subprocess, "run", return_value=proc):
            with self.assertRaises(cli.SsmStoreUnreadable):
                cli.ssm_load_all()

    def test_main_stops_before_any_stack_repair_or_prune_when_ssm_is_unknown(self):
        class InventoryOnlyGcom:
            def __init__(self, *_args, **_kwargs):
                self.reads = self.writes = 0

            def get(self, _path):
                self.reads += 1
                return 200, {"items": [{"slug": "a", "status": "active",
                                        "url": "https://authoritative-a.example"}]}

        with mock.patch.dict(cli.os.environ, {"GCINSIGHT_PROVISION_TOKEN": "x",
                                              "GCINSIGHT_ORG_ID": "900001",
                                              "GCINSIGHT_WRITE_STACK": "a"}, clear=False), \
             mock.patch.object(cli, "Gcom", InventoryOnlyGcom), \
             mock.patch.object(cli, "ssm_load_all", side_effect=cli.SsmStoreUnreadable("denied")), \
             mock.patch.object(cli, "list_sas") as list_sas, \
             mock.patch.object(cli, "repair") as repair, \
             mock.patch.object(cli, "ssm_delete") as delete:
            self.assertEqual(cli.main([]), 1)
        list_sas.assert_not_called()
        repair.assert_not_called()
        delete.assert_not_called()


class _RoleStack:
    def __init__(self, permissions, full_status=200):
        self.permissions = permissions
        self.full_status = full_status
        self.puts = []

    def get(self, path):
        if path == "/api/access-control/roles?includeHidden=true":
            return 200, [{"name": pr.ROLE_NAME, "uid": "role-1", "version": 7}]
        return self.full_status, {"permissions": self.permissions}

    def put(self, path, body):
        self.puts.append((path, body))
        return 200, {}


class EnsureRoleScopeTest(unittest.TestCase):
    def test_only_the_write_stack_role_accepts_and_adds_the_usage_datasource_scope(self):
        """The exact grant follows the nominated write stack and is removed from its predecessor."""
        ordinary = _RoleStack([dict(p) for p in pr.DESIRED_PERMISSIONS])
        ok, _, _ = cli.ensure_role(ordinary, write_stack=True)
        self.assertTrue(ok)
        pairs = {(p["action"], p.get("scope") or "")
                 for p in ordinary.puts[0][1]["permissions"]}
        self.assertIn(("datasources:query", f"datasources:uid:{pr.USAGE_DS_UID}"), pairs)

        unexpected = _RoleStack([dict(p) for p in pr.desired_permissions(write_stack=True)])
        ok, _, note = cli.ensure_role(unexpected, write_stack=False)
        self.assertTrue(ok)
        self.assertIn("patched", note)
        pairs = {(p["action"], p.get("scope") or "")
                 for p in unexpected.puts[0][1]["permissions"]}
        self.assertNotIn(pr.WRITE_STACK_PAIR, pairs)

    def test_a_query_action_at_the_wrong_scope_is_refused_before_any_write(self):
        permissions = [
            dict(p) for p in pr.DESIRED_PERMISSIONS
            if p["action"] != "datasources:query"
        ] + [{"action": "datasources:query", "scope": "datasources:*"}]
        st = _RoleStack(permissions)

        ok, uid, note = cli.ensure_role(st)

        self.assertFalse(ok)
        self.assertEqual(uid, "role-1")
        self.assertIn("REFUSED", note)
        self.assertIn("datasources:query", note)
        self.assertEqual(st.puts, [])

    def test_a_broad_query_is_not_preserved_beside_a_benign_extra(self):
        permissions = [
            dict(p) for p in pr.DESIRED_PERMISSIONS
            if p["action"] != "datasources:query"
        ] + [
            {"action": "datasources:query", "scope": "datasources:*"},
            {"action": "annotations:read", "scope": "annotations:*"},
        ]
        st = _RoleStack(permissions)

        ok, _, note = cli.ensure_role(st)

        self.assertFalse(ok)
        self.assertIn("datasources:query", note)
        self.assertEqual(st.puts, [])

    def test_an_unexpected_write_permission_is_refused_before_any_role_patch(self):
        permissions = [dict(p) for p in pr.DESIRED_PERMISSIONS] + [
            {"action": "dashboards:write", "scope": "dashboards:*"},
        ]
        st = _RoleStack(permissions)

        ok, _, note = cli.ensure_role(st)

        self.assertFalse(ok)
        self.assertIn("dashboards:write", note)
        self.assertEqual(st.puts, [])

    def test_a_rewrite_preserves_arbitrary_customer_added_permissions(self):
        """Reconciliation adds what we declared. It does not prune what the customer added.

        Pruning arbitrary access would make this project an authority on someone else's RBAC. The role
        is rewritten here because one declared pair is missing, which is the only trigger.
        """
        incomplete = [dict(p) for p in pr.DESIRED_PERMISSIONS
                      if p["action"] != "grafana-adaptivetraces-app.policies:read"]
        st = _RoleStack(incomplete + [{"action": "annotations:read", "scope": "annotations:*"}])

        ok, _, _ = cli.ensure_role(st)

        self.assertTrue(ok)
        pairs = {(p["action"], p.get("scope") or "") for p in st.puts[0][1]["permissions"]}
        self.assertIn(("annotations:read", "annotations:*"), pairs)
        self.assertIn(("grafana-adaptivetraces-app.policies:read", ""), pairs)
        self.assertTrue(pr.DESIRED_PAIRS <= pairs)

    def test_a_role_already_carrying_every_declared_pair_is_not_rewritten(self):
        """273 needless Admin identities per run would be the cost of rewriting a healthy role."""
        st = _RoleStack([dict(p) for p in pr.DESIRED_PERMISSIONS]
                        + [{"action": "annotations:read", "scope": "annotations:*"}])

        ok, _, _ = cli.ensure_role(st)

        self.assertTrue(ok)
        self.assertEqual(st.puts, [])

    def test_a_failed_full_role_read_never_blindly_overwrites_the_role(self):
        st = _RoleStack([], full_status=500)
        ok, _, note = cli.ensure_role(st)
        self.assertFalse(ok)
        self.assertIn("role read HTTP 500", note)
        self.assertEqual(st.puts, [])


class _RepairGcom:
    def __init__(self):
        self.dry_run = False
        self.deleted = []

    def post(self, path, _body):
        if path.endswith("/api/serviceaccounts"):
            return 201, {"id": 90, "name": pr.ADMIN_SA_NAME, "role": "Admin"}
        if path.endswith("/tokens"):
            return 200, {"id": 91, "key": "admin-token"}
        raise AssertionError(path)

    def delete(self, path):
        self.deleted.append(path)
        return 200, {}


class _RepairStack:
    patch_status = 200
    assignment_status = 200

    def __init__(self, *_args, **_kwargs):
        pass

    def patch(self, _path, _body):
        return self.patch_status, {"message": "patch"}

    def post(self, _path, _body):
        return self.assignment_status, {"message": "assign"}


class RepairVerificationTest(unittest.TestCase):
    def _presence(self, **updates):
        values = dict(sa_exists=True, secret_exists=True, token_status=200,
                      basic_role="None", role_exists=True,
                      role_actions=pr.DESIRED_ACTIONS, assigned=True)
        values.update(updates)
        return pr.Presence(**values)

    def _repair(self, presence, stack_cls=_RepairStack):
        sas = [{"id": 12, "name": pr.READER_SA_NAME, "role": presence.basic_role}]
        with mock.patch.object(cli, "Stack", stack_cls), \
             mock.patch.object(cli, "ensure_role", return_value=(True, "role-1", "unchanged")), \
             mock.patch.object(cli, "verify_reader", return_value=(True, "verified")):
            return cli.repair(
                _RepairGcom(), cli.Ledger(), "a", "https://real-a.example", sas, False,
                presence=presence, existing_token="reader-token",
            )

    def test_missing_presence_fails_before_any_write(self):
        g = mock.Mock()
        with self.assertRaises(TypeError):
            cli.repair(
                g, cli.Ledger(), "a", "https://real-a.example", [], False,
                presence=None, existing_token=None,
            )
        g.post.assert_not_called()

    def test_existing_token_fact_is_required_before_any_write(self):
        g = mock.Mock()
        with self.assertRaises(TypeError):
            cli.repair(
                g, cli.Ledger(), "a", "https://real-a.example", [], False,
                presence=self._presence(),
            )
        g.post.assert_not_called()

    def test_role_repair_keeps_the_working_reader_token(self):
        class CaptureGcom(_RepairGcom):
            def __init__(self):
                super().__init__()
                self.posts = []

            def post(self, path, body):
                self.posts.append((path, body))
                return super().post(path, body)

        presence = self._presence(role_actions=frozenset({"serviceaccounts:read"}))
        sas = [{"id": 12, "name": pr.READER_SA_NAME, "role": "None"}]
        g = CaptureGcom()
        with mock.patch.object(cli, "Stack", _RepairStack), \
             mock.patch.object(cli, "ensure_role", return_value=(True, "role-1", "patched")), \
             mock.patch.object(cli, "verify_reader", return_value=(True, "verified")):
            outcome = cli.repair(
                g, cli.Ledger(), "a", "https://real-a.example", sas, False,
                presence=presence, existing_token="reader-token",
            )

        self.assertEqual(outcome.action, pr.OK)
        self.assertFalse(any(path.endswith("/serviceaccounts/12/tokens") for path, _ in g.posts))

    def test_token_name_conflict_does_not_retry_with_a_timestamped_name(self):
        class ConflictGcom(_RepairGcom):
            token_names = []

            def post(self, path, body):
                if path.endswith("/serviceaccounts/12/tokens"):
                    self.token_names.append(body["name"])
                    return 400, {"messageId": "serviceaccounts.ErrTokenAlreadyExists"}
                return super().post(path, body)

        presence = self._presence(secret_exists=False, token_status=None)
        sas = [{"id": 12, "name": pr.READER_SA_NAME, "role": "None"}]
        with mock.patch.object(cli, "Stack", _RepairStack), \
             mock.patch.object(cli, "ensure_role", return_value=(True, "role-1", "unchanged")), \
             mock.patch.object(cli, "verify_reader") as verify:
            outcome = cli.repair(
                ConflictGcom(), cli.Ledger(), "a", "https://real-a.example", sas, False,
                presence=presence, existing_token=None,
            )

        self.assertEqual(outcome.action, "token_failed")
        self.assertEqual(ConflictGcom.token_names, [pr.token_name("a")])
        verify.assert_not_called()

    def test_failed_ssm_write_revokes_exactly_the_newly_minted_token(self):
        class MintGcom(_RepairGcom):
            def post(self, path, body):
                if path.endswith("/serviceaccounts/12/tokens"):
                    return 200, {"id": 123, "key": "new-reader-token"}
                return super().post(path, body)

        class CleanupStack(_RepairStack):
            deleted = []

            def delete(self, path):
                self.deleted.append(path)
                return 200, {"message": "deleted"}

        presence = self._presence(secret_exists=False, token_status=None)
        sas = [{"id": 12, "name": pr.READER_SA_NAME, "role": "None"}]
        with mock.patch.object(cli, "Stack", CleanupStack), \
             mock.patch.object(cli, "ensure_role", return_value=(True, "role-1", "unchanged")), \
             mock.patch.object(cli, "ssm_put", return_value=False), \
             mock.patch.object(cli, "verify_reader") as verify:
            outcome = cli.repair(
                MintGcom(), cli.Ledger(), "a", "https://real-a.example", sas, False,
                presence=presence, existing_token=None,
            )

        self.assertEqual(outcome.action, "ssm_write_failed")
        self.assertEqual(CleanupStack.deleted, ["/api/serviceaccounts/12/tokens/123"])
        verify.assert_not_called()

    def test_ssm_exception_still_revokes_exactly_the_newly_minted_token(self):
        class MintGcom(_RepairGcom):
            def post(self, path, body):
                if path.endswith("/serviceaccounts/12/tokens"):
                    return 200, {"id": 456, "key": "new-reader-token"}
                return super().post(path, body)

        class CleanupStack(_RepairStack):
            deleted = []

            def delete(self, path):
                self.deleted.append(path)
                return 200, {"message": "deleted"}

        presence = self._presence(secret_exists=False, token_status=None)
        sas = [{"id": 12, "name": pr.READER_SA_NAME, "role": "None"}]
        with mock.patch.object(cli, "Stack", CleanupStack), \
             mock.patch.object(cli, "ensure_role", return_value=(True, "role-1", "unchanged")), \
             mock.patch.object(cli, "ssm_put", side_effect=RuntimeError("aws unavailable")), \
             mock.patch.object(cli, "verify_reader") as verify:
            outcome = cli.repair(
                MintGcom(), cli.Ledger(), "a", "https://real-a.example", sas, False,
                presence=presence, existing_token=None,
            )

        self.assertEqual(outcome.action, "ssm_write_failed")
        self.assertIn("aws unavailable", outcome.detail)
        self.assertEqual(CleanupStack.deleted, ["/api/serviceaccounts/12/tokens/456"])
        verify.assert_not_called()

    def test_a_failed_basic_role_patch_is_a_failed_repair(self):
        class FailedPatch(_RepairStack):
            patch_status = 500

        outcome = self._repair(self._presence(basic_role="Admin"), FailedPatch)
        self.assertEqual(outcome.action, "basic_role_failed")

    def test_a_failed_role_assignment_is_a_failed_repair(self):
        class FailedAssignment(_RepairStack):
            assignment_status = 500

        outcome = self._repair(self._presence(), FailedAssignment)
        self.assertEqual(outcome.action, "role_assignment_failed")

    def test_a_failed_final_probe_cannot_return_ok(self):
        sas = [{"id": 12, "name": pr.READER_SA_NAME, "role": "None"}]
        with mock.patch.object(cli, "Stack", _RepairStack), \
             mock.patch.object(cli, "ensure_role", return_value=(True, "role-1", "unchanged")), \
             mock.patch.object(cli, "verify_reader", return_value=(False, "token still refused")):
            outcome = cli.repair(
                _RepairGcom(), cli.Ledger(), "a", "https://real-a.example", sas, False,
                presence=self._presence(), existing_token="reader-token",
            )
        self.assertEqual(outcome.action, "verification_failed")


class MainExitStatusTest(unittest.TestCase):
    def test_missing_org_id_is_refused_before_inventory(self):
        with mock.patch.dict(cli.os.environ, {"GCINSIGHT_PROVISION_TOKEN": "x"}, clear=True), \
             mock.patch.object(cli, "Gcom") as gcom:
            self.assertEqual(cli.main(["--dry-run"]), 2)
        gcom.assert_not_called()

    def test_unknown_write_stack_is_refused_before_credentials_or_repairs(self):
        class InventoryGcom:
            def __init__(self, *_args, **_kwargs):
                self.reads = self.writes = 0

            def get(self, _path):
                return 200, {"items": [{"slug": "a", "status": "active"}]}

        with mock.patch.dict(cli.os.environ, {
            "GCINSIGHT_PROVISION_TOKEN": "x", "GCINSIGHT_ORG_ID": "900001",
            "GCINSIGHT_WRITE_STACK": "missing",
        }, clear=True), mock.patch.object(cli, "Gcom", InventoryGcom), \
                mock.patch.object(cli, "ssm_load_all") as load:
            self.assertEqual(cli.main(["--dry-run"]), 2)
        load.assert_not_called()

    def _run_with(self, outcome):
        class OneStackGcom:
            def __init__(self, *_args, **_kwargs):
                self.reads = self.writes = 0

            def get(self, _path):
                self.reads += 1
                return 200, {"items": [{"slug": "a", "status": "active",
                                        "url": "https://authoritative-a.example"}]}

        presence = pr.Presence(False, False)
        with mock.patch.dict(cli.os.environ, {"GCINSIGHT_PROVISION_TOKEN": "x",
                                              "GCINSIGHT_ORG_ID": "900001",
                                              "GCINSIGHT_WRITE_STACK": "a"}, clear=False), \
             mock.patch.object(cli, "Gcom", OneStackGcom), \
             mock.patch.object(cli, "ssm_load_all", return_value={}), \
             mock.patch.object(cli, "list_sas", return_value=(200, [])), \
             mock.patch.object(cli, "sweep_leftover_admin", return_value=0), \
             mock.patch.object(cli, "probe", return_value=presence), \
             mock.patch.object(cli, "repair", return_value=outcome):
            return cli.main(["--no-prune"])

    def test_any_failed_repair_makes_the_process_fail(self):
        broken = pr.Outcome("a", pr.PROVISIONABLE, "verification_failed", "still refused")
        self.assertEqual(self._run_with(broken), 1)

    def test_a_role_failure_is_nonzero_even_if_the_stack_is_reclassified(self):
        broken = pr.Outcome("a", pr.NO_ASSISTANT, "role_failed", "plugin absent")
        self.assertEqual(self._run_with(broken), 1)


class RolePatchDoesNotChurnTokensTest(unittest.TestCase):
    """A role change must not re-mint a working credential.

    The repair path is monolithic: any repair runs the whole flow, and minting always ran. Token names
    are unique per ORG, so a re-mint against a live token falls back to a timestamped name and leaves
    the original live. Expanding the role across the estate would therefore have minted a token per
    stack and orphaned the one it replaced - hundreds of untracked, still-valid credentials on customer
    stacks, with SSM pointing only at the newest.

    Patching a role needs an Admin identity and a role write. It does not need a new token.
    """

    def test_a_working_token_is_not_reminted_when_only_the_role_drifted(self):
        p = pr.Presence(sa_exists=True, secret_exists=True, token_status=200,
                        basic_role="None", role_exists=True,
                        role_actions=frozenset({"serviceaccounts:read"}), assigned=True)
        self.assertEqual(pr.plan_action(p), pr.PATCH_ROLE)
        self.assertFalse(pr.needs_token_mint(p),
                         "a 200 credential must survive a role patch untouched")

    def test_a_dead_token_is_still_reminted(self):
        p = pr.Presence(sa_exists=True, secret_exists=True, token_status=401,
                        basic_role="None", role_exists=True,
                        role_actions=pr.DESIRED_ACTIONS, assigned=True)
        self.assertEqual(pr.plan_action(p), pr.MINT_TOKEN)
        self.assertTrue(pr.needs_token_mint(p))

    def test_a_missing_secret_is_still_minted(self):
        p = pr.Presence(sa_exists=True, secret_exists=False, role_exists=True,
                        role_actions=pr.DESIRED_ACTIONS, assigned=True, basic_role="None")
        self.assertTrue(pr.needs_token_mint(p))

    def test_a_403_never_triggers_a_mint(self):
        """403 means the credential is fine and the permissions are not. Re-minting would loop."""
        p = pr.Presence(sa_exists=True, secret_exists=True, token_status=403,
                        basic_role="None", role_exists=True,
                        role_actions=pr.DESIRED_ACTIONS, assigned=True)
        self.assertFalse(pr.needs_token_mint(p))


if __name__ == "__main__":
    unittest.main()
