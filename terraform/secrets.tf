# The credential container. VALUES ARE NEVER MANAGED HERE.
#
# Terraform state is not a secret store and a plan output is not a private channel, so this module
# creates the container and the IAM that reads it, and the two tokens are written out of band. That is
# also the conventional pattern, so it needs no separate explanation in the
# runbook.
#
# The collector wants TWO tokens, not one, and the split is the security property:
#
#   reader  org realm, read-only scopes, reaches all stacks.
#   writer  STACK realm - one stack - with metrics:write + logs:write.
#
# The writer physically cannot touch any other stack: the realm forbids it, so it is not a scope check
# that could be misconfigured. A single combined credential that could both scan the estate and write
# to it would be strictly more dangerous than the pair.

resource "aws_secretsmanager_secret" "tokens" {
  count = var.create_secret ? 1 : 0

  name        = local.secret_name
  description = "Grafana Cloud tokens for the ${var.name_prefix} collector: ${var.reader_secret_key} (read, org realm) and ${var.writer_secret_key} (write, single-stack realm)."
  tags        = local.tags

  # Long enough to notice and recover a deletion, short enough that a name can be reused within a
  # sprint. Zero-day deletion is not offered here on purpose: recreating the container is easy,
  # re-minting and re-distributing two Grafana Cloud tokens is not.
  recovery_window_in_days = 7
}

data "aws_secretsmanager_secret" "tokens" {
  count = var.create_secret ? 0 : 1

  name = local.secret_name
}

# Cost-allocation tags on an ADOPTED secret. `aws_secretsmanager_tag` manages one tag key WITHOUT owning
# the secret, which is the only way a module can tag something it was told not to create.
#
# **OPT-IN (default off) on purpose.** This module's posture is that it does not touch resources it did not
# create; tagging is benign metadata rather than a configuration change, but a module quietly writing to an
# adopted secret is still surprising. The caller asks for it explicitly.
#
# **There is no S3 equivalent - verified against the provider schema, not assumed.** Of 1,700 AWS resource
# types there are twelve standalone `*_tag` resources (`aws_ec2_tag`, `aws_ecs_tag`, `aws_secretsmanager_tag`,
# ...) and **none for S3**. So an adopted bucket cannot be tagged by Terraform at all without importing and
# managing it, which is exactly what `create_bucket = false` exists to avoid. Tag an adopted bucket out of
# band and see RUNBOOK.md; the bucket this module CREATES is tagged normally.
# **A FIRST APPLY MAY ERROR ON ONE KEY AND THE TAG IS STILL APPLIED. Re-run and it converges.**
# Observed 2026-08-19 creating five of these at once:
#
#   Error: reading secretsmanager resource (arn:...:secret:gcinsight/org-cap-CQVuvv) tag (Owner):
#   empty result
#
# The WRITE succeeded - the tag was present on the secret immediately afterwards, and the
# resource was in state - so this is the provider's post-create read-back hitting DescribeSecret before the
# tag set is consistent, not a failed tag. `TagResource` is additive rather than a replace, so five
# concurrent single-key writes do not clobber each other; only the read races. A second
# `apply -target=module.gcinsight` returned "No changes", which is what a consistency race looks like
# and what a real failure does not.
#
# Deliberately NOT serialised with `depends_on`: adding artificial ordering to work around a transient read
# would slow every apply to fix a cosmetic error. **`just check-tags` is the safety net** for the case
# that would actually matter - a tag genuinely absent - and it exits non-zero on a miss.
resource "aws_secretsmanager_tag" "adopted" {
  for_each = var.create_secret || !var.tag_adopted_secret ? {} : local.tags

  secret_id = local.secret_arn
  key       = each.key
  value     = each.value
}

# No aws_secretsmanager_secret_version resource, deliberately. If one existed, the tokens would be in
# state and in every plan diff. Write them with:
#
#   aws secretsmanager put-secret-value --secret-id <secret_name> --secret-string \
#     '{"GCINSIGHT_READ_TOKEN":"<reader>","GCINSIGHT_WRITE_TOKEN":"<writer>","GCINSIGHT_ORG_ID":"<org>"}'
#
# The task reads individual JSON keys, so extra keys in the object are harmless - the live secret also
# carries provenance fields recording which policy minted each token and when it expires.
