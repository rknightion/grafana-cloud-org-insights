set shell := ["bash", "-euo", "pipefail", "-c"]

# show the task surface
default:
    @just --list

# create a repo-local virtualenv and install the pinned pytest test runner (idempotent)
setup:
    python3 -m venv .venv
    .venv/bin/pip install --disable-pip-version-check --quiet pytest==9.1.1

# format the justfile itself (this repo has no Python formatter - it ships zero third-party deps)
[group('check')]
fmt:
    just --fmt

# verify the justfile is formatted
[group('check')]
fmt-check:
    just --fmt --check

# refuse a stray Python dependency file - this collector is stdlib-only by design
[group('check')]
[script('bash')]
lint:
    for f in requirements.txt requirements-dev.txt pyproject.toml Pipfile poetry.lock; do
      if [ -e "$f" ]; then
        echo "error: $f exists - this project ships a stdlib-only collector; the container image" >&2
        echo "error: installs nothing. Adding a dependency needs a Dockerfile change and a review." >&2
        exit 1
      fi
    done
    echo "no dependency files present"

# run pytest offline, terminating its process tree above 2 GiB RSS or 9 minutes
[group('check')]
[no-exit-message]
test filter="":
    .venv/bin/python3 -m tests.guarded_pytest tests -q {{ if filter == "" { "" } else { "-k " + quote(filter) } }}

# validate and test the reusable terraform module, validate the standalone example, check formatting
[group('infra')]
[no-exit-message]
tf-validate:
    cd terraform && tofu init -backend=false && tofu validate && tofu test
    cd terraform/examples/standalone && tofu init -backend=false && tofu validate
    tofu fmt -check -recursive terraform

# scan files and origin history locally; CI retains its all-ref history scan
# requires GCINSIGHT_CUSTOMER_IDENTIFIER_PATTERN in the environment (a repository secret in CI)
[group('check')]
check-identifiers *args:
    bin/check-customer-identifiers --history {{ if env_var_or_default("CI", "") == "true" { "" } else { "--origin-refs" } }} {{ args }}

# refuse em dashes in shipped text; private gitignored codex state is not shipped
[group('check')]
[script('bash')]
no-em-dashes:
    set -uo pipefail
    hits=$(grep -rIn $'\342\200\224' . \
      --exclude-dir=.git --exclude-dir=backlog --exclude-dir=testdata \
      --exclude-dir=.venv --exclude-dir=__pycache__ --exclude-dir=.terraform \
      --exclude-dir=codex || true)
    if [ -n "$hits" ]; then
      echo "em dashes present, use a spaced hyphen:"
      echo "$hits"
      exit 1
    fi
    echo "clean"

# THE GATE - exactly what CI enforces
[group('check')]
check: fmt-check lint test tf-validate check-identifiers no-em-dashes

# audit (or, with --fix, repair) the one Cost Explorer allocation tag on a live deployment
# needs NAME_PREFIX and GCINSIGHT_S3_BUCKET in the environment - see bin/check-tags.sh header
[group('infra')]
check-tags *args:
    bin/check-tags.sh {{ args }}

# build the collector image locally without pushing (parity check)
[group('build')]
image *args:
    bin/build-and-push.sh --no-push {{ args }}

# build and push the collector image to ECR as an immutable sha-<commit> tag
# needs GCINSIGHT_ECR_REPOSITORY (or pass --repo via args); see bin/build-and-push.sh header for flags
[confirm('push a new collector image to the configured ECR repository?')]
[group('release')]
publish-image *args:
    bin/build-and-push.sh {{ args }}

# build and verify a local immutable consumer candidate (never pushes)
[group('build')]
consumer-build manifest deployment_root terraform *args:
    bin/consumer-build --manifest {{ quote(manifest) }} --deployment-root {{ quote(deployment_root) }} --terraform {{ quote(terraform) }} {{ args }}

# execute a tool under one validated non-secret consumer projection
[group('dev')]
consumer-exec manifest deployment_root terraform kind *args:
    bin/consumer-exec --manifest {{ quote(manifest) }} --deployment-root {{ quote(deployment_root) }} --terraform {{ quote(terraform) }} --kind {{ quote(kind) }} -- {{ args }}

# verify local dated natural-T2 stability artifacts only; never calls AWS or a tenant or writes evidence
[group('infra')]
[script('bash')]
verify-labelling-stability evidence:
    ulimit -t 60
    PYTHONDONTWRITEBYTECODE=1 .venv/bin/python3 - {{ quote(evidence) }} <<'PY'
    import base64
    import datetime as dt
    import hashlib
    import json
    import math
    import pathlib
    import re
    import sys
    from collector import config, identity, label_rules

    def require(ok):
        if not ok:
            raise ValueError("incomplete or inconsistent stability evidence")

    def load(path, with_body=False):
        path = pathlib.Path(path)
        require(path.is_file() and path.stat().st_size <= 64 * 1024 * 1024)
        with path.open("rb") as stream:
            raw = stream.read(64 * 1024 * 1024 + 1)
        require(len(raw) <= 64 * 1024 * 1024)
        def unique(pairs):
            out = {}
            for key, value in pairs:
                require(key not in out)
                out[key] = value
            return out
        parsed = json.loads(raw, object_pairs_hook=unique,
                            parse_constant=lambda _: require(False))
        return (parsed, raw) if with_body else parsed

    def instant(value):
        require(isinstance(value, str))
        value = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
        require(value.tzinfo is not None)
        return value.astimezone(dt.timezone.utc)

    def number(value):
        require(type(value) in (int, float) and math.isfinite(value))
        return value

    try:
        evidence = pathlib.Path(sys.argv[1]).resolve()
        root = load(evidence)
        require(root["v"] == 1 and type(root["v"]) is int)
        require(re.fullmatch(r"[0-9a-f]{40}", root["source_sha"]) is not None)
        require(re.fullmatch(r"sha256:[0-9a-f]{64}", root["image_digest"]) is not None)
        require(re.fullmatch(r"[0-9a-f]{64}", root["runtime_projection_digest"]) is not None)
        require(root["catalogue_version"] == label_rules.CATALOGUE.version)
        require(type(root["catalogue_version"]) is int)
        deadline = number(root["deadline_seconds"])
        require(0 < deadline <= 3600)
        tolerance = number(root["max_score_delta"])
        require(0 <= tolerance <= 100)
        tunables = config.label_inventory_tunables(json.dumps(root.get("tunables", {})))
        observations = root["observations"]
        require(isinstance(observations, list) and 3 <= len(observations) <= 32)
        previous = None
        schedule_arn = None
        source_policy = None
        first = None
        tasks = set()
        days = set()
        durations = []
        peaks = []
        validated = 0
        scores = []
        for observation in observations:
            for key in ("source_sha", "image_digest", "catalogue_version", "runtime_projection_digest"):
                require(observation[key] == root[key])
            task = observation["task_arn"]
            require(isinstance(task, str) and re.fullmatch(r"arn:[^:]+:ecs:[^:]+:[0-9]{12}:task/.+", task))
            require(task not in tasks)
            tasks.add(task)
            def artifact(key, with_body=False):
                relative = pathlib.Path(observation[key])
                return load(relative if relative.is_absolute() else evidence.parent / relative, with_body)
            descriptor = artifact("stopped_path")
            require(not descriptor.get("failures") and len(descriptor["tasks"]) == 1)
            stopped = descriptor["tasks"][0]
            require(stopped["taskArn"] == task and stopped["lastStatus"] == "STOPPED")
            started_at = instant(stopped["startedAt"])
            stopped_at = instant(stopped["stoppedAt"])
            require(0 < (stopped_at - started_at).total_seconds() <= deadline)
            containers = stopped["containers"]
            require(containers and all(type(c["exitCode"]) is int and c["exitCode"] == 0 for c in containers))
            collector = [c for c in containers if c["name"] == observation["container_name"]]
            require(len(collector) == 1 and collector[0]["imageDigest"] == root["image_digest"])
            definition = artifact("task_definition_path")["taskDefinition"]
            require(definition["taskDefinitionArn"] == stopped["taskDefinitionArn"])
            definitions = [c for c in definition["containerDefinitions"] if c["name"] == observation["container_name"]]
            require(len(definitions) == 1 and definitions[0]["image"].endswith("@" + root["image_digest"]))
            actual = definitions[0]
            def environment(entries):
                out = {}
                for entry in entries:
                    require(entry["name"] not in out)
                    out[entry["name"]] = entry["value"]
                return out
            env = environment(actual.get("environment", []))
            command = actual["command"]
            overrides = stopped.get("overrides", {}).get("containerOverrides", [])
            selected_overrides = [c for c in overrides if c["name"] == observation["container_name"]]
            require(len(selected_overrides) <= 1)
            for override in selected_overrides:
                env.update(environment(override.get("environment", [])))
                command = override.get("command", command)
            # Only the actual publishing invocation is admissible, including ECS overrides.
            # A whitelist also rejects argparse abbreviations and equals-form subset/debug flags.
            require(isinstance(command, list) and all(isinstance(arg, str) for arg in command))
            options = {}
            index = 0
            while index < len(command):
                arg = command[index]
                name, equals, value = arg.partition("=")
                require(name in {"--tier", "--deadline-seconds", "--concurrency"} and name not in options)
                if not equals:
                    index += 1
                    require(index < len(command))
                    value = command[index]
                require(bool(value))
                options[name] = value
                index += 1
            require(options["--tier"] == "t2" and float(options["--deadline-seconds"]) == deadline)
            if "--concurrency" in options:
                require(re.fullmatch(r"[1-9][0-9]*", options["--concurrency"]) is not None)
            require(env["GCINSIGHT_LABEL_INVENTORY_ENABLED"] == "1")
            require(env["GCINSIGHT_RUNTIME_CONFIG_DIGEST"] == root["runtime_projection_digest"])
            require(identity.verify_runtime_projection("scan", environ=env) == root["runtime_projection_digest"])
            require(config.label_inventory_tunables(env["GCINSIGHT_LABEL_INVENTORY_TUNABLES"]) == tunables)
            policy = (config.label_inventory_static_names(env["GCINSIGHT_LABEL_INVENTORY_STATIC_NAMES"]),
                      config.label_inventory_budget(env["GCINSIGHT_LABEL_INVENTORY_BUDGET_SECONDS"]))
            source_policy = source_policy or policy
            require(policy == source_policy)
            schedule = artifact("schedule_path")
            require(re.fullmatch(r"arn:[^:]+:scheduler:[^:]+:[0-9]{12}:schedule/.+", schedule["Arn"]))
            schedule_arn = schedule_arn or schedule["Arn"]
            require(schedule["Arn"] == schedule_arn and schedule["State"] == "ENABLED")
            target = schedule["Target"]
            require(target["Arn"] == stopped["clusterArn"])
            require(target["EcsParameters"]["TaskDefinitionArn"] == stopped["taskDefinitionArn"])
            launch = artifact("launch_path")
            if "Records" in launch:
                require(len(launch["Records"]) == 1)
                launch = launch["Records"][0]
            require(launch["eventName"] == "RunTask" and launch["eventSource"] == "ecs.amazonaws.com")
            principal = launch["userIdentity"]
            require(principal["sessionContext"]["sessionIssuer"]["arn"] == target["RoleArn"])
            require(principal.get("invokedBy") == "scheduler.amazonaws.com" or launch.get("userAgent") == "scheduler.amazonaws.com")
            require(launch["requestParameters"]["cluster"] == stopped["clusterArn"])
            require(launch["requestParameters"]["taskDefinition"] == stopped["taskDefinitionArn"])
            launched = launch["responseElements"]
            require(not launched.get("failures") and len(launched["tasks"]) == 1)
            require(launched["tasks"][0]["taskArn"] == task)
            require(launched["tasks"][0]["taskDefinitionArn"] == stopped["taskDefinitionArn"])
            scheduled_at = instant(launch["eventTime"])
            require(stopped_at <= dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=5))
            require(0 <= (started_at - scheduled_at).total_seconds() <= 900)
            day = scheduled_at.date()
            require(day not in days)
            days.add(day)
            if previous is not None:
                require(day == previous.date() + dt.timedelta(days=1))
                require(23 * 3600 <= (scheduled_at - previous).total_seconds() <= 25 * 3600)
            first = first or scheduled_at
            previous = scheduled_at
            scan, body = artifact("scan_path", with_body=True)
            meta = scan["meta"]
            witness = artifact("publication_path")
            request, response = witness["request"], witness["response"]
            require(request["Bucket"] == env["GCINSIGHT_S3_BUCKET"])
            stamp = meta["generated_at"].replace(":", "").replace("-", "")
            require(request["Key"] == f"scans/t2/{stamp}.json")
            version = request["VersionId"]
            require(isinstance(version, str) and bool(version.strip()) and version == version.strip() and version != "null")
            require(response["VersionId"] == version)
            require(type(response["ContentLength"]) is int and response["ContentLength"] == len(body))
            digest = hashlib.sha256(body).digest()
            require(witness["body_sha256"] == digest.hex())
            etag = response["ETag"]
            require(isinstance(etag, str) and re.fullmatch(r'"[0-9a-f]{32}(-[1-9][0-9]*)?"', etag))
            # Bind actual S3 response metadata to bytes, not just a caller's digest declaration.
            # Multipart/KMS ETags are opaque: only a native full-object SHA256 can bind those.
            if "ChecksumSHA256" in response:
                require(response["ChecksumType"] == "FULL_OBJECT")
                require(base64.b64decode(response["ChecksumSHA256"], validate=True) == digest)
            else:
                require(response.get("ServerSideEncryption") == "AES256" and "SSECustomerAlgorithm" not in response)
                require(etag == '"' + hashlib.md5(body).hexdigest() + '"')
            publication = instant(response["LastModified"])
            if "publication_at" in observation:
                require(instant(observation["publication_at"]) == publication)
            require(started_at <= instant(meta["generated_at"]) <= publication <= stopped_at)
            require(meta["tier"] == "t2" and meta["scan_healthy"] is True and meta["sources_healthy"] is True)
            duration = number(meta["duration_seconds"])
            require(0 < duration <= deadline and duration <= (stopped_at - started_at).total_seconds() + 1)
            durations.append(duration)
            memory = artifact("memory_path")
            require(memory["task_arn"] == task)
            require(memory["method"] in {"cgroup-memory.peak", "container-insights-memory-utilized-max"})
            require(started_at <= instant(memory["window_start"]) <= instant(memory["window_end"]) <= stopped_at)
            require((instant(memory["window_start"]) - started_at).total_seconds() <= 60)
            require((stopped_at - instant(memory["window_end"])).total_seconds() <= 60)
            peak = number(memory["peak_bytes"])
            limit = number(memory["limit_bytes"])
            require(type(peak) is int and type(limit) is int)
            require(0 < peak <= limit and limit == int(stopped["memory"]) * 1024 * 1024)
            peaks.append(peak)
            private = scan["data"]["label_inventory"]
            require(isinstance(private, dict) and bool(private))
            daily_scores = {}
            for stack, payload in private.items():
                label_rules.validate_inventory(payload)
                require(set(payload["signals"]) == set(label_rules.SIGNALS))
                require(any(s["state"] != "unavailable" for s in payload["signals"].values()))
                validated += 1
                result = label_rules.evaluate({stack: payload}, tunables=tunables)
                for summary in result["summaries"]:
                    if "score" in summary:
                        daily_scores[(stack, summary["signal"])] = summary["score"]
            scores.append(daily_scores)
        require((previous - first).total_seconds() >= 48 * 3600)
        deltas = []
        for before, after in zip(scores, scores[1:]):
            common = before.keys() & after.keys()
            require(bool(common))
            deltas.extend(abs(before[key] - after[key]) for key in common)
        require(max(deltas) <= tolerance)
        print(json.dumps({"verified": "dated-natural-t2-artifact-contract-v1",
                          "observations": len(observations), "span_hours": (previous-first).total_seconds()/3600,
                          "duration_max_seconds": max(durations),
                          "peak_bytes": max(peaks), "minimized_stack_inputs_validated": validated,
                          "score_pairs_compared": len(deltas), "max_score_delta": max(deltas),
                          "max_score_delta_allowed": tolerance,
                          "privacy_scope": "minimized private input schema only, not all downstream sinks"}, sort_keys=True))
    except (OSError, ValueError, TypeError, KeyError, IndexError, OverflowError):
        print("unverified: missing, invalid or inconsistent local stability artifacts", file=sys.stderr)
        sys.exit(1)
    PY

# remove the local virtualenv (setup can always recreate it)
[group('dev')]
clean:
    rm -rf .venv
