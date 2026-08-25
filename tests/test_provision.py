"""Per-stack reader provisioning (PLAN 17D + 17D-review).

Every test here corresponds to a failure mode probed live against the organisation stacks on 2026-08-20. The
logic is small; the reason it needs tests is that each branch, if wrong, produces a run that LOOKS
successful  -  a stack reading green with no working credential, or 273 roles rewritten daily.
"""

from __future__ import annotations

import datetime as dt
import unittest

from collector import provision as pr

NOW = dt.datetime(2026, 8, 20, 12, 0, tzinfo=dt.timezone.utc)


def _p(**kw):
    base = dict(sa_exists=True, secret_exists=True, token_status=200, basic_role="None",
                role_exists=True, role_actions=pr.DESIRED_ACTIONS, assigned=True)
    base.update(kw)
    return pr.Presence(**base)


class TokenNamingTest(unittest.TestCase):
    """Verified live: token names are unique per ORG, not per service account."""

    def test_the_token_name_carries_the_slug(self):
        self.assertIn("stack039", pr.token_name("stack039"))

    def test_two_stacks_never_ask_for_the_same_token_name(self):
        self.assertNotEqual(pr.token_name("stack039"), pr.token_name("obs-hub"))

    def test_the_ssm_path_is_per_stack_not_one_shared_blob(self):
        self.assertNotEqual(pr.ssm_path("a"), pr.ssm_path("b"))
        self.assertTrue(pr.ssm_path("a").startswith(pr.SSM_PREFIX))


class ClassifyTest(unittest.TestCase):
    def test_an_active_stack_is_provisionable(self):
        self.assertEqual(pr.classify({"slug": "a", "status": "active"}), pr.PROVISIONABLE)

    def test_a_paused_stack_is_not_provisionable_rather_than_missing(self):
        """Verified: a paused stack 403s on /api/serviceaccounts/search itself.

        Classing these as 'missing' would fire the coverage alert forever on four test leftovers.
        """
        self.assertEqual(pr.classify({"slug": "a", "status": "paused"}), pr.PAUSED)

    def test_opt_out_beats_paused_so_the_reason_shown_is_our_decision(self):
        state = pr.classify({"slug": "a", "status": "paused"}, opted_out=["a"])
        self.assertEqual(state, pr.OPTED_OUT)

    def test_an_opted_out_active_stack_is_skipped(self):
        self.assertEqual(pr.classify({"slug": "a", "status": "active"}, opted_out=["a"]),
                         pr.OPTED_OUT)


class RoleDriftTest(unittest.TestCase):
    def test_an_identical_role_is_not_drift(self):
        self.assertFalse(pr.role_drift(pr.DESIRED_ACTIONS))

    def test_order_is_not_drift(self):
        """Ordered comparison would rewrite 273 roles every run and flood the audit log."""
        self.assertFalse(pr.role_drift(list(reversed(sorted(pr.DESIRED_ACTIONS)))))

    def test_the_folders_read_grafana_adds_itself_is_not_drift(self):
        """Verified live: the effective set is 12, not the 11 we declare."""
        self.assertFalse(pr.role_drift(set(pr.DESIRED_ACTIONS) | {"folders:read"}))

    def test_a_missing_declared_action_IS_drift(self):
        short = set(pr.DESIRED_ACTIONS) - {"serviceaccounts:read"}
        self.assertTrue(pr.role_drift(short))

    def test_an_empty_role_is_drift(self):
        self.assertTrue(pr.role_drift([]))


class PlanActionTest(unittest.TestCase):
    def test_a_fully_provisioned_stack_needs_nothing(self):
        self.assertEqual(pr.plan_action(_p()), pr.OK)

    def test_a_missing_service_account_is_created_first(self):
        self.assertEqual(pr.plan_action(_p(sa_exists=False)), pr.CREATE_SA)

    def test_an_existing_sa_with_no_stored_token_mints_rather_than_reporting_healthy(self):
        """THE trap: a crash between creating the SA and storing its token.

        A name-only coverage check reads healthy for ever while the stack has no usable credential.
        """
        self.assertEqual(pr.plan_action(_p(secret_exists=False, token_status=None)), pr.MINT_TOKEN)

    def test_a_401_remints_because_the_credential_is_dead(self):
        """Verified live: a revoked token returns 401."""
        self.assertEqual(pr.plan_action(_p(token_status=401)), pr.MINT_TOKEN)

    def test_a_403_on_an_otherwise_correct_stack_does_NOT_remint(self):
        """Verified live: a valid token with wrong permissions returns 403.

        Re-minting would loop for ever without fixing anything, because the token was never the problem.
        """
        self.assertEqual(pr.plan_action(_p(token_status=403)), pr.UNEXPLAINED_403)

    def test_an_unexplained_403_is_not_reported_as_provisioned(self):
        """It has a credential and reads nothing. Counting it healthy is the worst of both."""
        outcomes = [pr.Outcome("x", pr.PROVISIONABLE, pr.UNEXPLAINED_403,
                               first_seen_missing="2026-08-19T12:00:00Z")]
        m = dict((n, v) for n, _, v in pr.coverage_metrics(outcomes, now=NOW))
        self.assertEqual(m["gcinsight_stacks_missing_credential"], 1.0)
        self.assertEqual(m["gcinsight_stacks_provisioned"], 0.0)

    def test_a_lost_role_is_recreated(self):
        self.assertEqual(pr.plan_action(_p(role_exists=False)), pr.ENSURE_ROLE)

    def test_a_drifted_role_is_patched_not_recreated(self):
        """Role creation is NOT idempotent  -  a duplicate name returns 400."""
        thin = set(pr.DESIRED_ACTIONS) - {"grafana-assistant-app.usage:read"}
        self.assertEqual(pr.plan_action(_p(role_actions=thin)), pr.PATCH_ROLE)

    def test_a_lost_assignment_is_repaired_even_though_the_role_still_exists(self):
        self.assertEqual(pr.plan_action(_p(assigned=False)), pr.ASSIGN_ROLE)

    def test_a_basic_role_other_than_None_is_reset(self):
        """Our 'provably read-only' claim to the organisation depends on the basic role staying None."""
        self.assertEqual(pr.plan_action(_p(basic_role="Viewer")), pr.RESET_BASIC_ROLE)
        self.assertEqual(pr.plan_action(_p(basic_role="Admin")), pr.RESET_BASIC_ROLE)

    def test_an_unknown_basic_role_is_not_treated_as_broken(self):
        """`None` here means 'not probed', which must not trigger a write."""
        self.assertEqual(pr.plan_action(_p(basic_role=None)), pr.OK)

    def test_the_role_is_fixed_before_the_credential_is_minted(self):
        """Minting first would store a token that 403s on everything."""
        self.assertEqual(
            pr.plan_action(_p(role_exists=False, secret_exists=False, token_status=None)),
            pr.ENSURE_ROLE)


class PruneTest(unittest.TestCase):
    def test_a_credential_for_a_departed_stack_is_pruned(self):
        self.assertEqual(pr.prune_targets(["a", "b"], ["a"]), ["b"])

    def test_nothing_is_pruned_when_everything_is_still_live(self):
        self.assertEqual(pr.prune_targets(["a", "b"], ["a", "b"]), [])

    def test_an_empty_inventory_prunes_NOTHING(self):
        """A failed inventory call must never read as 'the estate is gone' and delete 273 credentials."""
        self.assertEqual(pr.prune_targets(["a", "b"], []), [])

    def test_a_new_stack_with_no_credential_yet_is_not_a_prune_target(self):
        self.assertEqual(pr.prune_targets(["a"], ["a", "brand-new"]), [])


class CoverageReportingTest(unittest.TestCase):
    def _outcomes(self):
        return [
            pr.Outcome("ok1", pr.PROVISIONABLE, pr.OK),
            pr.Outcome("late", pr.PROVISIONABLE, pr.CREATE_SA,
                       first_seen_missing="2026-08-17T12:00:00Z"),
            pr.Outcome("recent", pr.PROVISIONABLE, pr.MINT_TOKEN,
                       first_seen_missing="2026-08-20T06:00:00Z"),
            pr.Outcome("teststack1", pr.PAUSED, pr.OK),
            pr.Outcome("skipme", pr.OPTED_OUT, pr.OK),
        ]

    def test_paused_and_opted_out_stacks_are_not_counted_as_missing(self):
        m = dict((n, v) for n, _, v in pr.coverage_metrics(self._outcomes(), now=NOW))
        self.assertEqual(m["gcinsight_stacks_missing_credential"], 2.0)

    def test_the_age_reported_is_the_OLDEST_gap(self):
        m = dict((n, v) for n, _, v in pr.coverage_metrics(self._outcomes(), now=NOW))
        self.assertEqual(m["gcinsight_missing_credential_age_seconds"], 3 * 86400.0)

    def test_no_age_is_emitted_when_nothing_is_missing(self):
        """A zero would be indistinguishable from a run that measured nothing."""
        names = [n for n, _, _ in pr.coverage_metrics([pr.Outcome("a", pr.PROVISIONABLE, pr.OK)],
                                                      now=NOW)]
        self.assertNotIn("gcinsight_missing_credential_age_seconds", names)

    def test_the_metrics_are_estate_wide_and_carry_no_stack_label(self):
        """273 x per-stack gauges is what the view is for."""
        for _, labels, _ in pr.coverage_metrics(self._outcomes(), now=NOW):
            self.assertEqual(labels, {})

    def test_an_unparseable_first_seen_does_not_crash_the_run(self):
        out = [pr.Outcome("x", pr.PROVISIONABLE, pr.CREATE_SA, first_seen_missing="not-a-date")]
        names = [n for n, _, _ in pr.coverage_metrics(out, now=NOW)]
        self.assertIn("gcinsight_stacks_missing_credential", names)
        self.assertNotIn("gcinsight_missing_credential_age_seconds", names)

    def test_the_view_names_every_stack_and_why(self):
        rows = pr.coverage_view(self._outcomes())
        self.assertEqual(len(rows), 5)
        by = {r["Stack"]: r for r in rows}
        self.assertEqual(by["teststack1"]["State"], pr.PAUSED)
        self.assertEqual(by["skipme"]["State"], pr.OPTED_OUT)

    def test_the_view_puts_actionable_rows_first(self):
        rows = pr.coverage_view(self._outcomes())
        self.assertIn(rows[0]["Stack"], {"late", "recent"})


class FrozenSeamTest(unittest.TestCase):
    """These names identify live objects. A rename is a migration, not an edit."""

    #: The reviewed surface, action by action. A count alone would let one action be swapped for
    #: another without the test noticing, and every one is a grant on each provisioned stack.
    REVIEWED = {
        "plugins.app:access": "the Assistant, Adaptive Logs, Metrics and Traces plugin gateways",
        "grafana-assistant-app.usage:read": "Assistant aggregate usage",
        "grafana-assistant-app.investigations:read": "investigation counts",
        "grafana-assistant-app.investigations.all:read": "tenant investigation coverage",
        "grafana-assistant-app.investigations.system:read": "Assistant-created investigation counts",
        "grafana-assistant-app.mcps.tenant:read": "tenant MCP integration inventory",
        "grafana-assistant-app.skills.tenant:read": "tenant skill inventory",
        "grafana-assistant-app.automations.tenant:read": "tenant automation inventory",
        "grafana-assistant-app.rules.tenant:read": "tenant rule inventory",
        "grafana-assistant-app.watcher-agents:read": "watcher capability boundary checks",
        "grafana-adaptivelogs-app.patterns:read": "log patterns and drop-rate recommendations",
        # Adaptive Metrics: rules, recommendations, segments and config are all reachable on the Mimir
        # host with the ORG token. Only exemptions need a stack action, and an exemption caps the
        # achievable saving, so a savings figure computed without it overstates what can be applied.
        "grafana-adaptive-metrics-app.plugin:access": "the Adaptive Metrics plugin gateway",
        "grafana-adaptive-metrics-app.exemptions:read": "metrics and labels deliberately protected from aggregation",
        # Adaptive Traces. The plugin defines ONE role, admin, bundling writes and deletes with the
        # reads, so these actions are cherry-picked and that role is never assigned. Most Adaptive
        # Traces telemetry needs no credential at all - grafanacloud-usage carries eight
        # ..._adaptivetraces_* series - so these exist for the policy INVENTORY the datasource lacks.
        "grafana-adaptivetraces-app.plugin:access": "the Adaptive Traces plugin gateway",
        "grafana-adaptivetraces-app.policies:read": "sampling policy inventory, including policies inactive in the window",
        "grafana-adaptivetraces-app.recommendations:read": "sampling recommendations not yet applied",
        "grafana-adaptivetraces-app.config:read": "Adaptive Traces enablement and configuration",
        "serviceaccounts:read": "the per-stack service-account inventory",
        "serviceaccounts.permissions:read": "what each service account can actually do",
        "datasources:read": "LIST datasources - not query them",
        "datasources.caching:read": "query-caching settings, a cost lever",
        "datasources:query": "query ONE telemetry datasource, uid-pinned",
        "folders:read": "folder inventory",
        "dashboards:read": "dashboard inventory, and public-dashboard enumeration",
        "snapshots:read": "snapshot inventory, the same exposure class as public dashboards",
        "teams:read": "team inventory for the ownership directory",
        "teams.permissions:read": "team membership",
        "teams.roles:read": "roles assigned to a team",
        "users.roles:read": "roles assigned to a user or service account",
        "roles:read": "custom-role inventory, so RBAC sprawl is visible",
        "alert.rules:read": "alert rule inventory",
        "alert.notifications.receivers:read": "contact points, so 'alerts going nowhere' is measurable",
    }

    def test_the_declared_role_carries_exactly_the_reviewed_actions(self):
        """Adding an action must be a deliberate edit HERE, not a quiet drift in the provisioner.

        A role rollout costs a transient Admin identity on every stack in the estate. Adaptive Metrics
        exemptions and the Adaptive Traces read actions were added deliberately and are explicitly
        approved; the Traces plugin's only role bundles writes, so the reads are cherry-picked and that
        role is never assigned.
        """
        declared = set(pr.DESIRED_ACTIONS)
        self.assertEqual(declared, set(self.REVIEWED),
                         "the declared role no longer matches the reviewed surface")
        self.assertEqual(len(pr.DESIRED_ACTIONS), 32)

    def test_adaptive_traces_grants_reads_and_never_the_bundled_admin_role(self):
        """The plugin defines ONE role, admin, bundling writes and deletes with the reads.

        So the reads are cherry-picked into our own custom role. Any write, delete or apply action
        reaching the declared set would be that bundle leaking in.
        """
        traces = {
            action for action, _ in pr.DESIRED_PAIRS
            if action.startswith("grafana-adaptivetraces-app.")
        }
        self.assertEqual(traces, {
            "grafana-adaptivetraces-app.plugin:access",
            "grafana-adaptivetraces-app.policies:read",
            "grafana-adaptivetraces-app.recommendations:read",
            "grafana-adaptivetraces-app.config:read",
        })
        for action in traces:
            self.assertTrue(action.endswith((":read", ":access")), action)

    def test_adaptive_metrics_grants_only_exemptions_because_the_rest_is_org_reachable(self):
        """Rules, recommendations, segments and config answer to the ORG token on the Mimir host.

        Only exemptions are served by the plugin backend, so only exemptions justify a stack grant.
        """
        metrics = {
            action for action, _ in pr.DESIRED_PAIRS
            if action.startswith("grafana-adaptive-metrics-app.")
        }
        self.assertEqual(metrics, {
            "grafana-adaptive-metrics-app.plugin:access",
            "grafana-adaptive-metrics-app.exemptions:read",
        })

    def test_no_pair_is_both_desired_and_retired(self):
        """A pair in both sets makes the provisioner fight itself.

        It would grant the pair, read it back as drift, remove it, and rewrite the role on every stack
        on every run for ever - a transient Admin identity per stack per run, permanently.
        """
        self.assertEqual(pr.DESIRED_PAIRS & pr.RETIRED_PAIRS, frozenset())
        self.assertEqual(
            pr.permission_pairs(pr.desired_permissions(write_stack=True)) & pr.RETIRED_PAIRS,
            frozenset(),
        )

    def test_adaptive_traces_mutations_are_explicitly_refused(self):
        refused = {
            "grafana-adaptivetraces-app.recommendations:apply",
            "grafana-adaptivetraces-app.policies:write",
            "grafana-adaptivetraces-app.policies:delete",
            "grafana-adaptivetraces-app.config:write",
        }
        self.assertLessEqual(refused, set(pr.REFUSED_ACTIONS))
        self.assertTrue(refused.isdisjoint(pr.DESIRED_ACTIONS))

    def test_datasource_READ_is_estate_wide_and_datasource_QUERY_is_not(self):
        """The distinction that cost this platform real capability by being conflated.

        `datasources:*` on QUERY would be query rights over every datasource on 269 customer stacks,
        which is their production data. `datasources:*` on READ only LISTS them. So the list is
        estate-wide and the query right stays pinned to one Grafana-provisioned telemetry datasource.
        """
        ordinary = pr.desired_permissions(write_stack=False)
        write_stack = pr.desired_permissions(write_stack=True)
        ordinary_query = {p.get("scope") for p in ordinary
                          if p["action"] == "datasources:query"}
        write_query = {p.get("scope") for p in write_stack
                       if p["action"] == "datasources:query"}
        self.assertEqual(ordinary_query, {f"datasources:uid:{pr.USAGE_INSIGHTS_DS_UID}"})
        self.assertEqual(write_query, ordinary_query | {f"datasources:uid:{pr.USAGE_DS_UID}"})
        self.assertTrue(all(scope != "datasources:*" for scope in write_query))
        self.assertIn({"action": "datasources:read", "scope": "datasources:*"}, ordinary)
        self.assertIn({"action": "datasources.caching:read", "scope": "datasources:*"}, ordinary)

    def test_dashboards_read_is_scoped_to_dashboards_not_folders(self):
        """A dashboard in the General location sits in no folder, so a folder-scoped grant misses it -
        and a dashboard missed by a compliance check reads as compliant."""
        scope = [p.get("scope") for p in pr.DESIRED_PERMISSIONS
                 if p["action"] == "dashboards:read"][0]
        self.assertEqual(scope, "dashboards:*")

    def test_the_refusal_list_is_declared_and_none_of_it_is_granted(self):
        """A future 'we just need one more read' has to argue with this list first."""
        self.assertTrue(pr.REFUSED_ACTIONS)
        for action, reason in pr.REFUSED_ACTIONS.items():
            with self.subTest(action=action):
                self.assertNotIn(action, pr.DESIRED_ACTIONS)
                self.assertTrue(reason, "a refusal without a reason is not a decision")

    def test_no_secret_reading_action_is_granted(self):
        """Every `.secrets:read` variant exports DECRYPTED secrets. None may ever be declared."""
        for action in pr.DESIRED_ACTIONS:
            self.assertNotIn("secrets:", action)
            self.assertNotIn("securevalues", action)

    @staticmethod
    def _complete():
        """A permissions payload holding every declared pair.

        Built by APPENDING scopes per action, not by a dict comprehension over the pairs: two entries
        share the action `plugins.app:access`, so a comprehension keeps one scope and silently drops the
        other - which is the exact failure this whole comparison exists to catch.
        """
        out: dict[str, list[str]] = {}
        for action, scope in pr.DESIRED_PAIRS:
            out.setdefault(action, []).append(scope or "")
        return out

    def test_drift_is_compared_on_action_and_scope_together(self):
        """`plugins.app:access` is declared twice at different plugin scopes, so a name-only comparison
        would call the role complete while Adaptive Logs stayed silently unreachable. Grafana also
        attaches `folders:read` itself at `folders:uid:sharedwithme`, which satisfies nothing declared.
        """
        complete = self._complete()
        self.assertFalse(pr.role_drift(complete))

        one_plugin_missing = dict(complete)
        one_plugin_missing["plugins.app:access"] = ["plugins:id:grafana-assistant-app"]
        self.assertTrue(pr.role_drift(one_plugin_missing))
        self.assertIn(("plugins.app:access", f"plugins:id:{pr.ADAPTIVE_LOGS_PLUGIN}"),
                      pr.missing_pairs(one_plugin_missing))

        grafanas_own_folders_read = dict(complete)
        grafanas_own_folders_read["folders:read"] = ["folders:uid:sharedwithme"]
        self.assertTrue(pr.role_drift(grafanas_own_folders_read),
                       "a pseudo-folder grant must not satisfy a folders:* declaration")

    def test_an_extra_permission_grafana_attached_is_not_drift(self):
        """Demanding equality would rewrite every role in the estate, daily, for ever."""
        extra = self._complete()
        extra["annotations:read"] = ["annotations:*"]
        self.assertFalse(pr.role_drift(extra))

    def test_no_declared_action_can_write(self):
        """`query` is a read verb: it runs a query against a datasource and cannot mutate anything.
        The check is stated both ways round so a new verb has to be considered rather than slipping in
        under a permissive allow-list."""
        readonly = {"read", "access", "query"}
        forbidden = {"write", "create", "delete", "admin", "edit", "update", "add", "remove"}
        for a in pr.DESIRED_ACTIONS:
            verb = a.rpartition(":")[2]
            self.assertIn(verb, readonly, f"{a} is not a read")
            self.assertNotIn(verb, forbidden, f"{a} can mutate")

    def test_chats_access_is_deliberately_absent(self):
        """The credential must not be able to open an Assistant conversation."""
        self.assertNotIn("grafana-assistant-app.chats:access", pr.DESIRED_ACTIONS)

    def test_the_admin_token_ttl_is_short_enough_that_a_crashed_run_leaves_an_inert_leftover(self):
        self.assertLessEqual(pr.ADMIN_TOKEN_TTL, 1800)


if __name__ == "__main__":
    unittest.main()


class NeedsRepairTest(unittest.TestCase):
    """Phase 1 must be read-only, so it may only reason from facts obtainable without an Admin token."""

    def test_a_healthy_stack_needs_no_repair_and_therefore_no_gcom_write(self):
        self.assertFalse(pr.needs_repair(_p()))

    def test_a_missing_service_account_needs_repair(self):
        self.assertTrue(pr.needs_repair(_p(sa_exists=False)))

    def test_an_sa_with_no_stored_credential_needs_repair(self):
        self.assertTrue(pr.needs_repair(_p(secret_exists=False, token_status=None)))

    def test_a_dead_credential_needs_repair(self):
        self.assertTrue(pr.needs_repair(_p(token_status=401)))

    def test_a_403_needs_repair(self):
        self.assertTrue(pr.needs_repair(_p(token_status=403)))

    def test_a_flipped_basic_role_needs_repair_even_though_reads_still_work(self):
        self.assertTrue(pr.needs_repair(_p(basic_role="Admin")))

    def test_a_credential_missing_a_declared_action_needs_repair(self):
        thin = frozenset(pr.DESIRED_ACTIONS) - {"serviceaccounts:read"}
        self.assertTrue(pr.needs_repair(_p(role_actions=thin)))

    def test_the_extra_folders_read_does_not_trigger_pointless_repair(self):
        """273 needless Admin identities per run would be the cost of getting this wrong."""
        self.assertFalse(pr.needs_repair(_p(role_actions=frozenset(pr.DESIRED_ACTIONS) | {"folders:read"})))
