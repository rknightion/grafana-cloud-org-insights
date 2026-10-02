"""The provisioner's write-side safety checks (PLAN 17D-review).

`stack-service-accounts:write` is the narrowest scope gcom offers  -  there is no `:create`  -  so the
credential itself cannot be stopped from deleting the organisation's own service accounts, including
`Observability Service Account(DO NOT MODIFY OR DELETE!)` on all 273 stacks. These tests are the control.
"""

from __future__ import annotations

import importlib.util
import io
import json
import unittest
import urllib.request
from email.message import Message
from urllib.response import addinfourl
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

    def test_unknown_product_read_refuses_before_inventory_or_any_write_path(self):
        with mock.patch.dict(cli.os.environ, {
            "GCINSIGHT_PROVISION_TOKEN": "x", "GCINSIGHT_ORG_ID": "900001",
            "GCINSIGHT_WRITE_STACK": "a", "GCINSIGHT_READER_PRODUCT_READS": "slo,k6",
        }, clear=True), mock.patch.object(cli, "Gcom") as gcom, \
                mock.patch.object(cli, "ssm_load_all") as load, \
                mock.patch.object(cli, "sweep_leftover_admin") as sweep, \
                mock.patch.object(cli, "repair") as repair, \
                mock.patch.object(cli, "ssm_delete") as delete:
            self.assertEqual(cli.main([]), 2)

        gcom.assert_not_called()
        load.assert_not_called()
        sweep.assert_not_called()
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


class EnsureRoleReconciliationTest(unittest.TestCase):
    def test_configured_pairs_are_added_unconfigured_pairs_removed_and_exact_state_is_noop(self):
        def role(permissions):
            return _RoleStack([dict(p) for p in permissions])

        empty = role(pr.DESIRED_PERMISSIONS)
        ok, _, note = cli.ensure_role(empty, product_reads={"slo"})
        self.assertTrue(ok)
        self.assertIn("patched", note)
        added = {(p["action"], p.get("scope") or "")
                 for p in empty.puts[0][1]["permissions"]}
        self.assertEqual(added - pr.DESIRED_PAIRS, frozenset({
            ("grafana-slo-app.orgpreferences:read", ""),
            ("grafana-slo-app.slo:read", ""),
            ("plugins.app:access", "plugins:id:grafana-slo-app"),
        }))

        all_grants = [dict(p) for p in pr.desired_permissions(
            write_stack=False, product_reads={"slo", "synthetic-monitoring"},
        )]
        configured = role(all_grants)
        ok, _, note = cli.ensure_role(configured, product_reads={"slo"})
        self.assertTrue(ok)
        self.assertIn("patched", note)
        remaining = {(p["action"], p.get("scope") or "")
                     for p in configured.puts[0][1]["permissions"]}
        self.assertEqual(remaining - pr.DESIRED_PAIRS, frozenset({
            ("grafana-slo-app.orgpreferences:read", ""),
            ("grafana-slo-app.slo:read", ""),
            ("plugins.app:access", "plugins:id:grafana-slo-app"),
        }))

        unset = role(all_grants)
        ok, _, note = cli.ensure_role(unset)
        self.assertTrue(ok)
        self.assertIn("patched", note)
        self.assertEqual(
            {(p["action"], p.get("scope") or "")
             for p in unset.puts[0][1]["permissions"]},
            pr.DESIRED_PAIRS,
        )

        unchanged = role(pr.desired_permissions(write_stack=False, product_reads={"slo"}))
        ok, _, note = cli.ensure_role(unchanged, product_reads={"slo"})
        self.assertTrue(ok)
        self.assertEqual(note, "unchanged")
        self.assertEqual(unchanged.puts, [])

        generator = role(pr.desired_permissions(write_stack=False, product_reads={"slo"}))
        ok, _, note = cli.ensure_role(generator, product_reads=(name for name in ("slo",)))
        self.assertTrue(ok)
        self.assertEqual(note, "unchanged")
        self.assertEqual(generator.puts, [])

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



class VerifyReaderBackoffTest(unittest.TestCase):
    """GCI-0045 AC3. Propagation delay is retried read-only; persistent drift still fails."""

    def _run(self, results):
        calls = iter(results)
        waits = []
        with mock.patch.object(cli, "_verify_reader_once", side_effect=lambda *a, **k: next(calls)):
            outcome = cli.verify_reader(None, "s", "u", "t", sleep=waits.append)
        return outcome, waits

    def test_a_late_propagation_is_verified_without_failing_the_run(self):
        outcome, waits = self._run([(False, "post-repair probe still needs pairs (sa=True)"), (False, "post-repair probe still needs pairs (sa=True)"), (True, "verified")])
        self.assertEqual(outcome, (True, "verified"))
        self.assertEqual(len(waits), 2)

    def test_a_failure_that_waiting_cannot_fix_is_not_retried(self):
        """Each wait holds the transient Admin account open; a failed listing will not self-heal."""
        outcome, waits = self._run([(False, "service-account verification HTTP 500")])
        self.assertFalse(outcome[0])
        self.assertEqual(waits, [])

    def test_persistent_drift_fails_after_a_bounded_number_of_probes(self):
        results = [(False, "post-repair probe still needs pairs (sa=True)")] * (len(cli.VERIFY_BACKOFF_SECONDS) + 1)
        outcome, waits = self._run(results)
        self.assertEqual(outcome, (False, "post-repair probe still needs pairs (sa=True)"))
        self.assertEqual(waits, list(cli.VERIFY_BACKOFF_SECONDS))


class EndOfRunReverifyTest(unittest.TestCase):
    """GCI-0050. A mass role update can outlast the in-run backoff; the final probe decides."""

    PROPAGATING = "post-repair probe still needs patch_role (sa=True secret=True token=200 basic_role=None)"

    def _main(self, final_probe, slugs=("a", "b")):
        class InventoryGcom:
            def __init__(self, *_args, **_kwargs):
                self.reads = self.writes = 0

            def get(self, _path):
                self.reads += 1
                return 200, {"items": [{"slug": s, "status": "active",
                                        "url": f"https://authoritative-{s}.example"} for s in slugs]}

        stored = {s: {"token": f"token-{s}"} for s in slugs}
        probed = []

        def once(_g, slug, _url, token, **_kwargs):
            probed.append((slug, token))
            return final_probe[slug]

        out = io.StringIO()
        with mock.patch.dict(cli.os.environ, {"GCINSIGHT_PROVISION_TOKEN": "x",
                                              "GCINSIGHT_ORG_ID": "900001",
                                              "GCINSIGHT_WRITE_STACK": slugs[0]}, clear=False), \
             mock.patch.object(cli, "Gcom", InventoryGcom), \
             mock.patch.object(cli, "ssm_load_all", return_value=stored), \
             mock.patch.object(cli, "list_sas", return_value=(200, [])), \
             mock.patch.object(cli, "sweep_leftover_admin", return_value=0), \
             mock.patch.object(cli, "probe", return_value=pr.Presence(sa_exists=True, secret_exists=True, token_status=200, basic_role=None)), \
             mock.patch.object(cli.pr, "needs_repair", return_value=True), \
             mock.patch.object(cli.pr, "plan_action", return_value="patch_role"), \
             mock.patch.object(cli, "repair", side_effect=lambda _g, _l, slug, *a, **k: cli.pr.Outcome(
                 slug, cli.pr.PROVISIONABLE, "verification_failed", self.PROPAGATING)), \
             mock.patch.object(cli, "_verify_reader_once", side_effect=once), \
             mock.patch.object(cli.time, "sleep"), \
             mock.patch("sys.stdout", out):
            code = cli.main(["--no-prune"])
        return code, out.getvalue(), probed

    def test_repairs_that_verify_at_the_end_of_the_run_exit_zero(self):
        code, out, probed = self._main({"a": (True, "verified"), "b": (True, "verified")})
        self.assertEqual(code, 0)
        self.assertIn("provisionable/ok=2", out)
        # The final probe uses the durable stored credential, never a fresh mint.
        self.assertEqual(sorted(probed), [("a", "token-a"), ("b", "token-b")])

    def test_drift_that_survives_the_final_probe_still_fails_the_run(self):
        code, out, _ = self._main({"a": (True, "verified"), "b": (False, self.PROPAGATING)})
        self.assertEqual(code, 1)
        self.assertIn("provisionable/verification_failed=1", out)

    def test_final_waits_overlap_so_the_run_grows_by_at_most_the_minimum_age(self):
        now = [250.0]
        waits = []

        def sleep(seconds):
            waits.append(seconds)
            now[0] += seconds

        outcomes = [cli.pr.Outcome(s, cli.pr.PROVISIONABLE, "verification_failed", self.PROPAGATING)
                    for s in ("a", "b", "c")]
        pending = {"a": ("u", False, 0.0), "b": ("u", False, 100.0), "c": ("u", False, 150.0)}
        stored = {s: {"token": "t"} for s in pending}
        with mock.patch.object(cli, "_verify_reader_once", return_value=(True, "verified")):
            result = cli.reverify_pending(None, outcomes, pending, stored,
                                          clock=lambda: now[0], sleep=sleep)
        self.assertEqual(waits, [50.0, 100.0, 50.0])
        self.assertLessEqual(sum(waits), cli.FINAL_VERIFY_MIN_AGE_SECONDS)
        self.assertTrue(all(o.action == cli.pr.OK for o in result))

    def test_a_truncated_failure_list_says_how_many_it_left_out(self):
        slugs = tuple(f"s{i:02d}" for i in range(23))
        code, out, _ = self._main({s: (False, self.PROPAGATING) for s in slugs}, slugs=slugs)
        self.assertEqual(code, 1)
        self.assertIn("and 3 more", out)


def test_synthetic_deselection_discovers_once_across_real_main_repair_and_verify():
    """Repeated phases must reuse this run's exact SM witness, never repeat absent-token lookup."""
    selected = {"slo", "synthetic-monitoring"}
    permissions = list(pr.desired_permissions(write_stack=True, product_reads=selected))
    permissions += [{"action": a, **({"scope": s} if s else {})}
                    for a, s in pr.synthetic_pairs("synthetic-sm")]
    paths, writes = [], []
    reader = {"id": 20001, "name": pr.READER_SA_NAME, "role": "None"}
    class Gcom:
        def __init__(self, *args, **kwargs):
            self.reads = self.writes = 0
            self.dry_run = False
        def get(self, path):
            self.reads += 1
            if "serviceaccounts" in path:
                return 200, {"serviceAccounts": [reader]}
            return 200, {"items": [{"slug": "synthetic", "url": "https://inventory.example.test",
                                    "status": "active"}]}
        def post(self, path, body):
            self.writes += 1
            writes.append(path)
            if path.endswith("/tokens"):
                assert "/20001/" not in path, "working reader credential must not be minted"
                return 200, {"key": "admin"}
            return 201, {"id": 20002}
        def delete(self, path):
            self.writes += 1
            writes.append(path)
            assert path.endswith("/20002")
            return 200, {}
    class Stack:
        NOT_INSPECTED = 0
        def __init__(self, *args, **kwargs):
            pass
        def get_synthetic_datasources(self):
            paths.append("/api/datasources")
            return 200, [{"type": pr.SM_PLUGIN_TYPE, "uid": "synthetic-sm"}]
        def get(self, path):
            paths.append(path)
            if path == "/api/access-control/user/permissions":
                have = {}
                for permission in permissions:
                    have.setdefault(permission["action"], []).append(permission.get("scope", ""))
                return 200, have
            if path.endswith("?includeHidden=true"):
                return 200, [{"name": pr.ROLE_NAME, "uid": "synthetic-role", "version": 1}]
            return 200, {"permissions": permissions}
        def put(self, path, body):
            permissions[:] = body["permissions"]
            return 200, {}
        def post(self, path, body):
            assert path.endswith("/roles")
            return 200, {}
    with mock.patch.dict(cli.os.environ, {"GCINSIGHT_PROVISION_TOKEN": "fake", "GCINSIGHT_ORG_ID": "900001",
                                          "GCINSIGHT_WRITE_STACK": "synthetic", pr.PRODUCT_READS_ENV: "slo,synthetic-monitoring"}), \
         mock.patch.object(cli, "Gcom", Gcom), mock.patch.object(cli, "Stack", Stack), \
         mock.patch.object(cli, "ssm_load_all", return_value={"synthetic": {"token": "reader"}}), \
         mock.patch.object(cli, "ssm_put") as store:
        assert cli.main(["--no-prune"]) == 0
    store.assert_not_called()
    assert paths.count("/api/datasources") == 1, paths
    assert pr.permission_pairs(permissions) == pr.permission_pairs(pr.desired_permissions(
        write_stack=True, product_reads=selected))


def test_synthetic_discovery_redirect_cannot_forward_token_or_choose_query_grant():
    """Real urllib redirect processing must stop before the foreign HTTPS network edge."""
    from collector import httpclient

    seen, puts = [], []
    foreign = "https://foreign.example.test/api/datasources"

    def edge(_handler, req):
        seen.append((req.full_url, req.get_header("Authorization")))
        headers = Message()
        code = 200
        if req.full_url == foreign:
            body = [{"type": pr.SM_PLUGIN_TYPE, "uid": "customer-database"}]
        elif req.full_url.endswith("/api/datasources"):
            headers["Location"] = foreign
            code, body = 302, {}
        elif req.get_method() == "PUT":
            puts.append(json.loads(req.data))
            body = {}
        elif req.full_url.endswith("?includeHidden=true"):
            body = [{"name": pr.ROLE_NAME, "uid": "role-1", "version": 1}]
        else:
            body = {"permissions": list(pr.DESIRED_PERMISSIONS)}
        response = addinfourl(io.BytesIO(json.dumps(body).encode()), headers, req.full_url, code)
        response.msg = "test response"
        return response

    opener = urllib.request.build_opener()
    with mock.patch.object(urllib.request.HTTPSHandler, "https_open", edge), \
         mock.patch.object(httpclient._GuardedHTTPSHandler, "https_open", edge), \
         mock.patch.object(cli.urllib.request, "urlopen", opener.open):
        ok, _, _ = cli.ensure_role(
            cli.Stack("https://inventory.example.test", "fake-admin", dry_run=False),
            product_reads={"synthetic-monitoring", "synthetic-monitoring-query"})
    assert ok
    # Independently pin grant safety, no second request, and no bearer forwarding.
    assert all(("datasources:query", "datasources:uid:customer-database") not in
               pr.permission_pairs(body["permissions"]) for body in puts), puts
    assert [url for url, _ in seen].count("https://inventory.example.test/api/datasources") == 1
    assert not any(url == foreign for url, _ in seen), seen
    assert not any(url == foreign and auth for url, auth in seen), seen


def test_synthetic_discovery_validates_inventory_origin_before_sending_credentials():
    from collector import httpclient

    seen = []
    def edge(_handler, req):
        seen.append((req.full_url, req.get_method(), req.get_header("Authorization")))
        response = addinfourl(io.BytesIO(json.dumps([
            {"type": pr.SM_PLUGIN_TYPE, "uid": "synthetic-sm"}
        ]).encode()), Message(), req.full_url, 200)
        response.msg = "test response"
        return response

    tokens = {"synthetic-monitoring", "synthetic-monitoring-query"}
    with mock.patch.object(httpclient._GuardedHTTPSHandler, "https_open", edge):
        for url in ("https://user@inventory.example.test", "https://inventory.example.test/path",
                    "https://inventory.example.test?query=yes", "https://inventory.example.test#fragment",
                    "https://inventory.example.test:bad", "https://inventory.example.test///"):
            permissions, _, state = cli.reader_policy(cli.Stack(url, "fake-reader", False), {},
                                                       product_reads=tokens)
            assert state == "unreadable"
            assert not (pr.synthetic_pairs("synthetic-sm") & pr.permission_pairs(permissions))
        assert seen == []
        permissions, _, state = cli.reader_policy(
            cli.Stack("https://inventory.example.test/", "fake-reader", False), {}, product_reads=tokens)
    assert state == "available"
    assert pr.synthetic_pairs("synthetic-sm") <= pr.permission_pairs(permissions)
    assert seen == [("https://inventory.example.test/api/datasources", "GET", "Bearer fake-reader")]


def test_synthetic_bootstrap_without_reader_is_not_inspected():
    """Bootstrap must not send unauthenticated SM discovery before Admin repair."""
    st = cli.Stack("https://inventory.example.test", "dry-run", dry_run=True)
    with mock.patch.object(cli.urllib.request, "urlopen") as transport:
        permissions, removable, state = cli.reader_policy(st, {}, product_reads={
            "synthetic-monitoring", "synthetic-monitoring-query"})
    transport.assert_not_called()
    assert state == "not_inspected"
    assert not (pr.synthetic_pairs("synthetic-sm") & pr.permission_pairs(permissions))


def test_legacy_synthetic_customer_safety():
    """Original-source golden catches permission drift and unnecessary discovery on either stack role."""
    golden = json.loads((Path(__file__).parent / "fixtures/synthetic_legacy_permissions.json").read_text())
    for case in golden["cases"]:
        held = {}
        for p in case["desired"]:
            held.setdefault(p["action"], []).append(p.get("scope", ""))
        st = mock.Mock()
        st.get.return_value = (200, [{"type": pr.SM_PLUGIN_TYPE, "uid": "synthetic-sm"}])
        permissions, removable, state = cli.reader_policy(
            st, held, write_stack=case["write_stack"], product_reads=case["tokens"])
        assert list(permissions) == case["desired"]
        # The legacy golden stays immutable; this separately approved, unselected family adds
        # only its two retirement candidates, not grants or a Synthetic discovery exception.
        expected_removable = {tuple(pair) for pair in case["removable"]} | {
            ("grafana-irm-app.integrations:read", ""),
            ("plugins.app:access", "plugins:id:grafana-irm-app"),
            ("grafana-kowalski-app.apps:read", ""),
            ("plugins.app:access", "plugins:id:grafana-kowalski-app"),
            ("grafana-ml-app.forecasting:read", ""),
            ("plugins.app:access", "plugins:id:grafana-ml-app"),
            ("grafana-csp-app:read", ""),
            ("plugins.app:access", "plugins:id:grafana-csp-app"),
            ("grafana-pdc-app.private-networks:read", ""),
            ("plugins.app:access", "plugins:id:grafana-pdc-app"),
        }
        assert set(removable) == expected_removable
        wanted = pr.permission_pairs(permissions)
        assert sorted(pr.dangerous_extra_pairs(held, wanted, removable)) == case["dangerous"]
        st.get.assert_not_called()
        st.get_synthetic_datasources.assert_not_called()
        assert state == "not_selected"
        sas = [{"name": pr.READER_SA_NAME, "role": "None"}]
        with mock.patch.object(cli, "Stack") as stack:
            stack.return_value.get.return_value = (200, held)
            presence = cli.probe("synthetic", "https://inventory.example.test", sas,
                                 {"synthetic": {"token": "fake"}}, desired=wanted, removable=removable)
            stack.return_value.get.assert_called_once_with("/api/access-control/user/permissions")
        assert not pr.needs_repair(presence, wanted, removable=removable)


def test_synthetic_policy_exact_discovery_deselection_and_wrong_stack_usage():
    """No arbitrary query becomes approved, and only held unique SM pairs can be retired."""
    query = ("datasources:query", "datasources:uid:synthetic-sm")
    unrelated = ("datasources:query", "datasources:uid:customer-database")
    selected = {"synthetic-monitoring", "synthetic-monitoring-query"}
    for body, state in (([], "no_datasource"),
                        ([{"type": pr.SM_PLUGIN_TYPE, "uid": "synthetic-sm"}] * 2, "ambiguous"),
                        ([{"type": pr.SM_PLUGIN_TYPE, "uid": "bad:*"}], "invalid_uid"),
                        ([{"type": pr.SM_PLUGIN_TYPE, "uid": "synthetic-sm"}], "available")):
        for tokens in ((), selected):
            st = mock.Mock()
            st.get_synthetic_datasources.return_value = (200, body)
            have = {"datasources:query": [query[1], unrelated[1]], pr.SM_PROBES_PAIR[0]: [""]}
            permissions, removable, observed = cli.reader_policy(st, have, product_reads=tokens)
            st.get_synthetic_datasources.assert_called_once_with()
            assert observed == state
            wanted = pr.permission_pairs(permissions)
            assert unrelated in pr.dangerous_extra_pairs(have, wanted, removable)
            assert (query in wanted) == (bool(tokens) and state == "available")
            assert (query in removable) == (not tokens and state == "available")
            assert (pr.SM_PROBES_PAIR in removable) == (not tokens and state == "available")
            if state != "available":
                assert query in pr.dangerous_extra_pairs(have, wanted, removable)
                assert not (pr.synthetic_pairs("synthetic-sm") & removable)
    st = mock.Mock()
    st.get_synthetic_datasources.return_value = (200, [{"type": pr.SM_PLUGIN_TYPE, "uid": "synthetic-sm"}])
    wrong = {"datasources:query": [pr.WRITE_STACK_PAIR[1]]}
    permissions, removable, _ = cli.reader_policy(st, wrong, write_stack=False)
    st.get_synthetic_datasources.assert_called_once_with()
    assert pr.WRITE_STACK_PAIR not in pr.permission_pairs(permissions)
    assert pr.WRITE_STACK_PAIR in removable  # legacy telemetry removal rule unchanged
    assert query not in removable
    assert pr.SM_PROBES_PAIR not in removable


if __name__ == "__main__":
    unittest.main()
