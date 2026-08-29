#!/usr/bin/env bash
# Audit the ONE tag that makes this platform's spend isolatable in Cost Explorer.
#
# WHY THIS SCRIPT EXISTS: Cost Explorer can only group by activated allocation tags.
# `Namespace`, `Team`, `team` (`aws ce get-tags`). The four tags the resources already carried
# (`Purpose`, `Environment`, `Owner`, `Terraform`) are NOT activated and cannot be filtered on, so they
# look right in the console and are invisible in Cost Explorer.
#
# Most resources get the tag from Terraform. Two cannot, and this script is how you know they still have it:
#   * the ADOPTED S3 bucket  -  the AWS provider has NO standalone S3 tagging resource (verified against the
#     provider schema: twelve `*_tag` resources across 1,700 types, none for S3), so it is tagged out of
#     band and nothing in code will notice if that is lost;
#   * EventBridge Scheduler schedules, which are taggable only via their schedule GROUP. This module uses
#     the shared `default` group, so they stay untagged on purpose. Negligible cost; not checked here.
#
# Cost allocation tags are NOT retroactive, so a resource that loses this tag silently produces spend that
# can never be attributed. Run it after any apply that replaces storage, or whenever a Cost Explorer
# figure looks too low.
#
#   just check-tags              # audit, exit 1 if anything is missing
#   just check-tags --fix        # apply the tag to whatever is missing it, then re-audit
set -uo pipefail

REGION="${GCINSIGHT_S3_REGION:-eu-west-1}"
# No defaults: the prefix and bucket identify one deployment. Guessing either can audit or mutate a
# different installation when --fix is used.
PREFIX="${NAME_PREFIX:?set NAME_PREFIX to the terraform name_prefix of the deployment to audit}"
BUCKET="${GCINSIGHT_S3_BUCKET:?set GCINSIGHT_S3_BUCKET to the deployment bucket}"
SECRET="${GCINSIGHT_SECRET_NAME:-${PREFIX}/tokens}"
FIREHOSE_STREAM="${FIREHOSE_STREAM_NAME:-${PREFIX}-ecs-logs}"
# Optional override for a pre-stream audit. Once the stream exists, its live destination is the
# authority: the module accepts any adopted secret ARN, so assuming a conventional name can audit a
# different secret and report a false all-clear.
FIREHOSE_SECRET="${FIREHOSE_ACCESS_KEY_SECRET_ARN:-${FIREHOSE_SECRET_NAME:-}}"
KEY="Namespace"
WANT="${NAMESPACE_TAG_VALUE:-$PREFIX}"
FIX=0
[ "${1:-}" = "--fix" ] && FIX=1

missing=0
pass() { printf '  \033[32mok\033[0m   %-46s %s\n' "$1" "$2"; }
fail() { printf '  \033[31mMISS\033[0m %-46s %s\n' "$1" "${2:-<unset>}"; missing=$((missing + 1)); }

echo "Auditing ${KEY}=${WANT} (the only Cost Explorer-filterable tag) in ${REGION}"
echo

# --- ECS cluster ----------------------------------------------------------------------------------
cluster_arn=$(aws ecs describe-clusters --clusters "$PREFIX" --region "$REGION" \
  --query 'clusters[0].clusterArn' --output text 2>/dev/null)
got=$(aws ecs describe-clusters --clusters "$PREFIX" --include TAGS --region "$REGION" \
  --query "clusters[0].tags[?key=='${KEY}'].value" --output text 2>/dev/null)
if [ "$got" = "$WANT" ]; then pass "ECS cluster" "$got"; else
  fail "ECS cluster" "$got"
  [ "$FIX" = 1 ] && aws ecs tag-resource --resource-arn "$cluster_arn" \
    --tags "key=${KEY},value=${WANT}" --region "$REGION" >/dev/null 2>&1 && echo "       fixed"
fi

# --- task definitions -----------------------------------------------------------------------------
# Tags live on a REVISION, so a replaced task definition starts untagged unless Terraform supplies it.
for tier in t1 t2 t3 t4; do
  td=$(aws ecs describe-task-definition --task-definition "${PREFIX}-${tier}" --region "$REGION" \
    --query 'taskDefinition.taskDefinitionArn' --output text 2>/dev/null)
  got=$(aws ecs describe-task-definition --task-definition "${PREFIX}-${tier}" --include TAGS \
    --region "$REGION" --query "tags[?key=='${KEY}'].value" --output text 2>/dev/null)
  if [ "$got" = "$WANT" ]; then pass "task definition ${tier}" "$got"; else
    fail "task definition ${tier}" "$got"
    [ "$FIX" = 1 ] && aws ecs tag-resource --resource-arn "$td" \
      --tags "key=${KEY},value=${WANT}" --region "$REGION" >/dev/null 2>&1 && echo "       fixed"
  fi
done

# --- CloudWatch log group -------------------------------------------------------------------------
# `describe-log-groups` returns the ARN WITH a trailing `:*` and `tag-resource` rejects that form.
lg=$(aws logs describe-log-groups --log-group-name-prefix "/aws/ecs/${PREFIX}" --region "$REGION" \
  --query 'logGroups[0].arn' --output text 2>/dev/null)
lg="${lg%:\*}"
got=$(aws logs list-tags-for-resource --resource-arn "$lg" --region "$REGION" \
  --query "tags.${KEY}" --output text 2>/dev/null)
if [ "$got" = "$WANT" ]; then pass "CloudWatch log group" "$got"; else
  fail "CloudWatch log group" "$got"
  [ "$FIX" = 1 ] && aws logs tag-resource --resource-arn "$lg" --tags "${KEY}=${WANT}" \
    --region "$REGION" >/dev/null 2>&1 && echo "       fixed"
fi

# --- ECR repository -------------------------------------------------------------------------------
ecr=$(aws ecr describe-repositories --repository-names "$PREFIX" --region "$REGION" \
  --query 'repositories[0].repositoryArn' --output text 2>/dev/null)
got=$(aws ecr list-tags-for-resource --resource-arn "$ecr" --region "$REGION" \
  --query "tags[?Key=='${KEY}'].Value" --output text 2>/dev/null)
if [ "$got" = "$WANT" ]; then pass "ECR repository" "$got"; else
  fail "ECR repository" "$got"
  [ "$FIX" = 1 ] && aws ecr tag-resource --resource-arn "$ecr" \
    --tags "Key=${KEY},Value=${WANT}" --region "$REGION" >/dev/null 2>&1 && echo "       fixed"
fi

# --- S3 bucket: THE ONE NOTHING IN CODE PROTECTS --------------------------------------------------
got=$(aws s3api get-bucket-tagging --bucket "$BUCKET" --region "$REGION" \
  --query "TagSet[?Key=='${KEY}'].Value" --output text 2>/dev/null)
if [ "$got" = "$WANT" ]; then pass "S3 bucket ${BUCKET}" "$got"; else
  fail "S3 bucket ${BUCKET} (adopted, no TF route)" "$got"
  if [ "$FIX" = 1 ]; then
    # put-bucket-tagging REPLACES the whole set, so merge with whatever is already there.
    existing=$(aws s3api get-bucket-tagging --bucket "$BUCKET" --region "$REGION" \
      --output json 2>/dev/null | python3 -c 'import json,sys
try: cur={t["Key"]: t["Value"] for t in json.load(sys.stdin)["TagSet"]}
except Exception: cur={}
cur["'"${KEY}"'"]="'"${WANT}"'"
print(json.dumps({"TagSet":[{"Key":k,"Value":v} for k,v in sorted(cur.items())]}))')
    aws s3api put-bucket-tagging --bucket "$BUCKET" --region "$REGION" \
      --tagging "$existing" >/dev/null 2>&1 && echo "       fixed (merged, not replaced)"
  fi
fi

# --- Secrets Manager secret -----------------------------------------------------------------------
got=$(aws secretsmanager describe-secret --secret-id "$SECRET" --region "$REGION" \
  --query "Tags[?Key=='${KEY}'].Value" --output text 2>/dev/null)
if [ "$got" = "$WANT" ]; then pass "secret ${SECRET}" "$got"; else
  fail "secret ${SECRET}" "$got"
  [ "$FIX" = 1 ] && aws secretsmanager tag-resource --secret-id "$SECRET" \
    --tags "Key=${KEY},Value=${WANT}" --region "$REGION" >/dev/null 2>&1 && echo "       fixed"
fi

# --- Optional ECS-log Firehose path ---------------------------------------------------------------
# Default-off resources are audited only when the delivery stream exists. A disabled module must not
# make the repository-wide tag gate fail because there is intentionally nothing to tag.
firehose_arn=$(aws firehose describe-delivery-stream --delivery-stream-name "$FIREHOSE_STREAM" \
  --region "$REGION" --query 'DeliveryStreamDescription.DeliveryStreamARN' --output text 2>/dev/null)
if [ -n "$firehose_arn" ] && [ "$firehose_arn" != "None" ]; then
  got=$(aws firehose list-tags-for-delivery-stream --delivery-stream-name "$FIREHOSE_STREAM" \
    --region "$REGION" --query "Tags[?Key=='${KEY}'].Value" --output text 2>/dev/null)
  if [ "$got" = "$WANT" ]; then pass "Firehose delivery stream" "$got"; else
    fail "Firehose delivery stream" "$got"
    [ "$FIX" = 1 ] && aws firehose tag-delivery-stream --delivery-stream-name "$FIREHOSE_STREAM" \
      --tags "Key=${KEY},Value=${WANT}" --region "$REGION" >/dev/null 2>&1 && echo "       fixed"
  fi

  if [ -z "$FIREHOSE_SECRET" ]; then
    FIREHOSE_SECRET=$(aws firehose describe-delivery-stream \
      --delivery-stream-name "$FIREHOSE_STREAM" --region "$REGION" \
      --query 'DeliveryStreamDescription.Destinations[0].HttpEndpointDestinationDescription.SecretsManagerConfiguration.SecretARN' \
      --output text 2>/dev/null)
    [ "$FIREHOSE_SECRET" = "None" ] && FIREHOSE_SECRET=""
  fi

  account_id=$(aws sts get-caller-identity --query Account --output text 2>/dev/null)
  firehose_bucket="${FIREHOSE_BACKUP_BUCKET:-${PREFIX}-fh-failed-${account_id}}"
  got=$(aws s3api get-bucket-tagging --bucket "$firehose_bucket" --region "$REGION" \
    --query "TagSet[?Key=='${KEY}'].Value" --output text 2>/dev/null)
  if [ "$got" = "$WANT" ]; then pass "Firehose failed-record bucket" "$got"; else
    fail "Firehose failed-record bucket" "$got"
    if [ "$FIX" = 1 ]; then
      # put-bucket-tagging replaces every tag, so preserve the resource's full existing set.
      existing=$(aws s3api get-bucket-tagging --bucket "$firehose_bucket" --region "$REGION" \
        --output json 2>/dev/null | python3 -c 'import json,sys
try: cur={t["Key"]: t["Value"] for t in json.load(sys.stdin)["TagSet"]}
except Exception: cur={}
cur["'"${KEY}"'"]="'"${WANT}"'"
print(json.dumps({"TagSet":[{"Key":k,"Value":v} for k,v in sorted(cur.items())]}))')
      aws s3api put-bucket-tagging --bucket "$firehose_bucket" --region "$REGION" \
        --tagging "$existing" >/dev/null 2>&1 && echo "       fixed (merged, not replaced)"
    fi
  fi

  got=""
  if [ -n "$FIREHOSE_SECRET" ]; then
    got=$(aws secretsmanager describe-secret --secret-id "$FIREHOSE_SECRET" --region "$REGION" \
      --query "Tags[?Key=='${KEY}'].Value" --output text 2>/dev/null)
  fi
  if [ "$got" = "$WANT" ]; then pass "Firehose access-key secret" "$got"; else
    fail "Firehose access-key secret" "$got"
    [ "$FIX" = 1 ] && [ -n "$FIREHOSE_SECRET" ] && \
      aws secretsmanager tag-resource --secret-id "$FIREHOSE_SECRET" \
      --tags "Key=${KEY},Value=${WANT}" --region "$REGION" >/dev/null 2>&1 && echo "       fixed"
  fi

  for role_spec in \
    "${PREFIX}-logs-subscription|Firehose subscription role" \
    "${PREFIX}-firehose|Firehose delivery role"; do
    role_name="${role_spec%%|*}"
    role_label="${role_spec#*|}"
    got=$(aws iam list-role-tags --role-name "$role_name" \
      --query "Tags[?Key=='${KEY}'].Value" --output text 2>/dev/null)
    if [ "$got" = "$WANT" ]; then pass "$role_label" "$got"; else
      fail "$role_label" "$got"
      [ "$FIX" = 1 ] && aws iam tag-role --role-name "$role_name" \
        --tags "Key=${KEY},Value=${WANT}" >/dev/null 2>&1 && echo "       fixed"
    fi
  done
else
  printf '  \033[33mskip\033[0m %-46s %s\n' "Optional Firehose log path" "not created"
fi

echo
if [ "$missing" -gt 0 ]; then
  echo "${missing} resource(s) missing ${KEY}=${WANT}."
  [ "$FIX" = 0 ] && echo "Re-run with --fix to apply, then confirm with 'aws ce get-tags' after ~24h."
  exit 1
fi
echo "All cost-bearing resources carry ${KEY}=${WANT}."
echo "Reminder: tags are NOT retroactive and take ~24h to appear in Cost Explorer."
